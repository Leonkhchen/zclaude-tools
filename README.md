# EPUB / PDF 轉換器

**Windows GUI 工具，支援 EPUB ↔ PDF / Markdown 互相轉換，完整支援繁體中文排版。**

![Python](https://img.shields.io/badge/Python-3.13-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)
![Version](https://img.shields.io/badge/Version-v1.1-orange)

---

## 功能特色

| 功能 | 說明 |
|------|------|
| **EPUB → PDF** | Calibre 主引擎（最佳品質）+ reportlab 備援（保證中文顯示） |
| **EPUB → Markdown** | 純 Python 實作，保留標題、粗體、表格、圖片等格式 |
| **EPUB → PDF + MD** | 一次同時產出兩種格式 |
| **PDF → EPUB** | Calibre 主引擎 + PyMuPDF 備援 |
| **批次轉換** | 一次加入多個檔案或整個資料夾（含子資料夾） |
| **拖放支援** | 直接將 .epub / .pdf 拖入視窗 |
| **CJK 中文** | 自動嵌入 Microsoft JhengHei 字型，確保中文正確顯示 |

---

## 系統需求

- **作業系統**：Windows 10 / 11
- **Python**：3.10 以上
- **Calibre**：建議安裝（主引擎，品質最佳）

---

## 安裝步驟

### 1. 安裝 Calibre（建議）

前往 [https://calibre-ebook.com/download](https://calibre-ebook.com/download) 下載並安裝。

> 未安裝 Calibre 仍可使用，程式會自動切換為 reportlab 備援引擎。

### 2. 安裝 Python 套件

```bash
pip install tkinterdnd2 ebooklib beautifulsoup4 lxml pillow reportlab pymupdf
```

### 3. 下載程式

```bash
git clone https://github.com/Leonkhchen/zclaude-tools.git
cd zclaude-tools
```

---

## 使用方法

### 方法一：雙擊啟動（最簡單）

直接雙擊 `開啟EPUB轉換器.bat`，程式會在背景開啟 GUI 視窗。

### 方法二：命令列啟動

```bash
python epub_to_pdf_gui.py
```

---

## GUI 操作說明

1. **新增檔案**：點「＋ 新增檔案」選擇 `.epub` 或 `.pdf`，或直接拖放到清單
2. **選擇格式**：右側選 PDF / Markdown / PDF + Markdown
3. **設定輸出資料夾**：預設為 `C:\Zepub`（自動建立），可自行更改
4. **開始轉換**：按「▶ 開始轉換」，進度條會顯示轉換狀態
5. **查看結果**：按「📂 開啟輸出資料夾」直接瀏覽輸出檔案

### 轉換模式說明

| 輸入 | 選擇格式 | 輸出 |
|------|----------|------|
| `.epub` | PDF 文件 | `.pdf` |
| `.epub` | Markdown | `.md` |
| `.epub` | PDF + Markdown | `.pdf` + `.md` |
| `.pdf` | 自動偵測 | `.epub` |

> 輸入 `.pdf` 時，程式會自動偵測並切換為「PDF → EPUB」模式，不需手動選格式。

---

## 狀態圖示

| 圖示 | 說明 |
|------|------|
| ⏳ 待轉換 | 尚未開始 |
| ⚙️ 轉換中 | 正在處理 |
| ✅ 成功 | 轉換完成 |
| ❌ 失敗 | 轉換失敗（可查看 Log 了解原因） |

---

## 已知限制

1. **Calibre 逾時**：部分含大量 JavaScript 的 EPUB 會觸發 60 秒逾時，程式會自動切換備援引擎。
2. **備援引擎樣式**：reportlab 備援引擎不保留原始 CSS 樣式（顏色、字距），但保留段落與標題結構。
3. **PDF → EPUB 圖片**：PyMuPDF 備援引擎目前僅轉換文字，圖片需靠 Calibre 引擎保留。
4. **SVG 圖片**：reportlab 不支援 SVG，SVG 圖片會被略過。
5. **僅支援 Windows**：字型路徑、`.bat` 啟動腳本均針對 Windows 設計。

---

## 版本歷程

| 版本 | 日期 | 說明 |
|------|------|------|
| v1.1 | 2026-04-30 | 修正批次轉換 bug（第二個檔案不執行），修正 reportlab 圖片縮放 |
| v1.0 | 2026-04-29 | 新增 Markdown 輸出、PDF→EPUB、預設輸出 C:\Zepub、隱藏 Calibre 子視窗 |
| v0.5 | 2026-04-28 | 進度條改為動畫模式 |
| v0.4 | 2026-04-28 | 修正 CJK 字型（改用 reportlab 直接輸出） |
| v0.3 | 2026-04-27 | 加入 Calibre 主引擎 + reportlab 備援 |
| v0.2 | 2026-04-27 | GUI 視窗版（Tkinter） |
| v0.1 | 2026-04-27 | 初版 CLI |

---

## License

MIT License
