# Colab 辨識服務

在 Google Colab 開一份新 Notebook，依序執行以下 cell，就會得到一個對外的
辨識 API 端點，貼到「墨評」後端的設定頁即可串接。

## 1. 安裝套件

先裝共用套件，再依你想用的模型裝對應套件（不必全裝，缺哪個裝哪個即可）：

```python
!pip install -q fastapi uvicorn python-multipart pyngrok pillow nest_asyncio

# 依你要用的模型挑著裝：
!pip install -q cnocr                     # cnocr（預設、最輕量）
# !pip install -q paddlepaddle paddleocr  # paddleocr
# !pip install -q easyocr                 # easyocr
# !pip install -q transformers torch      # trocr
```

## 2. 貼上 `poem_ocr_server.py` 的內容

把這個資料夾裡 `poem_ocr_server.py` 的完整內容貼進一個 cell 執行（或用
`%%writefile poem_ocr_server.py` 存成檔案再 `import`）。這個檔案本身不會
啟動服務，只會定義模型與 FastAPI app。

## 3. 啟動服務並取得對外網址

```python
import nest_asyncio, threading
from pyngrok import ngrok

nest_asyncio.apply()

# 如果有 ngrok 帳號，建議先設定 authtoken，連線比較穩定：
# ngrok.set_auth_token("你的_NGROK_AUTHTOKEN")

public_url = ngrok.connect(8000)
print("辨識服務網址：", public_url)

threading.Thread(target=run, daemon=True).start()
```

執行後印出的網址（例如 `https://xxxx.ngrok-free.app`）就是要貼到「墨評」
後端設定頁「Colab 端點」欄位的值。

## 4. 換模型不用重跑 Notebook

服務啟動後，直接呼叫 API 就能切換使用中的模型：

```python
import requests
requests.post(f"{public_url}/switch_model", json={"name": "paddleocr"}).json()
```

或者直接在「墨評」網頁的設定頁下拉選單裡選模型、按「套用」，後端會呼叫
同一支 `/switch_model` API。第一次切到某個模型會花時間載入權重，之後在
同一個 Colab 執行階段內切回來都是瞬間的（模型會被快取住）。

## 5. 新增一個新模型

打開 `poem_ocr_server.py`：

1. 新增一個繼承 `OCRModel` 的類別，實作 `load()`（載入權重）與
   `recognize(image)`（回傳辨識文字）
2. 把它加進 `MODEL_REGISTRY = {"你的模型名稱": 你的類別, ...}`

不用改任何路由或前端程式碼，重新執行這支檔案的 cell 後，新模型就會出現在
`/models` 清單、也會出現在「墨評」設定頁的下拉選單裡。

## 注意事項

- 免費版 Colab 在閒置一段時間後會自動斷線，這個網址也會跟著失效，重新執行
  一次上面的步驟即可拿到新網址。
- 這個做法適合原型開發與小量測試；正式上線建議把 `poem_ocr_server.py`
  部署到常駐環境（Cloud Run、自架 GPU 主機等），因為程式碼完全沒有動，
  只是換一個地方跑 `uvicorn`。
