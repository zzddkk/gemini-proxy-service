import os
import httpx
import itertools
import certifi  # <--- 這是新增的第一行
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
# --- 配置区 ---

# 1. 你的代理服务的API Key，客户端连接时需要提供这个Key
PROXY_API_KEY = "123456" # 请务必修改成一个复杂且安全的密钥

# 2. 你的Google Gemini API Key 池
GEMINI_API_KEYS = [
    "AIzaSyAFeywFR_te1isEPmdupiZQgAqlW-KK_jQ",
    "AIzaSyBOAwfms4DHzQa-mf2PqSXL-5V-1vKo42o",
    "AIzaSyA5DjXI2pbhkIhemPMbd9EZ5wsmL7_W38g",
    # ... 在这里添加更多你的Gemini API Key
]


# --- 代碼正文 (無需修改) ---

if not GEMINI_API_KEYS or "YOUR_GEMINI_API_KEY_THAT_WORKED_IN_CURL" in GEMINI_API_KEYS:
    raise ValueError("請在 GEMINI_API_KEYS 列表中配置你用 curl 測試成功的 Gemini API Key")

key_cycler = itertools.cycle(GEMINI_API_KEYS)
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com"
app = FastAPI()

@app.middleware("http")
async def authenticate_request(request: Request, call_next):
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
    print(f"--- 密鑰匹配成功! 正在使用密鑰: ...{selected_gemini_key[-4:]} 轉發請求 ---")
    
    original_path = request.url.path
    target_url = f"{GEMINI_API_BASE_URL}{original_path}?key={selected_gemini_key}"
    request_body = await request.json()
    
    # 【最終修正】: 明確指定 SSL 證書進行驗證
    async with httpx.AsyncClient(verify=certifi.where()) as client: # <--- 這是修改的第二行
        try:
            google_req = client.build_request("POST", target_url, json=request_body, timeout=120.0)
            google_res = await client.send(google_req, stream=True)
            proxy_headers = dict(google_res.headers)
            proxy_headers.pop("content-encoding", None)
            proxy_headers.pop("Content-Encoding", None)
            proxy_headers.pop("transfer-encoding", None)
            return StreamingResponse(
                google_res.aiter_bytes(),
                status_code=google_res.status_code,
                headers=proxy_headers
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"請求 Google API 時出錯: {e}")

@app.get("/")
def read_root():
    return {"status": "Gemini API Proxy is running"}

import uvicorn
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
