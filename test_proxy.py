import httpx
import certifi
import asyncio
import traceback

# --- 請修改這裡 ---
# 請將這裡替換成您用 curl 測試成功的那枚 Gemini API Key
GEMINI_API_KEY = "AIzaSyA5DjXI2pbhkIhemPMbd9EZ5wsmL7_W38g"
# --- 代碼正文 ---

URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:streamGenerateContent?key={GEMINI_API_KEY}&alt=sse"

async def main():
    """定義我們的異步測試任務"""
    print(f"正在嘗試直接連接到: {URL[:80]}...")
    try:
        # 強制使用 HTTP/1.1，並使用 certifi 證書
        transport = httpx.AsyncHTTPTransport(http1=True, http2=False)
        async with httpx.AsyncClient(transport=transport, verify=certifi.where(), timeout=30.0) as client:
            async with client.stream("POST", URL, json={"contents": [{"parts": [{"text": "Hello, tell me a short story."}]}]}) as response:
                print(f"請求狀態碼: {response.status_code}")
                response.raise_for_status()
                
                print("數據流已成功開始，正在接收數據塊...")
                chunk_count = 0
                async for chunk in response.aiter_bytes():
                    chunk_count += 1
                    # 在 Colab 中，我們可以更頻繁地打印來看到流動效果
                    print(chunk.decode('utf-8'), end="")
                
                print(f"\n\n數據流成功結束！總共接收了 {chunk_count} 個數據塊。")

    except Exception as e:
        print(f"\n--- 發生錯誤 ---")
        print(f"錯誤類型: {type(e).__name__}")
        print(f"錯誤信息: {e}")
        print("詳細錯誤追蹤:")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())