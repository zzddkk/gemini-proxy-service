import os
import httpx
import itertools
import certifi
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import json # 導入 json 模組

# --- 配置區 ---
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
    if request.url.path == '/':
        return await call_next(request)

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

# --- 非流式 (Non-streaming) 處理 (已升級) ---
@app.post("/{api_version:path}/models/{model:path}:generateContent")
async def proxy_gemini_non_stream(request: Request, api_version: str, model: str):
    try:
        request_body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "無效的 JSON 請求體 (Invalid JSON body)"})

    last_error = None
    num_keys = len(GEMINI_API_KEYS)

    async with httpx.AsyncClient(verify=certifi.where()) as client:
        # 迴圈嘗試所有可用的 Key
        for i in range(num_keys):
            selected_gemini_key = next(key_cycler)
            print(f"--- 嘗試第 {i+1}/{num_keys} 個密鑰: ...{selected_gemini_key[-4:]} [非流式] ---")
            
            target_url = f"{GEMINI_API_BASE_URL}{request.url.path}?key={selected_gemini_key}"
            
            try:
                google_res = await client.post(target_url, json=request_body, timeout=180.0)
                google_res.raise_for_status()
                # 請求成功，直接返回結果
                print(f"--- 密鑰 ...{selected_gemini_key[-4:]} 請求成功 ---")
                return JSONResponse(content=google_res.json(), status_code=google_res.status_code)
            
            except httpx.HTTPStatusError as e:
                # 捕獲 HTTP 狀態錯誤
                error_details = e.response.json()
                last_error = (error_details, e.response.status_code)
                
                # 如果是 429 (速率超限) 或 5xx (伺服器錯誤)，則嘗試下一個 key
                if e.response.status_code == 429 or e.response.status_code >= 500:
                    print(f"--- 密鑰 ...{selected_gemini_key[-4:]} 遇到 {e.response.status_code} 錯誤，正在嘗試下一個密鑰... ---")
                    continue  # 進入下一次迴圈
                else:
                    # 如果是其他客戶端錯誤 (如 400, 403, 404)，重試無效，直接返回錯誤
                    print(f"--- 遇到不可重試的錯誤 {e.response.status_code}，終止請求 ---")
                    return JSONResponse(content=error_details, status_code=e.response.status_code)
                    
            except httpx.RequestError as e:
                # 捕獲網路層級的錯誤
                last_error = ({"error": {"message": f"請求 Google API 時出錯: {e}"}}, 502)
                print(f"--- 密鑰 ...{selected_gemini_key[-4:]} 發生網路錯誤，正在嘗試下一個密鑰... ---")
                continue

    # 如果迴圈結束後仍然沒有成功 (所有 key 都失敗了)
    print("--- 所有密鑰均嘗試失敗，返回最後一個遇到的錯誤 ---")
    if last_error:
        return JSONResponse(content=last_error[0], status_code=last_error[1])
    
    # 備用錯誤，理論上不應該觸發
    raise HTTPException(status_code=500, detail="所有 API 密鑰均嘗試失敗，且未捕獲到具體錯誤。")


# --- 流式 (Streaming) 處理 (已升級) ---
@app.post("/{api_version:path}/models/{model:path}:streamGenerateContent")
async def proxy_gemini_stream(request: Request, api_version: str, model: str):
    try:
        request_body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "無效的 JSON 請求體 (Invalid JSON body)"})

    num_keys = len(GEMINI_API_KEYS)

    async def stream_generator():
        last_error_content = None
        last_error_status = 500

        # 迴圈嘗試所有可用的 Key
        for i in range(num_keys):
            selected_gemini_key = next(key_cycler)
            print(f"--- 嘗試第 {i+1}/{num_keys} 個密鑰: ...{selected_gemini_key[-4:]} [流式] ---")
            
            target_url = f"{GEMINI_API_BASE_URL}{request.url.path}?key={selected_gemini_key}&alt=sse"
            
            try:
                async with httpx.AsyncClient(verify=certifi.where()) as client:
                    async with client.stream("POST", target_url, json=request_body, timeout=180.0) as response:
                        response.raise_for_status()
                        
                        # 請求成功，開始轉發數據流
                        print(f"--- 密鑰 ...{selected_gemini_key[-4:]} 流式請求成功 ---")
                        async for chunk in response.aiter_bytes():
                            yield chunk
                        return # 成功結束生成器

            except httpx.HTTPStatusError as e:
                # 捕獲 HTTP 狀態錯誤
                last_error_content = await e.response.aread()
                last_error_status = e.response.status_code
                
                # 如果是 429 (速率超限) 或 5xx (伺服器錯誤)，則嘗試下一個 key
                if e.response.status_code == 429 or e.response.status_code >= 500:
                    print(f"--- 密鑰 ...{selected_gemini_key[-4:]} 遇到 {e.response.status_code} 錯誤，正在嘗試下一個密鑰... ---")
                    continue # 進入下一次迴圈
                else:
                    # 如果是其他客戶端錯誤，直接產出錯誤並終止
                    print(f"--- 遇到不可重試的錯誤 {e.response.status_code}，終止請求 ---")
                    yield last_error_content
                    return

            except httpx.RequestError as e:
                # 捕獲網路層級的錯誤
                error_message = f'{{"error": {{"message": "請求 Google API 時出錯: {e}"}}}}'
                last_error_content = error_message.encode('utf-8')
                last_error_status = 502
                print(f"--- 密鑰 ...{selected_gemini_key[-4:]} 發生網路錯誤，正在嘗試下一個密鑰... ---")
                continue
        
        # 如果所有 key 都失敗了，產出最後一個錯誤
        print("--- 所有密鑰均嘗試失敗，返回最後一個遇到的錯誤 ---")
        if last_error_content:
            # 這裡我們不能直接返回 JSONResponse，所以我們以流的形式返回錯誤訊息
            yield last_error_content

    # 流式響應需要特殊的 media_type
    # 注意：如果最終是錯誤，客戶端可能需要解析這個流來獲取錯誤信息
    return StreamingResponse(stream_generator(), media_type='text/event-stream')


@app.get("/")
def read_root():
    return {"status": "Gemini API Proxy with streaming and non-streaming support is running"}