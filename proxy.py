import os
import httpx
import itertools
import certifi
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

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

@app.post("/{api_version:path}/models/{model:path}:streamGenerateContent")
@app.post("/{api_version:path}/models/{model:path}:generateContent")
async def proxy_gemini(request: Request, api_version: str, model: str):
    if api_version not in ["v1", "v1beta"]:
         raise HTTPException(status_code=404, detail="API version not supported")

    selected_gemini_key = next(key_cycler)
    print(f"--- 密鑰匹配成功! 正在使用密鑰: ...{selected_gemini_key[-4:]} 以非流式模式轉發請求 ---")
    
    # 【最終修正】: 徹底構建一個乾淨的、非流式的目標URL
    # 1. 獲取原始路徑
    path = request.url.path
    # 2. 確保路徑指向非流式接口
    if ":streamGenerateContent" in path:
        path = path.replace(":streamGenerateContent", ":generateContent")
    # 3. 構建URL，且不包含任何來自客戶端的查詢參數 (如 ?alt=sse)
    target_url = f"{GEMINI_API_BASE_URL}{path}?key={selected_gemini_key}"
    
    request_body = await request.json()
    
    transport = httpx.AsyncHTTPTransport(http1=True, http2=False)
    
    async with httpx.AsyncClient(transport=transport, verify=certifi.where()) as client:
        try:
            google_res = await client.post(target_url, json=request_body, timeout=180.0)
            google_res.raise_for_status()
            return JSONResponse(content=google_res.json())

        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.json())
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"請求 Google API 時出錯: {e}")

@app.get("/")
def read_root():
    return {"status": "Gemini API Proxy with non-streaming mode is running"}