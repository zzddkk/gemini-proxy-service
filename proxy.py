import os
import httpx
import itertools
import certifi
import asyncio
import time
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

# --- 配置區 ---
PROXY_API_KEY = os.getenv("PROXY_API_KEY")
GEMINI_API_KEYS_STR = os.getenv("GEMINI_API_KEYS")
# 禁用金鑰後，多少秒後自動重新啟用
RE_ENABLE_SECONDS = int(os.getenv("RE_ENABLE_SECONDS", 3600)) 

# --- 代碼正文 ---

if not PROXY_API_KEY or not GEMINI_API_KEYS_STR:
    raise ValueError("環境變量 PROXY_API_KEY 和 GEMINI_API_KEYS 未設置")

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com"

# --- 核心 API 金鑰池管理 ---

class ApiKey:
    """用於管理單一 API 金鑰狀態的類"""
    def __init__(self, key: str):
        self.key = key
        self.status = "ACTIVE"  # 可選狀態: ACTIVE, DISABLED
        self.disabled_at = None

    def disable(self):
        """禁用此金鑰"""
        self.status = "DISABLED"
        self.disabled_at = time.time()
        print(f"--- 金鑰 ...{self.key[-4:]} 已被禁用 ---")

    def activate(self):
        """啟用此金鑰"""
        self.status = "ACTIVE"
        self.disabled_at = None
        print(f"--- 金鑰 ...{self.key[-4:]} 已被重新啟用 ---")

class KeyManager:
    """管理和輪詢 API 金鑰池"""
    def __init__(self, keys: list[str]):
        if not keys:
            raise ValueError("API 金鑰列表不可為空")
        self._keys = [ApiKey(k) for k in keys]
        self._lock = asyncio.Lock()
        self._cycler = itertools.cycle(range(len(self._keys)))

    async def get_next_key(self) -> ApiKey | None:
        """異步、安全地獲取下一個可用的金鑰"""
        async with self._lock:
            for _ in range(len(self._keys)):
                key_index = next(self._cycler)
                key_obj = self._keys[key_index]
                if key_obj.status == "ACTIVE":
                    return key_obj
            return None # 如果所有金鑰都禁用

    async def disable_key(self, key_obj: ApiKey):
        """異步、安全地禁用一個金鑰"""
        async with self._lock:
            key_obj.disable()

    async def re_enable_keys_task(self):
        """定期檢查並重新啟用金鑰的背景任務"""
        while True:
            await asyncio.sleep(60) # 每分鐘檢查一次
            async with self._lock:
                for key_obj in self._keys:
                    if key_obj.status == "DISABLED" and \
                       time.time() - key_obj.disabled_at > RE_ENABLE_SECONDS:
                        key_obj.activate()

key_manager = KeyManager([key.strip() for key in GEMINI_API_KEYS_STR.split(',')])
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    """在應用啟動時，創建背景任務"""
    asyncio.create_task(key_manager.re_enable_keys_task())
    print("--- 金鑰自動重新啟用背景任務已啟動 ---")

@app.middleware("http")
async def authenticate_request(request: Request, call_next):
    if request.url.path == '/':
        return await call_next(request)
    auth_header = request.headers.get("Authorization")
    google_api_header = request.headers.get("x-goog-api-key")
    if not ( (auth_header and auth_header == f"Bearer {PROXY_API_KEY}") or \
             (google_api_header and google_api_header == PROXY_API_KEY) ):
        return JSONResponse(status_code=401, content={"error": {"message": "無效的 API 密鑰"}})
    return await call_next(request)

async def process_request(request: Request, stream: bool):
    """統一處理流式和非流式請求的核心邏輯"""
    try:
        request_body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "無效的 JSON 請求體"})

    for _ in range(len(key_manager._keys)): # 最多重試金鑰池大小的次數
        key_obj = await key_manager.get_next_key()
        if not key_obj:
            raise HTTPException(status_code=503, detail="所有 API 金鑰均不可用")

        print(f"--- 正在嘗試使用金鑰: ...{key_obj.key[-4:]} ---")
        
        path = request.url.path
        params = {'key': key_obj.key}
        if stream:
            params['alt'] = 'sse'

        target_url = f"{GEMINI_API_BASE_URL}{path}"

        async with httpx.AsyncClient(verify=certifi.where()) as client:
            try:
                if stream:
                    # 流式請求處理
                    async def stream_generator():
                        async with client.stream("POST", target_url, params=params, json=request_body, timeout=180.0) as response:
                            response.raise_for_status()
                            async for chunk in response.aiter_bytes():
                                yield chunk
                    return StreamingResponse(stream_generator(), media_type='text/event-stream')
                else:
                    # 非流式請求處理
                    response = await client.post(target_url, params=params, json=request_body, timeout=180.0)
                    response.raise_for_status()
                    return JSONResponse(content=response.json(), status_code=response.status_code)

            except httpx.HTTPStatusError as e:
                # 如果是 400 (無效金鑰) 或 429 (額度耗盡)，則禁用金鑰並重試
                if e.response.status_code in [400, 429]:
                    print(f"--- 金鑰 ...{key_obj.key[-4:]} 請求失敗，狀態碼: {e.response.status_code}。正在禁用並重試下一個... ---")
                    await key_manager.disable_key(key_obj)
                    continue # 繼續循環，嘗試下一個金鑰
                else:
                    # 其他錯誤直接返回給客戶端
                    return JSONResponse(content=e.response.json(), status_code=e.response.status_code)
            except httpx.RequestError as e:
                # 網絡層錯誤，直接拋出異常
                raise HTTPException(status_code=502, detail=f"請求 Google API 時出錯: {e}")

    # 如果循環結束仍未成功，說明所有金鑰都嘗試失敗了
    raise HTTPException(status_code=503, detail="所有 API 金鑰均嘗試失敗，請稍後再試")

@app.post("/{api_version:path}/models/{model:path}:generateContent")
async def proxy_gemini_non_stream(request: Request):
    return await process_request(request, stream=False)

@app.post("/{api_version:path}/models/{model:path}:streamGenerateContent")
async def proxy_gemini_stream(request: Request):
    return await process_request(request, stream=True)

@app.get("/")
def read_root():
    return {"status": "Complete Gemini API Key Pool Proxy is running"}