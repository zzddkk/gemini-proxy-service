import os
import httpx
import itertools
import certifi
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

# --- 配置區 ---
# 建議從環境變數讀取，確保安全
PROXY_API_KEY = os.getenv("PROXY_API_KEY")
GEMINI_API_KEYS_STR = os.getenv("GEMINI_API_KEYS")

# --- 代碼正文 ---

if not PROXY_API_KEY or not GEMINI_API_KEYS_STR:
    raise ValueError("環境變量 PROXY_API_KEY 和 GEMINI_API_KEYS 未設置")

GEMINI_API_KEYS = [key.strip() for key in GEMINI_API_KEYS_STR.split(',')]
key_cycler = itertools.cycle(GEMINI_API_KEYS)
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com"

app = FastAPI()

@app.middleware("http")
async def authenticate_request(request: Request, call_next):
    # 如果是根路徑 (通常是健康檢查)，直接放行
    if request.url.path == '/':
        return await call_next(request)

    # 認證邏輯
    auth_header = request.headers.get("Authorization")
    google_api_header = request.headers.get("x-goog-api-key")
    
    is_authorized = False
    if auth_header and auth_header == f"Bearer {PROXY_API_KEY}":
        is_authorized = True
    elif google_api_header and google_api_header == PROXY_API_KEY:
        is_authorized = True
        
    if not is_authorized:
        return JSONResponse(
            status_code=401,
            content={"error": {"message": "無效的 API 密鑰 (Invalid API Key)"}}
        )
        
    response = await call_next(request)
    return response

# --- 非流式 (Non-streaming) 處理 ---
@app.post("/{api_version:path}/models/{model:path}:generateContent")
async def proxy_gemini_non_stream(request: Request, api_version: str, model: str):
    selected_gemini_key = next(key_cycler)
    print(f"--- 密鑰匹配成功! 正在使用密鑰: ...{selected_gemini_key[-4:]} 以【非流式】模式轉發請求 ---")
    
    target_url = f"{GEMINI_API_BASE_URL}{request.url.path}?key={selected_gemini_key}"
    
    try:
        request_body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "無效的 JSON 請求體 (Invalid JSON body)"})

    async with httpx.AsyncClient(verify=certifi.where()) as client:
        try:
            google_res = await client.post(target_url, json=request_body, timeout=180.0)
            google_res.raise_for_status()
            return JSONResponse(content=google_res.json(), status_code=google_res.status_code)
        except httpx.HTTPStatusError as e:
            error_details = e.response.json()
            return JSONResponse(content=error_details, status_code=e.response.status_code)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"請求 Google API 時出錯: {e}")

# --- 流式 (Streaming) 處理 ---
@app.post("/{api_version:path}/models/{model:path}:streamGenerateContent")
async def proxy_gemini_stream(request: Request, api_version: str, model: str):
    selected_gemini_key = next(key_cycler)
    print(f"--- 密鑰匹配成功! 正在使用密鑰: ...{selected_gemini_key[-4:]} 以【流式】模式轉發請求 ---")

    # 為了實現流式傳輸，Google API 需要 `alt=sse` 參數
    target_url = f"{GEMINI_API_BASE_URL}{request.url.path}?key={selected_gemini_key}&alt=sse"
    
    try:
        request_body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "無效的 JSON 請求體 (Invalid JSON body)"})

    async def stream_generator():
        """這個異步生成器會逐塊從 Google API 讀取數據並轉發"""
        async with httpx.AsyncClient(verify=certifi.where()) as client:
            try:
                async with client.stream("POST", target_url, json=request_body, timeout=180.0) as response:
                    # 首先檢查初始響應狀態碼，如果 Google 返回錯誤，則不進入流式處理
                    response.raise_for_status()
                    # 逐塊讀取並轉發
                    async for chunk in response.aiter_bytes():
                        yield chunk
            except httpx.HTTPStatusError as e:
                # 如果在建立連接時就出錯，嘗試讀取錯誤訊息並以流的形式返回
                error_content = e.response.read()
                yield error_content
            except httpx.RequestError as e:
                 # 處理網絡層面的錯誤
                error_message = f'{{"error": {{"message": "請求 Google API 時出錯: {e}"}}}}'
                yield error_message.encode('utf-8')


    # 使用 StreamingResponse 將生成器返回的數據流式傳輸給客戶端
    # media_type='text/event-stream' 是 Server-Sent Events (SSE) 的標準類型
    return StreamingResponse(stream_generator(), media_type='text/event-stream')

@app.get("/")
def read_root():
    return {"status": "Gemini API Proxy with streaming and non-streaming support is running"}