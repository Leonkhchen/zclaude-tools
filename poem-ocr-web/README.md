# 墨評 — 手寫詩句辨識與批改

拍照上傳手寫的詩句 → 呼叫 Colab 上執行的開源辨識模型轉成文字 → 跟標準詩句
逐字比對批改 → 結果可匯出（目前先落地到本機，Google Drive 串接留了明確的
擴充點，見 `drive_export.py`）。

## 架構

```
瀏覽器（拍照/選圖）
   │  上傳照片、選詩句
   ▼
後端 Flask（app.py）── 讀寫 settings.json（Colab 端點、目前使用的模型）
   │  POST /ocr（呼叫 ocr_client.py）
   ▼
Colab 辨識服務（colab/poem_ocr_server.py）
   │  模型可用 /switch_model 隨時替換，不用重跑 Notebook
   ▼
回傳辨識文字 → 後端用 grading.py 逐字比對標準詩句 → 回傳批改結果給前端
```

這是「先出系統設計文件」那次規劃的第 Ⅰ、Ⅱ 階段原型：單一流程打通 + 批改
邏輯／詩句資料庫，還沒做帳號系統與 Google Drive 正式授權。

## 本機啟動後端

```bash
cd poem-ocr-web
pip install -r requirements.txt
python app.py
# 預設在 http://localhost:5001
```

## 啟動 Colab 辨識服務

依照 `colab/README.md` 的步驟，在 Google Colab 開一份 Notebook 執行，會得
到一個對外網址（例如 `https://xxxx.ngrok-free.app`）。

## 串接

1. 打開 `http://localhost:5001`
2. 在「Colab 辨識服務設定」欄位貼上 Colab 印出來的網址，按「連線」
3. 下拉選單會列出 Colab 端目前支援的模型（`cnocr`／`paddleocr`／`trocr`／
   `easyocr`），選一個按「套用」即可切換 —— 不需要重啟 Colab 或後端
4. 選一首詩、上傳照片、按「開始辨識與批改」

## 模型替換怎麼做到「彈性」

- Colab 端的每個模型都實作同一個 `OCRModel` 介面（`load` / `recognize`），
  註冊在 `MODEL_REGISTRY` 表裡，新增模型只要加一個類別、加一行註冊，不用
  動路由或前端
- 後端完全不知道 Colab 端實際在跑哪個模型，只認得 `/health`、`/models`、
  `/switch_model`、`/ocr` 這組固定介面 —— 之後要把 Colab 換成正式部署的
  服務（Cloud Run、自架 GPU 主機），只要新服務實作同一組介面，後端與前端
  程式碼完全不用改
- 已經載入過的模型會快取在 Colab 執行階段的記憶體裡，切換回去是瞬間的，
  只有第一次用某個模型才需要等待載入

## 尚未完成（下一步）

- Google Drive 正式授權（OAuth 2.0 + `drive.file` scope），目前 `drive_export.py`
  先把結果存到本機 `exports/` 資料夾，介面已經設計好，串接時只需要換掉
  `_upload_to_drive()` 的實作
- 使用者帳號與批改歷史紀錄
- 詩句資料庫目前只有 `data/poems.json` 四首示範詩，量產前需要擴充內容來源
