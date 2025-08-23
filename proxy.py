import os
import httpx
import itertools
import certifi
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse

# --- 配置區 ---
# 從環境變量中讀取密鑰，這是在雲端部署的標準做法
# 我們將在 Render 的儀表板上設置這些值
PROXY_API_KEY = os.getenv("PROXY_API_KEY")
GEMINI_API_KEYS_STR = os.getenv("GEMINI_API_KEYS")

# --- 代碼正文 (無需修改) ---

# 檢查環境變量是否已設置
if not PROXY_API_KEY or not GEMINI_API_KEYS_STR:
    raise ValueError("環境變量 PROXY_API_KEY 和 GEMINI_API_KEYS 未設置")

# 將逗號分隔的密鑰字符串轉換為列表
GEMINI_API_KEYS = [key.strip() for key in GEMINI_API_KEYS_STR.split(',')]

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
    print(f"--- 密鑰匹配成功! 正在使用密鑰: ...{selected_gemini_key[-4:]} 轉發請求 (協議: HTTP/1.1) ---")
    
    original_path = request.url.path
    target_url = f"{GEMINI_API_BASE_URL}{original_path}?key={selected_gemini_key}"
    request_body = await request.json()
    
    transport = httpx.AsyncHTTPTransport(http1=True, http2=False)
    
    async with httpx.AsyncClient(transport=transport, verify=certifi.where()) as client:
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

# 在 Render 上，我們不需要 uvicorn.run()，因為 Render 會用自己的命令啟動服務