# EPUB / PDF 轉換器 — 系統規劃文件

**版本**：v1.0  
**日期**：2026-04-29  
**開發語言**：Python 3.13  
**主程式**：`C:\Zclaude\epub_to_pdf_gui.py`  
**啟動腳本**：`C:\Zclaude\開啟EPUB轉換器.bat`  
**預設輸出資料夾**：`C:\Zepub`

---

## 一、功能清單

### 1. EPUB → PDF 轉換
- 主引擎：**Calibre ebook-convert**（品質最佳，嵌入 Microsoft JhengHei 字型）
- 備援引擎：**reportlab 直接輸出**（Calibre 失敗時自動切換，保證 CJK 中文正確顯示）
- 支援 A4 紙張、上下左右邊距設定
- 字型嵌入：MicrosoftJhengHeiRegular / MicrosoftJhengHeiBold

### 2. EPUB → Markdown 轉換
- 純 Python 實作（ebooklib + BeautifulSoup）
- 支援標籤轉換：`<h1>`~`<h6>` → `#`~`######`
- 支援：段落、粗體、斜體、超連結、圖片、清單、表格、程式碼區塊、引用區塊
- 章節間自動插入分隔線 `---`
- 輸出 UTF-8 編碼 `.md` 檔

### 3. EPUB → PDF + Markdown（同時輸出）
- 一次轉換同時產出 `.pdf` 與 `.md` 兩個檔案

### 4. PDF → EPUB 轉換
- 主引擎：**Calibre ebook-convert**（含 `--enable-heuristics` 啟發式結構偵測）
- 備援引擎：**PyMuPDF + ebooklib**（逐頁抽取文字，組裝標準 EPUB3）
- 自動偵測輸入檔案副檔名（`.pdf`）→ 自動套用此模式，無需手動選格式

### 5. 批次轉換
- 支援同時加入多個 EPUB / PDF 檔案
- 支援掃描整個資料夾（含子資料夾）
- 獨立背景執行緒，轉換期間 GUI 不凍結

### 6. 拖放支援
- 支援直接將 `.epub` / `.pdf` 拖入檔案清單（需安裝 `tkinterdnd2`）
- 支援拖入資料夾（自動遞迴掃描）

### 7. 進度顯示
- 進度條：轉換中顯示滾動動畫（indeterminate），完成後顯示 100%
- 進度文字：`已完成 X%`、`N / 總數 — 檔名`
- 每列狀態圖示：⏳待轉換 / ⚙️轉換中 / ✅成功 / ❌失敗

### 8. 輸出資料夾管理
- 預設輸出資料夾：`C:\Zepub`（自動建立）
- 支援手動瀏覽選擇其他資料夾
- 「開啟輸出資料夾」快捷按鈕

### 9. 訊息記錄（Log）
- 顯示每個步驟的詳細轉換訊息
- 顏色分類：綠色（成功）、紅色（失敗）、藍色（資訊）、灰色（分隔）
- 顯示 Calibre 子進程輸出（不跳出黑色視窗）

---

## 二、系統架構

```
epub_to_pdf_gui.py
│
├── 轉換引擎層
│   ├── _convert_to_pdf()          EPUB → PDF 入口
│   │   ├── _convert_with_calibre()    主引擎（Calibre）
│   │   └── _convert_with_reportlab()  備援引擎（reportlab + CJK 字型）
│   │
│   ├── _convert_to_md()           EPUB → Markdown
│   │   └── _elem_to_md()              遞迴 HTML→MD 轉換器
│   │
│   └── _convert_pdf_to_epub()     PDF → EPUB 入口
│       ├── _calibre_run()             Calibre 子進程（CREATE_NO_WINDOW）
│       └── _pdf_to_epub_python()      備援（PyMuPDF + ebooklib）
│
├── 字型層
│   └── _register_cjk_font()       向 reportlab 註冊 TTC 字型
│       候選：msjh.ttc / msyh.ttc / simsun.ttc / mingliu.ttc
│
└── GUI 層（Tkinter + tkinterdnd2）
    ├── App.__init__()             視窗初始化
    ├── _build_left()              EPUB/PDF 檔案清單（Treeview）
    ├── _build_right()             設定面板（資料夾、格式、進度、Log）
    ├── _worker()                  背景轉換執行緒
    └── _on_done()                 完成後 UI 更新
```

---

## 三、引擎優先順序

| 轉換方向 | 主引擎 | 備援引擎 |
|----------|--------|----------|
| EPUB → PDF | Calibre ebook-convert | reportlab + msjh.ttc |
| EPUB → MD | BeautifulSoup 遞迴轉換 | — |
| PDF → EPUB | Calibre ebook-convert | PyMuPDF + ebooklib |

---

## 四、依賴套件

### Python 套件
| 套件 | 用途 |
|------|------|
| `tkinter` | GUI 框架（內建） |
| `tkinterdnd2` | 拖放支援 |
| `ebooklib` | EPUB 讀取 / 寫入 |
| `beautifulsoup4` | HTML 解析 |
| `lxml` | HTML/XML 解析器 |
| `reportlab` | PDF 直接生成（備援引擎） |
| `pillow` | 圖片處理 |
| `pymupdf` | PDF 文字抽取（PDF→EPUB 備援） |

### 外部程式
| 程式 | 路徑 | 用途 |
|------|------|------|
| Calibre | `C:\Program Files\Calibre2\ebook-convert.exe` | 主要轉換引擎 |

### 系統字型（CJK 備援引擎使用）
| 字型檔 | 字型名稱 | 優先順序 |
|--------|----------|----------|
| `C:\Windows\Fonts\msjh.ttc` | Microsoft JhengHei | 1 |
| `C:\Windows\Fonts\msyh.ttc` | Microsoft YaHei | 2 |
| `C:\Windows\Fonts\simsun.ttc` | SimSun | 3 |
| `C:\Windows\Fonts\mingliu.ttc` | MingLiU | 4 |

---

## 五、檔案結構

```
C:\Zclaude\
├── epub_to_pdf_gui.py          主程式
├── epub_to_pdf.py              CLI 版（舊版，已不維護）
├── 開啟EPUB轉換器.bat           啟動腳本（雙擊執行）
└── EPUB_轉換器_系統規劃文件.md  本文件

C:\Zepub\                       預設輸出資料夾
```

---

## 六、輸出格式說明

| 格式選項 | 輸入 | 輸出 |
|----------|------|------|
| PDF 文件 | .epub | .pdf |
| Markdown (.md) | .epub | .md |
| PDF + Markdown | .epub | .pdf + .md |
| 自動（PDF 輸入）| .pdf | .epub |

---

## 七、已知限制

1. **Calibre webkit 逾時**：部分含大量 JavaScript 的 EPUB 會觸發 Calibre 60 秒逾時，自動切換備援引擎（reportlab）。
2. **備援引擎格式**：reportlab 備援引擎保留段落結構與標題層級，但不保留原始 CSS 樣式（顏色、字距等）。
3. **PDF→EPUB 圖片**：Calibre 引擎可保留圖片；PyMuPDF 備援引擎目前僅轉換文字內容。
4. **SVG 圖片**：xhtml2pdf / reportlab 不支援 SVG，SVG 圖片會被略過。

---

## 八、測試紀錄

| 測試案例 | 輸入 | 輸出 | 結果 | 大小 |
|----------|------|------|------|------|
| 一般 EPUB → PDF | 矽谷思維.epub | .pdf | ✅ Calibre | 8,500 KB |
| 含 JS EPUB → PDF | 試錯策略.epub | .pdf | ✅ reportlab 備援 | 3,155 KB |
| EPUB → MD | 1010490531.epub | .md | ✅ 54 章節 | 795 KB |
| EPUB → PDF | 1010490531.epub | .pdf | ✅ Calibre | 4,962 KB |
| PDF → EPUB | test_output.pdf | .epub | ✅ Calibre | 2,008 KB |

---

## 九、版本歷程

| 版本 | 日期 | 變更說明 |
|------|------|----------|
| v0.1 | 2026-04-27 | 初版 CLI（epub_to_pdf.py） |
| v0.2 | 2026-04-27 | GUI 視窗版（Tkinter + tkinterdnd2） |
| v0.3 | 2026-04-27 | 加入 Calibre 主引擎 + reportlab 備援 |
| v0.4 | 2026-04-28 | 修正 CJK 字型（改用 reportlab 直接輸出，取代 xhtml2pdf） |
| v0.5 | 2026-04-28 | 進度條改為 indeterminate 動畫模式 |
| v1.0 | 2026-04-29 | 新增 Markdown 輸出、PDF→EPUB 轉換、預設輸出至 C:\Zepub、隱藏 Calibre 子視窗 |
| v1.1 | 2026-04-30 | 修正批次轉換 bug：worker 執行緒在首個檔案完成後因 `epub_path` 未定義崩潰，改用 `src_path.name` |
