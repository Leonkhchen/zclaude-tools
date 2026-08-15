# Péndulo — 節拍器網頁應用

一個為 iPhone 使用設計的節拍器（Metronome）網頁應用：木質琴身、黃銅擺錘的視覺風格，內建精準的音訊排程引擎，單一 HTML 檔、零依賴，可直接在 Safari 開啟，或「加入主畫面」變成全螢幕的類 App 體驗。

**線上使用：** https://pendulo-metronome-8f3k2x9.zeabur.app

一般使用者操作說明請見 [`使用說明.md`](./使用說明.md)。

## 功能一覽

| 功能 | 說明 |
| --- | --- |
| 速度調整 | 30–260 BPM，拖曳滑桿或點 −／＋ 微調 |
| Tap Tempo | 依實際敲擊節奏自動換算 BPM |
| 拍號 | 每小節 1–9 拍可調，重拍會加大並發亮 |
| 音符細分 | 四分音符／八分音符／三連音，音色隨細分層級變化 |
| 音量 | 獨立音量滑桿 |
| 視覺節拍 | 擺錘依速度擺動、拍點燈號與音訊同步閃爍 |
| 外觀 | 淺色／深色主題，跟隨系統或手動切換 |
| 螢幕常亮 | 播放時透過 Wake Lock API 防止螢幕自動熄滅 |

## 技術重點

- **精準計時**：採用 Web Audio API 的 lookahead scheduler（而非 `setInterval` 直接發聲），避免瀏覽器計時器抖動造成的拍點漂移。詳見 `index.html` 中的 `scheduler()` / `nextNote()`。
- **iOS 音訊解鎖**：`AudioContext` 只在使用者點擊「開始」時建立／恢復，符合 iOS 的自動播放限制。
- **視覺同步**：擺錘動畫與拍點燈號皆對齊音訊排程時間（`requestAnimationFrame` 比對 `audioCtx.currentTime`），而非單純依賴 CSS 動畫時間，因此聲音與畫面不會脫節。
- **零依賴**：整個應用是單一 `index.html`，無需建置流程、無外部字型或 CDN 請求，離線也能開啟。
- **iOS 主畫面圖示**：頁面載入時用 `<canvas>` 動態繪製節拍器圖示，設為 `apple-touch-icon`，不需要額外的圖片檔案。

## 檔案結構

```
metronome-web-app/
├── index.html      # 完整應用（HTML + CSS + JS），畫面左上角有連到 guide.html 的小字連結
├── guide.html      # 使用說明的網頁版（使用說明.md 的 HTML 呈現，與 index.html 一起部署）
├── README.md        # 本檔案（專案說明／技術文件）
└── 使用說明.md        # 使用說明的原始 Markdown 版本
```

> 註：`guide.html` 的檔名刻意使用英文，因為部署環境（Kubernetes ConfigMap）的檔名鍵值不接受中文字元；中文版說明保留在 `使用說明.md`，內容與 `guide.html` 同步維護。

## 本機開發

不需要任何建置工具，直接用瀏覽器開啟 `index.html` 即可測試；若要在區網其他裝置（例如 iPhone）上預覽，可在此資料夾下起一個簡單的靜態伺服器：

```bash
cd metronome-web-app
python3 -m http.server 8000
# 手機與電腦在同一網路時，於 iPhone Safari 開啟 http://<電腦區網 IP>:8000
```

## 部署

目前部署在 [Zeabur](https://zeabur.com)，以 `nginx:alpine` 映像檔搭配設定檔注入的方式提供靜態內容，未經過建置流程。若要重新部署，把更新後的 `index.html` 內容取代 Zeabur 服務設定中的檔案內容即可；也可以改用任何靜態網站託管服務（GitHub Pages、Netlify、Vercel、Cloudflare Pages 等），因為整個應用只有一個 HTML 檔案。
