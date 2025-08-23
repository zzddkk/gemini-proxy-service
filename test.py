import requests
import json
import time

# --- 配置區: 請根據您的部署情況修改這裡 ---

# 1. 您的代理服務的公開URL (本地測試請使用 http://127.0.0.1:8000)
PROXY_URL = "http://127.0.0.1:8000"

# 2. 您在 proxy.py 中設置的那個代理密鑰 (PROXY_API_KEY)
CORRECT_PROXY_KEY = "123456"

# 3. 用於測試的Gemini模型
MODEL_NAME = "gemini-2.5-flash"

# --- 測試腳本正文 (無需修改) ---

def test_successful_request():
    """測試一個成功的、流式的API請求"""
    print("--- [1] 正在執行: 成功請求測試 ---")
    
    # 使用 streamGenerateContent 端點
    endpoint = f"{PROXY_URL}/v1/models/{MODEL_NAME}:streamGenerateContent"
    headers = {
        "Authorization": f"Bearer {CORRECT_PROXY_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{
            "parts": [{"text": "回答 3.11 和 3.7谁大。"}]
        }]
    }

    try:
        with requests.post(endpoint, headers=headers, json=payload, stream=True, timeout=60) as response:
            print(f"狀態碼: {response.status_code}")
            response.raise_for_status()

            print("Gemini回復 (流式輸出):")
            for chunk in response.iter_content(chunk_size=None):
                if chunk:
                    print(chunk.decode('utf-8'), end="", flush=True)
            
            print("\n--- [1] 成功請求測試: 通過 ---\n")
            return True
    except requests.exceptions.RequestException as e:
        print(f"\n請求失敗: {e}")
        print("--- [1] 成功請求測試: 失敗 ---\n")
        return False

def test_wrong_key():
    """測試使用錯誤的API密鑰"""
    print("--- [2] 正在執行: 錯誤密鑰認證測試 ---")
    endpoint = f"{PROXY_URL}/v1/models/{MODEL_NAME}:streamGenerateContent"
    headers = {"Authorization": "Bearer I_AM_A_WRONG_KEY"}
    try:
        response = requests.post(endpoint, headers=headers, json={"contents": [{"parts": [{"text": "test"}]}]}, timeout=10)
        print(f"狀態碼: {response.status_code}, 響應: {response.text}")
        if response.status_code == 401:
            print("--- [2] 錯誤密鑰認證測試: 通過 (伺服器按預期拒絕了請求) ---\n")
        else:
            print(f"--- [2] 錯誤密鑰認證測試: 失敗 (期望狀態碼 401, 實際為 {response.status_code}) ---\n")
    except requests.exceptions.RequestException as e:
        print(f"--- [2] 錯誤密鑰認證測試: 失敗 ({e}) ---\n")

def test_key_rotation(num_requests=5):
    """驗證密鑰輪換功能"""
    print(f"--- [3] 正在執行: 密鑰輪換驗證 (將連續發送 {num_requests} 次請求) ---")
    print("重要提示：請同時觀察您的【代理伺服器】的控制台日誌輸出。\n")
    
    for i in range(num_requests):
        print(f"發送第 {i+1}/{num_requests} 次請求...")
        if not test_successful_request():
            print(f"第 {i+1} 次請求失敗，測試中止。")
            break
        time.sleep(1)
    
    print(f"--- [3] 密鑰輪換驗證: 完成 (請檢查伺服器日誌) ---")

if __name__ == "__main__":
    # 依次運行基礎測試
    # if test_successful_request():
    #     test_wrong_key()
    #     # 詢問是否進行輪換測試
    #     if input("基礎測試通過。是否要繼續進行密鑰輪換測試? (y/n): ").lower() == 'y':
    #         test_key_rotation(num_requests=5)
    test_successful_request()