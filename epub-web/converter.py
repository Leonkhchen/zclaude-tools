"""
converter.py  —  EPUB / PDF 轉換引擎（無 GUI，支援 Windows + Linux）
=====================================================================
平台字型：
  Windows → C:\\Windows\\Fonts\\msjh.ttc  (Microsoft JhengHei)
  Linux   → /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc

引擎優先順序（EPUB → PDF）：
  1. Calibre ebook-convert
  2. reportlab 直接輸出（備援）

PDF → EPUB：
  1. Calibre
  2. PyMuPDF + ebooklib（備援）

EPUB → Markdown：
  ebooklib + BeautifulSoup（純 Python）
"""

from __future__ import annotations
import os, re, platform, subprocess, shutil
from pathlib import Path
from urllib.parse import unquote

# ── Calibre 路徑偵測 ──────────────────────────────────────────────────────────

_CALIBRE_CANDIDATES_WIN = [
    r"C:\Program Files\Calibre2\ebook-convert.exe",
    r"C:\Program Files (x86)\Calibre2\ebook-convert.exe",
]

def _find_calibre() -> str | None:
    if platform.system() == "Windows":
        for p in _CALIBRE_CANDIDATES_WIN:
            if Path(p).exists():
                return p
    return shutil.which("ebook-convert")

CALIBRE_PATH = _find_calibre()

# ── CJK 字型候選（依平台）────────────────────────────────────────────────────

def _cjk_candidates():
    if platform.system() == "Windows":
        return [
            (r"C:\Windows\Fonts\msjh.ttc",    0, "MSJhengHei"),
            (r"C:\Windows\Fonts\msyh.ttc",    0, "MSYaHei"),
            (r"C:\Windows\Fonts\simsun.ttc",  0, "SimSun"),
            (r"C:\Windows\Fonts\mingliu.ttc", 0, "MingLiU"),
        ]
    else:
        return [
            # WQY Micro Hei — TrueType 格式，reportlab 可用，含完整 CJK
            ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",        0, "WQYMicroHei"),
            # WQY Zen Hei（備用）
            ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",          0, "WQYZenHei"),
            # Noto CJK（opentype/CFF，reportlab 不支援，跳過）
            # DejaVu fallback（無 CJK 但不 crash）
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",        0, "DejaVuSans"),
        ]


# ═══════════════════════════════════════════════════════════════════════════════
#  共用輔助
# ═══════════════════════════════════════════════════════════════════════════════

def _calibre_run(src: Path, dst: Path, extra_args: list, log) -> int:
    """執行 ebook-convert，把 stdout/stderr 轉給 log callback。"""
    cmd = [CALIBRE_PATH, str(src), str(dst)] + extra_args

    kwargs = dict(
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )

    if platform.system() == "Windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        # Linux / Docker: 確保 Chromium sandbox 旗標正確設定
        env = dict(os.environ)
        env["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --disable-gpu"
        env["QT_QPA_PLATFORM"] = "offscreen"
        kwargs["env"] = env

        # 如果 xvfb-run 存在，用它包裝（提供虛擬 X display 給 QtWebEngine）
        xvfb = shutil.which("xvfb-run")
        if xvfb:
            cmd = [xvfb, "--auto-servernum", "--server-args=-screen 0 1024x768x24"] + cmd

    log(f"    cmd: {' '.join(repr(c) for c in cmd[:4] if not c.startswith('-'))}")
    proc = subprocess.run(cmd, **kwargs)
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            log(f"    {line}")
    return proc.returncode


def _register_cjk_font(log) -> str:
    """向 reportlab 登記 CJK 字型，回傳登記成功的字型名稱（空字串=失敗）。"""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for path, idx, name in _cjk_candidates():
        if not Path(path).exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont(name, path, subfontIndex=idx))
            log(f"  CJK 字型：{path}（{name}）")
            return name
        except Exception as e:
            log(f"  字型載入失敗 {path}：{e}")
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
#  Markdown 轉換核心
# ═══════════════════════════════════════════════════════════════════════════════

def _elem_to_md(el) -> str:
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
    return kids


def convert_to_md(epub_path: Path, md_path: Path, log) -> None:
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

    content = "\n".join(parts)
    content = re.sub(r"\n{4,}", "\n\n\n", content)

    md_path.write_text(content, encoding="utf-8")
    kb = md_path.stat().st_size // 1024
    log(f"  完成！{md_path.name}  ({kb:,} KB)")


# ═══════════════════════════════════════════════════════════════════════════════
#  PDF → EPUB
# ═══════════════════════════════════════════════════════════════════════════════

def _pdf_to_epub_python(pdf_path: Path, epub_path: Path, log) -> None:
    try:
        import fitz
    except ImportError:
        raise RuntimeError("找不到 PyMuPDF，請執行 pip install pymupdf，或安裝 Calibre")

    import ebooklib
    from ebooklib import epub as epublib

    log("  純 Python 備援引擎（PyMuPDF → ebooklib）…")
    doc  = fitz.open(str(pdf_path))
    book = epublib.EpubBook()
    book.set_title(pdf_path.stem)
    book.set_language("zh")

    spine_items, toc = [], []
    for pn in range(len(doc)):
        page = doc[pn]
        text = page.get_text("text").strip()
        if not text:
            continue
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
        c = epublib.EpubHtml(title=f"Page {pn+1}",
                              file_name=f"page_{pn+1:04d}.xhtml", lang="zh")
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


def convert_pdf_to_epub(pdf_path: Path, epub_path: Path, log) -> None:
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
#  EPUB → PDF
# ═══════════════════════════════════════════════════════════════════════════════

def _convert_with_reportlab(epub_path: Path, pdf_path: Path, log) -> None:
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
        raise RuntimeError("找不到 CJK 字型，無法轉換")

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
    PAGE_W = A4[0] - 5 * cm
    PAGE_H = A4[1] - 8 * cm

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


def _calibre_cjk_font() -> str:
    """回傳 Calibre 可用的 CJK 字型名稱（依平台）。"""
    if platform.system() == "Windows":
        return "Microsoft JhengHei"
    # Linux: 查 Noto CJK 是否安裝
    for path in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    ):
        if Path(path).exists():
            return "Noto Sans CJK TC"
    return ""   # 讓 Calibre 自行選擇


def _convert_with_calibre(epub_path: Path, pdf_path: Path, log) -> None:
    log("  引擎：Calibre（備援：純 Python reportlab）")
    cjk = _calibre_cjk_font()
    pdf_opts = [
        "--paper-size", "a4",
        "--margin-top", "20", "--margin-bottom", "20",
        "--margin-left", "25", "--margin-right", "25",
        "--pdf-default-font-size", "12",
        "--base-font-size", "12",
    ]
    if cjk:
        pdf_opts += ["--pdf-serif-family", cjk, "--pdf-sans-family", cjk]
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


def convert_to_pdf(epub_path: Path, pdf_path: Path, log) -> None:
    if CALIBRE_PATH:
        _convert_with_calibre(epub_path, pdf_path, log)
    else:
        _convert_with_reportlab(epub_path, pdf_path, log)
