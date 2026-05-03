"""
epub_to_pdf_gui.py  —  EPUB → PDF / Markdown 視窗轉換程式
=========================================================
引擎優先順序（PDF）：
  1. Calibre ebook-convert（首選，中文字型最佳）
  2. reportlab 直接輸出（備援，保證 CJK 正確顯示）

Markdown 輸出：
  ebooklib + BeautifulSoup 遞迴轉換 HTML→MD（純 Python，無需額外套件）

依賴：
    pip install tkinterdnd2 ebooklib beautifulsoup4 lxml pillow reportlab
    # 若需 Calibre 引擎，請另外安裝 Calibre

執行：
    python epub_to_pdf_gui.py
"""

from __future__ import annotations
import os, re, sys, base64, threading, subprocess, shutil
from pathlib import Path
from urllib.parse import unquote

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════════
#  常數與路徑
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_OUT_DIR = Path(r"C:\Zepub")
DEFAULT_OUT_DIR.mkdir(parents=True, exist_ok=True)

_CALIBRE_CANDIDATES = [
    r"C:\Program Files\Calibre2\ebook-convert.exe",
    r"C:\Program Files (x86)\Calibre2\ebook-convert.exe",
]

def _find_calibre() -> str | None:
    for p in _CALIBRE_CANDIDATES:
        if Path(p).exists():
            return p
    return shutil.which("ebook-convert")

CALIBRE_PATH = _find_calibre()


# ═══════════════════════════════════════════════════════════════════════════════
#  Markdown 轉換核心
# ═══════════════════════════════════════════════════════════════════════════════

def _elem_to_md(el) -> str:
    """遞迴將 BeautifulSoup element 轉為 Markdown 字串。"""
    from bs4 import NavigableString, Tag

    if isinstance(el, NavigableString):
        return str(el)
    if not isinstance(el, Tag):
        return ""

    name = (el.name or "").lower()
    kids = "".join(_elem_to_md(c) for c in el.children)

    if name in ("script", "style", "head"):
        return ""
    if name == "h1":
        return f"\n# {kids.strip()}\n\n"
    if name == "h2":
        return f"\n## {kids.strip()}\n\n"
    if name == "h3":
        return f"\n### {kids.strip()}\n\n"
    if name == "h4":
        return f"\n#### {kids.strip()}\n\n"
    if name in ("h5", "h6"):
        return f"\n##### {kids.strip()}\n\n"
    if name == "p":
        t = kids.strip()
        return f"{t}\n\n" if t else ""
    if name in ("strong", "b"):
        return f"**{kids}**"
    if name in ("em", "i"):
        return f"*{kids}*"
    if name == "code":
        return f"`{kids}`"
    if name == "pre":
        return f"\n```\n{kids.strip()}\n```\n\n"
    if name == "blockquote":
        lines = kids.strip().splitlines()
        return "\n".join(f"> {l}" for l in lines) + "\n\n"
    if name == "a":
        href = el.get("href", "")
        text = kids.strip() or href
        return f"[{text}]({href})"
    if name == "img":
        alt = el.get("alt", "")
        src = el.get("src", "")
        if src.startswith("data:"):
            src = ""
        return f"![{alt}]({src})\n\n" if src else ""
    if name == "ul":
        parts = []
        for li in el.find_all("li", recursive=False):
            parts.append(f"- {_elem_to_md(li).strip()}")
        return "\n".join(parts) + "\n\n" if parts else kids
    if name == "ol":
        parts = []
        for i, li in enumerate(el.find_all("li", recursive=False), 1):
            parts.append(f"{i}. {_elem_to_md(li).strip()}")
        return "\n".join(parts) + "\n\n" if parts else kids
    if name == "li":
        return kids
    if name == "br":
        return "\n"
    if name == "hr":
        return "\n---\n\n"
    if name == "table":
        rows = el.find_all("tr")
        if not rows:
            return kids
        result = []
        for ri, row in enumerate(rows):
            cells = row.find_all(["td", "th"])
            row_md = " | ".join(_elem_to_md(c).strip() for c in cells)
            result.append(f"| {row_md} |")
            if ri == 0:
                result.append("|" + "|".join(" --- " for _ in cells) + "|")
        return "\n".join(result) + "\n\n"
    # div / span / section / body / html / etc.
    return kids


def _convert_to_md(epub_path: Path, md_path: Path, log) -> None:
    """將 EPUB 轉換為 Markdown 檔案（純 Python）。"""
    import ebooklib, warnings
    from ebooklib import epub
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

    log("  轉換為 Markdown …")
    book = epub.read_epub(str(epub_path), options={"ignore_ncx": True})

    chapters: list[str] = []
    for item_id, _ in book.spine:
        item = book.get_item_with_id(item_id)
        if item and item.get_type() == ebooklib.ITEM_DOCUMENT:
            raw = item.get_content()
            if raw:
                chapters.append(raw.decode("utf-8", errors="replace"))
    if not chapters:
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            raw = item.get_content()
            if raw:
                chapters.append(raw.decode("utf-8", errors="replace"))

    log(f"  共 {len(chapters)} 個章節")
    title = book.title or epub_path.stem

    parts = [f"# {title}\n\n"]
    for i, html in enumerate(chapters):
        soup = BeautifulSoup(html, "lxml")
        body = soup.find("body") or soup
        md = _elem_to_md(body).strip()
        if md:
            if i > 0:
                parts.append("\n\n---\n\n")
            parts.append(md)

    # 清理多餘空行
    content = "\n".join(parts)
    content = re.sub(r"\n{4,}", "\n\n\n", content)

    md_path.write_text(content, encoding="utf-8")
    kb = md_path.stat().st_size // 1024
    log(f"  完成！{md_path.name}  ({kb:,} KB)")


# ═══════════════════════════════════════════════════════════════════════════════
#  PDF → EPUB 轉換核心
# ═══════════════════════════════════════════════════════════════════════════════

def _pdf_to_epub_python(pdf_path: Path, epub_path: Path, log) -> None:
    """純 Python 備援：PyMuPDF 抽文字 → ebooklib 組 EPUB。"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("找不到 PyMuPDF，請執行 pip install pymupdf，或安裝 Calibre")

    import ebooklib
    from ebooklib import epub as epublib

    log("  純 Python 備援引擎（PyMuPDF → ebooklib）…")
    doc  = fitz.open(str(pdf_path))
    book = epublib.EpubBook()
    book.set_title(pdf_path.stem)
    book.set_language("zh")

    spine_items = []
    toc         = []

    for pn in range(len(doc)):
        page = doc[pn]
        text = page.get_text("text").strip()
        if not text:
            continue
        # 每頁做一個 HTML chapter
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines   = escaped.splitlines()
        html_body = "\n".join(
            f"<p>{l}</p>" if l.strip() else "<br/>" for l in lines
        )
        html = (
            "<?xml version='1.0' encoding='utf-8'?>"
            "<!DOCTYPE html>"
            "<html xmlns='http://www.w3.org/1999/xhtml'><head>"
            f"<title>Page {pn+1}</title>"
            "<meta charset='utf-8'/></head><body>"
            f"<h2>第 {pn+1} 頁</h2>"
            f"{html_body}</body></html>"
        )
        c = epublib.EpubHtml(
            title=f"Page {pn+1}",
            file_name=f"page_{pn+1:04d}.xhtml",
            lang="zh",
        )
        c.content = html.encode("utf-8")
        book.add_item(c)
        spine_items.append(c)
        toc.append(epublib.Link(c.file_name, f"第 {pn+1} 頁", f"page{pn+1}"))

    book.toc   = toc
    book.spine = ["nav"] + spine_items
    book.add_item(epublib.EpubNcx())
    book.add_item(epublib.EpubNav())
    epublib.write_epub(str(epub_path), book)

    kb = epub_path.stat().st_size // 1024
    log(f"  完成！{epub_path.name}  ({kb:,} KB)")


def _convert_pdf_to_epub(pdf_path: Path, epub_path: Path, log) -> None:
    """PDF → EPUB：優先 Calibre，備援 PyMuPDF + ebooklib。"""
    if CALIBRE_PATH:
        log("  引擎：Calibre（備援：PyMuPDF + ebooklib）")
        opts = ["--enable-heuristics", "--language", "zh"]
        log("  嘗試 1：Calibre PDF → EPUB …")
        rc = _calibre_run(pdf_path, epub_path, opts, log)
        if rc == 0 and epub_path.exists():
            kb = epub_path.stat().st_size // 1024
            log(f"  完成！{epub_path.name}  ({kb:,} KB)")
            return
        log("  嘗試 1 失敗，改用純 Python 備援 …")
        if epub_path.exists():
            epub_path.unlink()

    _pdf_to_epub_python(pdf_path, epub_path, log)


# ═══════════════════════════════════════════════════════════════════════════════
#  EPUB → PDF / MD 轉換核心
# ═══════════════════════════════════════════════════════════════════════════════

def _calibre_run(src: Path, dst: Path, extra_args: list, log) -> int:
    cmd = [CALIBRE_PATH, str(src), str(dst)] + extra_args
    log(f"    cmd: {' '.join(repr(c) for c in cmd[:3])}")
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            log(f"    {line}")
    return proc.returncode


def _register_cjk_font(log) -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    cjk_candidates = [
        (r"C:\Windows\Fonts\msjh.ttc",    0, "MSJhengHei"),
        (r"C:\Windows\Fonts\msyh.ttc",    0, "MSYaHei"),
        (r"C:\Windows\Fonts\simsun.ttc",  0, "SimSun"),
        (r"C:\Windows\Fonts\mingliu.ttc", 0, "MingLiU"),
    ]
    for path, idx, name in cjk_candidates:
        if not Path(path).exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont(name, path, subfontIndex=idx))
            log(f"  CJK 字型：{path}（{name}）")
            return name
        except Exception as e:
            log(f"  字型載入失敗 {path}：{e}")
    return ""


def _convert_with_reportlab(epub_path: Path, pdf_path: Path, log) -> None:
    """備用引擎：ebooklib + reportlab 直接輸出（保證 CJK 正確顯示）。"""
    import ebooklib, warnings
    from ebooklib import epub
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image as RLImage,
    )
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

    font_name = _register_cjk_font(log)
    if not font_name:
        raise RuntimeError("找不到 CJK 字型（msjh.ttc / msyh.ttc / simsun.ttc），無法轉換")

    log("  純 reportlab 備援引擎啟動 …")
    log(f"  使用字型：{font_name}")
    log("  讀取 EPUB …")
    book = epub.read_epub(str(epub_path), options={"ignore_ncx": True})

    images: dict[str, bytes] = {}
    for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
        data = item.get_content()
        images[item.get_name()] = data
        images[os.path.basename(item.get_name())] = data

    chapters: list[str] = []
    for item_id, _ in book.spine:
        item = book.get_item_with_id(item_id)
        if item and item.get_type() == ebooklib.ITEM_DOCUMENT:
            raw = item.get_content()
            if raw:
                chapters.append(raw.decode("utf-8", errors="replace"))
    if not chapters:
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            raw = item.get_content()
            if raw:
                chapters.append(raw.decode("utf-8", errors="replace"))

    log(f"  共 {len(chapters)} 個章節，建立 PDF …")
    title = book.title or epub_path.stem

    def ps(name, size, leading, sb=0, sa=4, align=0):
        return ParagraphStyle(name, fontName=font_name, fontSize=size,
                               leading=leading, spaceBefore=sb, spaceAfter=sa,
                               alignment=align, wordWrap="CJK")

    S = {
        "title": ps("title", 20, 28, sb=0,  sa=16, align=1),
        "h1":    ps("h1",    18, 26, sb=14, sa=8),
        "h2":    ps("h2",    15, 22, sb=10, sa=6),
        "h3":    ps("h3",    13, 20, sb=8,  sa=4),
        "h4":    ps("h4",    12, 19, sb=6,  sa=4),
        "h5":    ps("h5",    11, 18, sb=4,  sa=4),
        "h6":    ps("h6",    11, 18, sb=4,  sa=4),
        "p":     ps("p",     11, 18, sb=0,  sa=4),
    }
    TAG_S = {t: S.get(t, S["p"]) for t in ("h1","h2","h3","h4","h5","h6","p")}
    PAGE_W = A4[0] - 5 * cm          # 可用寬度
    PAGE_H = A4[1] - 8 * cm          # 可用高度（保守值，避免超出 frame）

    def esc(t: str) -> str:
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4,
                             leftMargin=2.5*cm, rightMargin=2.5*cm,
                             topMargin=2*cm,    bottomMargin=2*cm)
    story: list = [Paragraph(esc(title), S["title"]), Spacer(1, 0.5*cm)]

    for ci, html in enumerate(chapters):
        if ci > 0:
            story.append(PageBreak())
        soup = BeautifulSoup(html, "lxml")
        body = soup.find("body") or soup
        for el in body.find_all(["h1","h2","h3","h4","h5","h6","p","img"]):
            if el.name == "img":
                src = el.get("src", "")
                src_d = unquote(src)
                img_data = images.get(src_d) or images.get(os.path.basename(src_d))
                if img_data:
                    try:
                        ri = RLImage(BytesIO(img_data))
                        w, h = ri.drawWidth, ri.drawHeight
                        # 等比縮放，確保同時符合寬與高限制
                        scale = min(PAGE_W / w, PAGE_H / h, 1.0)
                        ri.drawWidth  = w * scale
                        ri.drawHeight = h * scale
                        story.append(ri)
                        story.append(Spacer(1, 0.3*cm))
                    except Exception:
                        pass
            else:
                text = el.get_text(" ", strip=True)
                if text:
                    story.append(Paragraph(esc(text), TAG_S[el.name]))

    doc.build(story)
    kb = pdf_path.stat().st_size // 1024
    log(f"  完成！{pdf_path.name}  ({kb:,} KB)")


def _convert_with_calibre(epub_path: Path, pdf_path: Path, log) -> None:
    log("  引擎：Calibre（備援：純 Python reportlab）")
    pdf_opts = [
        "--paper-size", "a4",
        "--margin-top", "20", "--margin-bottom", "20",
        "--margin-left", "25", "--margin-right", "25",
        "--pdf-serif-family", "Microsoft JhengHei",
        "--pdf-sans-family",  "Microsoft JhengHei",
        "--pdf-default-font-size", "12",
        "--base-font-size", "12",
    ]
    log("  嘗試 1：Calibre EPUB → PDF …")
    rc = _calibre_run(epub_path, pdf_path, pdf_opts, log)
    if rc == 0 and pdf_path.exists():
        kb = pdf_path.stat().st_size // 1024
        log(f"  完成！{pdf_path.name}  ({kb:,} KB)")
        return

    log("  嘗試 1 失敗，改用純 Python 備援（reportlab）…")
    if pdf_path.exists():
        pdf_path.unlink()
    _convert_with_reportlab(epub_path, pdf_path, log)


def _convert_to_pdf(epub_path: Path, pdf_path: Path, log) -> None:
    if CALIBRE_PATH:
        _convert_with_calibre(epub_path, pdf_path, log)
    else:
        _convert_with_reportlab(epub_path, pdf_path, log)


# ═══════════════════════════════════════════════════════════════════════════════
#  GUI
# ═══════════════════════════════════════════════════════════════════════════════

CLR = {
    "blue":      "#2563EB",
    "blue_dark": "#1D4ED8",
    "blue_dim":  "#93C5FD",
    "green":     "#16A34A",
    "red":       "#DC2626",
    "orange":    "#D97706",
    "bg":        "#F8FAFC",
    "panel":     "#FFFFFF",
    "border":    "#E2E8F0",
    "text":      "#1E293B",
    "muted":     "#64748B",
    "log_bg":    "#0F172A",
    "log_fg":    "#E2E8F0",
    "header_bg": "#1E3A5F",
}

STATUS_ICON = {
    "待轉換": ("⏳", CLR["muted"]),
    "轉換中": ("⚙️",  CLR["blue"]),
    "成功":   ("✅", CLR["green"]),
    "失敗":   ("❌", CLR["red"]),
}


class FileRow:
    __slots__ = ("path", "status", "msg")

    def __init__(self, path: str):
        self.path   = path
        self.status = "待轉換"
        self.msg    = ""


class App(TkinterDnD.Tk if _DND_AVAILABLE else tk.Tk):
    # ── 初始化 ────────────────────────────────────────────────────────────────
    def __init__(self):
        super().__init__()
        self.title("EPUB 轉換器")
        self.configure(bg=CLR["bg"])
        self.minsize(820, 540)

        self._rows:      list[FileRow] = []
        self._converting = False
        self._output_dir = tk.StringVar(value=str(DEFAULT_OUT_DIR))
        self._fmt        = tk.StringVar(value="pdf")   # pdf | md | both

        self._build_ui()
        self._center(960, 640)
        self._log("程式就緒。新增 EPUB 後按「開始轉換」。")
        self._log(f"預設輸出資料夾：{DEFAULT_OUT_DIR}")
        if _DND_AVAILABLE:
            self._log("✓ 支援拖放：可直接將 .epub 拖入左側清單。")

    # ── 版面 ──────────────────────────────────────────────────────────────────
    def _build_ui(self):
        hdr = tk.Frame(self, bg=CLR["header_bg"], height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="EPUB / PDF 轉換器",
                 bg=CLR["header_bg"], fg="white",
                 font=("Microsoft JhengHei UI", 14, "bold")
                 ).pack(side="left", padx=20, pady=14)
        engine = "引擎：Calibre ✓" if CALIBRE_PATH else "引擎：reportlab（備用）"
        tk.Label(hdr, text=f"EPUB→PDF/MD　PDF→EPUB　支援批次・中文排版　{engine}",
                 bg=CLR["header_bg"], fg=CLR["blue_dim"],
                 font=("Microsoft JhengHei UI", 9)
                 ).pack(side="left", pady=14)

        body = tk.Frame(self, bg=CLR["bg"])
        body.pack(fill="both", expand=True, padx=14, pady=10)
        self._build_left(body)
        self._build_right(body)

        sbar = tk.Frame(self, bg=CLR["border"], height=26)
        sbar.pack(fill="x", side="bottom")
        sbar.pack_propagate(False)
        self._status_var = tk.StringVar(value="就緒")
        tk.Label(sbar, textvariable=self._status_var,
                 bg=CLR["border"], fg=CLR["muted"],
                 font=("Microsoft JhengHei UI", 8), anchor="w"
                 ).pack(side="left", padx=10)

    def _build_left(self, parent):
        frame = tk.LabelFrame(parent, text="  輸入 EPUB / PDF 清單  ",
                              bg=CLR["panel"], fg=CLR["text"],
                              font=("Microsoft JhengHei UI", 10),
                              relief="flat", bd=1,
                              highlightthickness=1,
                              highlightbackground=CLR["border"])
        frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        cols = ("status", "name", "path")
        tv_frame = tk.Frame(frame, bg=CLR["panel"])
        tv_frame.pack(fill="both", expand=True, padx=8, pady=(6, 4))

        style = ttk.Style()
        style.configure("File.Treeview",
                         background=CLR["panel"], fieldbackground=CLR["panel"],
                         foreground=CLR["text"], rowheight=26,
                         font=("Microsoft JhengHei UI", 9))
        style.configure("File.Treeview.Heading",
                         background=CLR["border"], foreground=CLR["muted"],
                         font=("Microsoft JhengHei UI", 9, "bold"))
        style.map("File.Treeview",
                  background=[("selected", CLR["blue"])],
                  foreground=[("selected", "white")])

        sb_y = ttk.Scrollbar(tv_frame, orient="vertical")
        sb_x = ttk.Scrollbar(tv_frame, orient="horizontal")
        self._tv = ttk.Treeview(tv_frame, columns=cols, show="headings",
                                 style="File.Treeview",
                                 yscrollcommand=sb_y.set,
                                 xscrollcommand=sb_x.set,
                                 selectmode="extended")
        sb_y.config(command=self._tv.yview)
        sb_x.config(command=self._tv.xview)

        self._tv.heading("status", text="狀態",    anchor="center")
        self._tv.heading("name",   text="檔案名稱",anchor="w")
        self._tv.heading("path",   text="完整路徑", anchor="w")
        self._tv.column("status", width=70,  minwidth=60,  stretch=False, anchor="center")
        self._tv.column("name",   width=200, minwidth=120, stretch=False)
        self._tv.column("path",   width=400, minwidth=200, stretch=True)

        for key, (icon, color) in STATUS_ICON.items():
            self._tv.tag_configure(key, foreground=color)

        self._tv.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")
        sb_x.grid(row=1, column=0, sticky="ew")
        tv_frame.rowconfigure(0, weight=1)
        tv_frame.columnconfigure(0, weight=1)

        if _DND_AVAILABLE:
            self._tv.drop_target_register(DND_FILES)
            self._tv.dnd_bind("<<Drop>>", self._on_drop)

        btn_bar = tk.Frame(frame, bg=CLR["panel"])
        btn_bar.pack(fill="x", padx=8, pady=(0, 8))
        self._flat_btn(btn_bar, "＋ 新增檔案",  self._add_files,  CLR["blue"]).pack(side="left", padx=(0,6))
        self._flat_btn(btn_bar, "新增資料夾",   self._add_folder, CLR["muted"]).pack(side="left", padx=(0,6))
        self._flat_btn(btn_bar, "－ 移除選取",  self._remove_sel, CLR["muted"]).pack(side="left", padx=(0,6))
        self._flat_btn(btn_bar, "清空清單",     self._clear_all,  CLR["red"]).pack(side="left")
        self._count_lbl = tk.Label(btn_bar, text="共 0 個檔案",
                                    bg=CLR["panel"], fg=CLR["muted"],
                                    font=("Microsoft JhengHei UI", 9))
        self._count_lbl.pack(side="right")

    def _build_right(self, parent):
        right = tk.Frame(parent, bg=CLR["bg"], width=290)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        # 輸出資料夾
        self._panel(right, "輸出資料夾", self._build_output_section)

        # 輸出格式
        fmt_p = self._panel(right, "輸出格式", None)
        for text, val in [("PDF 文件", "pdf"), ("Markdown (.md)", "md"), ("PDF + Markdown", "both")]:
            tk.Radiobutton(fmt_p, text=text, variable=self._fmt, value=val,
                           bg=CLR["panel"], fg=CLR["text"],
                           activebackground=CLR["panel"],
                           font=("Microsoft JhengHei UI", 9),
                           selectcolor=CLR["panel"]
                           ).pack(anchor="w")

        # 轉換進度
        prog_p = self._panel(right, "轉換進度", None)
        self._prog_label = tk.Label(prog_p, text="尚未開始",
                                     bg=CLR["panel"], fg=CLR["muted"],
                                     font=("Microsoft JhengHei UI", 9), anchor="w")
        self._prog_label.pack(fill="x", pady=(0, 4))
        style = ttk.Style()
        style.configure("Blue.Horizontal.TProgressbar",
                         troughcolor=CLR["border"],
                         background=CLR["blue"], thickness=12)
        self._progress = ttk.Progressbar(prog_p,
                                          style="Blue.Horizontal.TProgressbar",
                                          mode="determinate")
        self._progress.pack(fill="x")
        self._prog_pct = tk.Label(prog_p, text="",
                                   bg=CLR["panel"], fg=CLR["muted"],
                                   font=("Microsoft JhengHei UI", 8), anchor="e")
        self._prog_pct.pack(fill="x")

        # 開始轉換
        self._convert_btn = tk.Button(
            right, text="▶  開始轉換",
            bg=CLR["blue"], fg="white",
            activebackground=CLR["blue_dark"], activeforeground="white",
            font=("Microsoft JhengHei UI", 13, "bold"),
            relief="flat", cursor="hand2", height=2,
            command=self._start_convert,
        )
        self._convert_btn.pack(fill="x", pady=(10, 0))

        self._open_dir_btn = tk.Button(
            right, text="📂  開啟輸出資料夾",
            bg=CLR["border"], fg=CLR["text"],
            activebackground="#CBD5E1",
            font=("Microsoft JhengHei UI", 10),
            relief="flat", cursor="hand2",
            command=self._open_output_dir,
        )
        self._open_dir_btn.pack(fill="x", pady=(6, 0))

        log_p = self._panel(right, "訊息記錄", None, expand=True)
        log_frame = tk.Frame(log_p, bg=CLR["log_bg"])
        log_frame.pack(fill="both", expand=True)
        log_sb = ttk.Scrollbar(log_frame)
        log_sb.pack(side="right", fill="y")
        self._log_box = tk.Text(log_frame, yscrollcommand=log_sb.set,
                                 bg=CLR["log_bg"], fg=CLR["log_fg"],
                                 font=("Consolas", 8), relief="flat",
                                 state="disabled", wrap="word",
                                 insertbackground=CLR["log_fg"])
        self._log_box.pack(fill="both", expand=True, padx=4, pady=4)
        log_sb.config(command=self._log_box.yview)
        self._log_box.tag_configure("ok",   foreground="#4ADE80")
        self._log_box.tag_configure("err",  foreground="#F87171")
        self._log_box.tag_configure("info", foreground="#93C5FD")
        self._log_box.tag_configure("dim",  foreground="#64748B")

    def _build_output_section(self, parent):
        tk.Entry(parent, textvariable=self._output_dir,
                 font=("Consolas", 8), relief="solid", bd=1,
                 bg=CLR["bg"]
                 ).pack(fill="x", pady=(0, 6))
        self._flat_btn(parent, "瀏覽…", self._browse_output, CLR["muted"]).pack(anchor="w")

    # ── 輔助 UI ───────────────────────────────────────────────────────────────
    def _flat_btn(self, parent, text, cmd, color=CLR["muted"], **kw):
        return tk.Button(parent, text=text, command=cmd,
                         bg=color, fg="white",
                         activebackground=color, activeforeground="white",
                         font=("Microsoft JhengHei UI", 9),
                         relief="flat", cursor="hand2",
                         padx=10, pady=4, **kw)

    def _panel(self, parent, title, builder, expand=False):
        outer = tk.LabelFrame(parent, text=f"  {title}  ",
                              bg=CLR["panel"], fg=CLR["muted"],
                              font=("Microsoft JhengHei UI", 9),
                              relief="flat", bd=1,
                              highlightthickness=1,
                              highlightbackground=CLR["border"])
        outer.pack(fill="both" if expand else "x",
                   expand=expand, pady=(0, 8))
        inner = tk.Frame(outer, bg=CLR["panel"])
        inner.pack(fill="both", expand=expand, padx=8, pady=6)
        if builder:
            builder(inner)
        return inner

    def _center(self, w: int, h: int):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ── 清單操作 ──────────────────────────────────────────────────────────────
    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="選擇 EPUB 或 PDF 檔案",
            filetypes=[
                ("電子書 / PDF", "*.epub *.pdf"),
                ("EPUB 電子書", "*.epub"),
                ("PDF 文件",    "*.pdf"),
                ("所有檔案",    "*.*"),
            ],
        )
        for p in paths:
            self._insert_row(p)

    def _add_folder(self):
        d = filedialog.askdirectory(title="選擇含有 EPUB / PDF 的資料夾")
        if not d:
            return
        found = [p for p in Path(d).rglob("*")
                 if p.suffix.lower() in (".epub", ".pdf")]
        for p in found:
            self._insert_row(str(p))
        if found:
            self._log(f"從資料夾加入 {len(found)} 個檔案", "info")

    def _on_drop(self, event):
        paths = self.tk.splitlist(event.data)
        added = 0
        for p in paths:
            p = p.strip("{}")
            if Path(p).is_dir():
                for ep in Path(p).rglob("*"):
                    if ep.suffix.lower() in (".epub", ".pdf"):
                        self._insert_row(str(ep)); added += 1
            elif Path(p).suffix.lower() in (".epub", ".pdf"):
                self._insert_row(p); added += 1
        if added:
            self._log(f"拖放加入 {added} 個檔案", "info")

    def _insert_row(self, path: str):
        if path in {r.path for r in self._rows}:
            return
        row = FileRow(path)
        self._rows.append(row)
        icon, _ = STATUS_ICON[row.status]
        self._tv.insert("", "end", iid=path,
                         values=(f"{icon} {row.status}", Path(path).name, path),
                         tags=(row.status,))
        self._refresh_count()

    def _remove_sel(self):
        if self._converting:
            return
        for iid in self._tv.selection():
            self._tv.delete(iid)
            self._rows = [r for r in self._rows if r.path != iid]
        self._refresh_count()

    def _clear_all(self):
        if self._converting:
            return
        self._tv.delete(*self._tv.get_children())
        self._rows.clear()
        self._refresh_count()

    def _refresh_count(self):
        n = len(self._rows)
        self._count_lbl.config(text=f"共 {n} 個檔案")
        self._status_var.set(f"清單中共 {n} 個 EPUB 待轉換" if n else "就緒")

    def _update_row_status(self, path: str, status: str):
        icon, _ = STATUS_ICON[status]
        try:
            self._tv.item(path,
                           values=(f"{icon} {status}", Path(path).name, path),
                           tags=(status,))
        except tk.TclError:
            pass

    # ── 輸出資料夾 ────────────────────────────────────────────────────────────
    def _browse_output(self):
        d = filedialog.askdirectory(title="選擇輸出資料夾",
                                     initialdir=self._output_dir.get())
        if d:
            self._output_dir.set(d)

    def _open_output_dir(self):
        d = self._output_dir.get()
        if Path(d).is_dir():
            subprocess.Popen(["explorer", os.path.normpath(d)])
        else:
            messagebox.showerror("找不到資料夾", f"路徑不存在：\n{d}")

    # ── 訊息記錄 ──────────────────────────────────────────────────────────────
    def _log(self, msg: str, tag: str = ""):
        self._log_box.configure(state="normal")
        if tag:
            self._log_box.insert("end", msg + "\n", tag)
        else:
            self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _log_t(self, msg: str, tag: str = ""):
        self.after(0, self._log, msg, tag)

    # ── 轉換流程 ──────────────────────────────────────────────────────────────
    def _start_convert(self):
        if self._converting:
            return
        rows = [r for r in self._rows if r.status in ("待轉換", "失敗")]
        if not rows:
            messagebox.showwarning("無待轉換項目",
                                    "清單中沒有「待轉換」或「失敗」的檔案。")
            return

        out_dir = self._output_dir.get().strip()
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        if not Path(out_dir).is_dir():
            messagebox.showerror("輸出資料夾錯誤", f"資料夾不存在：\n{out_dir}")
            return

        fmt = self._fmt.get()
        self._converting = True
        self._convert_btn.config(text="⏹  轉換中…", bg="#6B7280", state="disabled")
        self._total_rows = len(rows)
        self._progress.config(mode="indeterminate")
        self._progress.start(15)
        self._prog_label.config(text=f"0 / {len(rows)}")
        self._prog_pct.config(text="轉換中…")

        self._log(f"\n{'─'*42}", "dim")
        fmt_label = {"pdf": "PDF", "md": "Markdown", "both": "PDF + Markdown"}[fmt]
        self._log(f"開始批次轉換，共 {len(rows)} 個檔案", "info")
        self._log(f"EPUB 輸出格式：{fmt_label}　PDF 輸入 → 自動轉 EPUB", "info")

        threading.Thread(target=self._worker,
                          args=(rows, out_dir, fmt), daemon=True).start()

    def _worker(self, rows: list[FileRow], out_dir: str, fmt: str):
        success, failed = 0, []
        total = len(rows)

        for i, row in enumerate(rows):
            src_path = Path(row.path)
            stem     = src_path.stem
            ext      = src_path.suffix.lower()

            self._log_t(f"\n[{i+1}/{total}]  {src_path.name}", "info")
            self.after(0, self._update_row_status, row.path, "轉換中")
            row.status = "轉換中"

            try:
                if ext == ".pdf":
                    # PDF → EPUB（自動）
                    epub_out = Path(out_dir) / (stem + ".epub")
                    self._log_t("  模式：PDF → EPUB", "info")
                    _convert_pdf_to_epub(src_path, epub_out,
                                         lambda m: self._log_t(m))
                else:
                    # EPUB → PDF / MD / both
                    pdf_path = Path(out_dir) / (stem + ".pdf")
                    md_path  = Path(out_dir) / (stem + ".md")
                    if fmt in ("pdf", "both"):
                        _convert_to_pdf(src_path, pdf_path,
                                        lambda m: self._log_t(m))
                    if fmt in ("md", "both"):
                        _convert_to_md(src_path, md_path,
                                       lambda m: self._log_t(m))

                row.status = "成功"
                self.after(0, self._update_row_status, row.path, "成功")
                self._log_t("  ✅ 成功", "ok")
                success += 1
            except Exception as e:
                row.status = "失敗"
                row.msg    = str(e)
                self.after(0, self._update_row_status, row.path, "失敗")
                self._log_t(f"  ❌ 失敗：{e}", "err")
                failed.append(src_path.name)

            done = i + 1
            pct  = int(done / total * 100)
            self.after(0, self._tick, done, total, pct, src_path.name)

        self.after(0, self._on_done, success, failed, out_dir)

    def _tick(self, done: int, total: int, pct: int, name: str):
        self._prog_label.config(text=f"{done} / {total}  —  {name}")
        self._prog_pct.config(text=f"已完成 {pct}%")
        self._status_var.set(f"轉換中 {done}/{total}：{name}")

    def _on_done(self, success: int, failed: list[str], out_dir: str):
        self._converting = False
        self._convert_btn.config(text="▶  開始轉換",
                                  bg=CLR["blue"], state="normal")
        self._progress.stop()
        self._progress.config(mode="determinate")
        self._progress["maximum"] = 1
        self._progress["value"]   = 1
        self._prog_pct.config(text="100%")

        self._log(f"\n{'─'*42}", "dim")
        if failed:
            self._log(f"完成！成功 {success} 個，失敗 {len(failed)} 個", "err")
            self._log(f"失敗清單：{', '.join(failed)}", "err")
            self._status_var.set(f"完成！成功 {success} 個，失敗 {len(failed)} 個")
            messagebox.showwarning("部分失敗",
                f"成功 {success} 個\n失敗 {len(failed)} 個：\n" +
                "\n".join(failed))
        else:
            self._log(f"全部完成！{success} 個檔案轉換成功", "ok")
            self._status_var.set(f"全部完成！{success} 個檔案轉換成功")
            messagebox.showinfo("轉換完成",
                f"全部 {success} 個檔案轉換成功！\n\n輸出位置：\n{out_dir}")


# ═══════════════════════════════════════════════════════════════════════════════
#  進入點
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = App()
    app.mainloop()
