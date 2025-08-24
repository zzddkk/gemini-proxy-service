## ENV
```
pip install -r requirements.txt
```
## run
test.py test pool
test_proxy test the machine proxy
```
python test.py
python test_proxy.py 
```

## deploy
```
選擇 Web Service。

上传gemini-proxy-service 倉庫

Name:  gemini-proxy

Region: Singapore 或 Oregon (US West)。

Branch: main。

Root Directory: 空白。

Runtime: Python 3。

Build Command: pip install -r requirements.txt 。

Start Command: uvicorn proxy:app --host 0.0.0.0 --port 10000

Instance Type: Free。

PROXY_API_KEY : （填入密钥）

GEMINI_API_KEYS ： （填入API）
```