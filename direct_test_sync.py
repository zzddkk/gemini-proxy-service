import requests
import json

# --- 配置區 ---
# 請將這裡替換成您用 curl 測試成功的那枚 Gemini API Key
GEMINI_API_KEY = "AIzaSyA5DjXI2pbhkIhemPMbd9EZ5wsmL7_W38g"
# --- 代碼正文 ---

URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:streamGenerateContent?key={GEMINI_API_KEY}&alt=sse"

def main_sync():
    """定義我們的同步測試任務"""
    print(f"正在使用 [requests] 庫直接連接到: {URL[:80]}...")
    headers = {
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{
            "parts": [{"text": "Hello, tell me a short story."}]
        }]
    }

    try:
        with requests.post(URL, headers=headers, json=payload, stream=True, timeout=60) as response:
            print(f"請求狀態碼: {response.status_code}")
            response.raise_for_status()

            print("數據流已成功開始，正在接收數據塊...")
            chunk_count = 0
            for chunk in response.iter_content(chunk_size=None):
                if chunk:
                    chunk_count += 1
                    # 簡單處理一下SSE格式，只打印主要內容
                    decoded_chunk = chunk.decode('utf-8')
                    if '"text":' in decoded_chunk:
                        print(decoded_chunk.strip())

            print(f"\n數據流成功結束！總共接收了 {chunk_count} 個數據塊。")

    except requests.exceptions.RequestException as e:
        print(f"\n--- 發生錯誤 ---")
        print(f"錯誤類型: {type(e).__name__}")
        print(f"錯誤信息: {e}")

if __name__ == "__main__":
    main_sync()