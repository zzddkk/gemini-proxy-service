import os
import httpx
import itertools
import certifi
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse # 導入 JSONResponse

# --- 配置區 ---
PROXY_API_KEY = os.getenv("PROXY_API_KEY")
GEMINI_API_KEYS_STR = os.getenv("GEMINI_API_KEYS")

# --- 代碼正文 (無需修改) ---

if not PROXY_API_KEY or not GEMINI_API_KEYS_STR:
    raise ValueError("環境變量 PROXY_API_KEY 和 GEMINI_API_KEYS 未設置")

GEMINI_API_KEYS = [key.strip() for key in GEMINI_API_KEYS_STR.split(',')]
key_cycler = itertools.cycle(GEMINI_API_KEYS)
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com"
app = FastAPI()

@app.middleware("http")
async def authenticate_request(request: Request, call_next):
    # (認證部分代碼保持不變)
    auth_header = request.headers.get("Authorization")
    google_api_header = request.headers.get("x-goog-api-key")
    is_authorized = False
    if auth_header and auth_header == f"Bearer {PROXY_API_KEY}":
        is_authorized = True
    elif google_api_header and google_api_header == PROXY_API_KEY:
        is_authorized = True
    if not is_authorized:
        raise HTTPException(status_code=401, detail="無效的 API 密鑰")
    response = await call_next(request)
    return response

# 我們將把流式和非流式請求，統一用非流式的方式返回
@app.post("/{api_version:path}/models/{model:path}:streamGenerateContent")
@app.post("/{api_version:path}/models/{model:path}:generateContent")
async def proxy_gemini(request: Request, api_version: str, model: str):
    if api_version not in ["v1", "v1beta"]:
         raise HTTPException(status_code=404, detail="API version not supported")

    selected_gemini_key = next(key_cycler)
    print(f"--- 密鑰匹配成功! 正在使用密鑰: ...{selected_gemini_key[-4:]} 轉發請求 ---")
    
    # 【核心修改】: 將客戶端的流式請求，轉換為對 Google 的非流式請求
    # 我們將 :streamGenerateContent 替換為 :generateContent
    original_path = request.url.path.replace(":streamGenerateContent", ":generateContent")
    
    target_url = f"{GEMINI_API_BASE_URL}{original_path}?key={selected_gemini_key}"
    request_body = await request.json()
    
    transport = httpx.AsyncHTTPTransport(http1=True, http2=False)
    
    async with httpx.AsyncClient(transport=transport, verify=certifi.where()) as client:
        try:
            # 【核心修改】: 使用普通的 post 請求，而不是 stream
            google_res = await client.post(target_url, json=request_body, timeout=180.0) # 延長超時以等待完整響應
            google_res.raise_for_status() # 如果Google返回錯誤，這裡會拋出異常

            # 【核心修改】: 將從 Google 收到的完整 JSON 數據，一次性返回給客戶端
            return JSONResponse(content=google_res.json())

        except httpx.HTTPStatusError as e:
            # 將 Google 返回的詳細錯誤信息轉發給客戶端
            raise HTTPException(status_code=e.response.status_code, detail=e.response.json())
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"請求 Google API 時出錯: {e}")

@app.get("/")
def read_root():
    return {"status": "Gemini API Proxy with non-streaming mode is running"}