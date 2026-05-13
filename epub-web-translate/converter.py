"""
converter.py  —  EPUB / PDF 轉換引擎（含翻譯支援）
====================================================
在原版 epub-web/converter.py 基礎上加入：
  - translation_mode 參數（none / bilingual / zh）
  - 翻譯後以 reportlab 重建 PDF（繁體 WQY 字型）
  - Markdown 輸出時一併翻譯
"""

from __future__ import annotations
import os, re, platform, subprocess, shutil, threading
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

# ── CJK 字型（WQY TrueType，reportlab 相容）──────────────────────────────────

_WQY_RUNTIME_PATH = Path("/tmp/epub_jobs/wqy-microhei.ttc")
_wqy_lock = threading.Lock()


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
            (str(_WQY_RUNTIME_PATH),                                    0, "WQYMicroHei"),
            ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",         0, "WQYMicroHei"),
            ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",           0, "WQYZenHei"),
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",        0, "DejaVuSans"),
        ]


def _ensure_wqy_font(log) -> None:
    with _wqy_lock:
        if _WQY_RUNTIME_PATH.exists() and _WQY_RUNTIME_PATH.stat().st_size > 1_000_000:
            return
        for apt_path in (
            Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
            Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        ):
            if apt_path.exists():
                return
        import urllib.request
        url = ("https://raw.githubusercontent.com/"
               "anthonyfok/fonts-wqy-microhei/master/wqy-microhei.ttc")
        try:
            log("  WQY 字型不存在，正在下載（~5 MB）…")
            _WQY_RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = _WQY_RUNTIME_PATH.with_suffix(".tmp")
            urllib.request.urlretrieve(url, str(tmp))
            if tmp.stat().st_size > 1_000_000:
                tmp.rename(_WQY_RUNTIME_PATH)
                log(f"  WQY 字型下載完成（{_WQY_RUNTIME_PATH.stat().st_size // 1024:,} KB）")
            else:
                tmp.unlink(missing_ok=True)
        except Exception as e:
            log(f"  WQY 字型下載失敗：{e}")


def _register_cjk_font(log) -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if platform.system() != "Windows":
        _ensure_wqy_font(log)
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


# ── Calibre 執行 ──────────────────────────────────────────────────────────────

def _calibre_run(src: Path, dst: Path, extra_args: list, log) -> int:
    cmd = [CALIBRE_PATH, str(src), str(dst)] + extra_args
    kwargs = dict(
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    if platform.system() == "Windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        env = dict(os.environ)
        env["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --disable-gpu"
        env["QT_QPA_PLATFORM"] = "offscreen"
        kwargs["env"] = env
        xvfb = shutil.which("xvfb-run")
        if xvfb:
            cmd = [xvfb, "--auto-servernum", "--server-args=-screen 0 1024x768x24"] + cmd
    proc = subprocess.run(cmd, **kwargs)
    for line in proc.stdout.splitlines():
        if line.strip():
            log(f"    {line.strip()}")
    return proc.returncode


# ── HTML → Markdown / 純文字 工具 ─────────────────────────────────────────────

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
    if name == "h1": return f"\n# {kids.strip()}\n\n"
    if name == "h2": return f"\n## {kids.strip()}\n\n"
    if name == "h3": return f"\n### {kids.strip()}\n\n"
    if name in ("h4","h5","h6"): return f"\n#### {kids.strip()}\n\n"
    if name == "p":
        t = kids.strip()
        return f"{t}\n\n" if t else ""
    if name in ("strong","b"): return f"**{kids}**"
    if name in ("em","i"):     return f"*{kids}*"
    if name == "code":         return f"`{kids}`"
    if name == "pre":          return f"\n```\n{kids.strip()}\n```\n\n"
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
        parts = [f"- {_elem_to_md(li).strip()}"
                 for li in el.find_all("li", recursive=False)]
        return "\n".join(parts) + "\n\n" if parts else kids
    if name == "ol":
        parts = [f"{i}. {_elem_to_md(li).strip()}"
                 for i, li in enumerate(el.find_all("li", recursive=False), 1)]
        return "\n".join(parts) + "\n\n" if parts else kids
    if name == "li":  return kids
    if name == "br":  return "\n"
    if name == "hr":  return "\n---\n\n"
    if name == "table":
        rows = el.find_all("tr")
        if not rows: return kids
        result = []
        for ri, row in enumerate(rows):
            cells = row.find_all(["td","th"])
            result.append("| " + " | ".join(_elem_to_md(c).strip() for c in cells) + " |")
            if ri == 0:
                result.append("|" + "|".join(" --- " for _ in cells) + "|")
        return "\n".join(result) + "\n\n"
    return kids


def _extract_chapters_html(epub_path: Path) -> tuple[str, list[str]]:
    """讀取 EPUB，回傳 (title, [html_string, ...])。"""
    import ebooklib, warnings
    from ebooklib import epub
    from bs4 import XMLParsedAsHTMLWarning
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

    book = epub.read_epub(str(epub_path), options={"ignore_ncx": True})
    title = book.title or epub_path.stem
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
    return title, chapters


def _html_to_plain(html: str) -> str:
    """將 HTML 章節轉為純文字（用於語言偵測與翻譯）。
    以段落層級元素分割，確保 _split_paragraphs 能正確切割。
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    body = soup.find("body") or soup
    BLOCK = {"p", "h1", "h2", "h3", "h4", "h5", "h6",
             "li", "blockquote", "pre", "div", "td", "th"}
    parts: list[str] = []
    for tag in body.find_all(BLOCK):
        # 跳過巢狀 block（避免重複）
        if any(p.name in BLOCK for p in tag.parents if p != body):
            continue
        t = tag.get_text(" ", strip=True)
        if t:
            parts.append(t)
    if parts:
        return "\n\n".join(parts)
    # fallback：直接用雙換行
    return body.get_text("\n\n", strip=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  Markdown 輸出
# ═══════════════════════════════════════════════════════════════════════════════

def convert_to_md(
    epub_path: Path,
    md_path: Path,
    log,
    translation_mode: str = "none",
) -> None:
    """EPUB → Markdown（可選翻譯）。"""
    from bs4 import BeautifulSoup

    log("  轉換為 Markdown …")
    title, html_chapters = _extract_chapters_html(epub_path)
    log(f"  共 {len(html_chapters)} 個章節")

    # 翻譯
    if translation_mode != "none":
        from translator import translate_chapters
        plain_chapters = [_html_to_plain(h) for h in html_chapters]
        detected_lang, translated_texts = translate_chapters(
            plain_chapters, translation_mode, log
        )
        # 翻譯模式：直接用純文字輸出（不再解析 HTML 結構）
        parts = [f"# {title}\n\n"]
        for i, text in enumerate(translated_texts):
            if i > 0:
                parts.append("\n\n---\n\n")
            parts.append(text)
        content = "\n".join(parts)
    else:
        # 原文模式：保留 HTML 結構轉 Markdown
        parts = [f"# {title}\n\n"]
        for i, html in enumerate(html_chapters):
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
        raise RuntimeError("找不到 PyMuPDF，請執行 pip install pymupdf")
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
        escaped = text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        html_body = "\n".join(
            f"<p>{l}</p>" if l.strip() else "<br/>" for l in escaped.splitlines()
        )
        html = (
            "<?xml version='1.0' encoding='utf-8'?>"
            "<!DOCTYPE html>"
            "<html xmlns='http://www.w3.org/1999/xhtml'><head>"
            f"<title>Page {pn+1}</title>"
            "<meta charset='utf-8'/></head><body>"
            f"<h2>第 {pn+1} 頁</h2>{html_body}</body></html>"
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
        rc = _calibre_run(pdf_path, epub_path,
                          ["--enable-heuristics", "--language", "zh"], log)
        if rc == 0 and epub_path.exists():
            log(f"  完成！{epub_path.name}  ({epub_path.stat().st_size//1024:,} KB)")
            return
        log("  改用純 Python 備援 …")
        if epub_path.exists():
            epub_path.unlink()
    _pdf_to_epub_python(pdf_path, epub_path, log)


# ═══════════════════════════════════════════════════════════════════════════════
#  EPUB → PDF（含翻譯）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_pdf_from_texts(
    title: str,
    chapters_text: list[str],
    pdf_path: Path,
    log,
) -> None:
    """用 reportlab 從純文字段落建立 PDF（含 CJK 字型）。"""
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

    font_name = _register_cjk_font(log)
    if not font_name:
        raise RuntimeError("找不到 CJK 字型，無法建立 PDF")

    def ps(name, size, leading, sb=0, sa=4, align=0):
        return ParagraphStyle(name, fontName=font_name, fontSize=size,
                               leading=leading, spaceBefore=sb, spaceAfter=sa,
                               alignment=align, wordWrap="CJK")

    S = {
        "title": ps("title", 20, 28, sb=0,  sa=16, align=1),
        "p":     ps("p",     11, 18, sb=0,  sa=4),
    }

    def esc(t: str) -> str:
        return t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=A4,
        leftMargin=2.5*cm, rightMargin=2.5*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    story: list = [Paragraph(esc(title), S["title"]), Spacer(1, 0.5*cm)]

    for ci, text in enumerate(chapters_text):
        if ci > 0:
            story.append(PageBreak())
        for para in re.split(r"\n{2,}", text.strip()):
            para = para.strip()
            if para:
                story.append(Paragraph(esc(para), S["p"]))

    doc.build(story)
    kb = pdf_path.stat().st_size // 1024
    log(f"  完成！{pdf_path.name}  ({kb:,} KB)")


def _convert_with_reportlab(
    epub_path: Path, pdf_path: Path, log,
    translation_mode: str = "none",
) -> None:
    """reportlab 備援引擎（支援翻譯）。"""
    import warnings
    from bs4 import XMLParsedAsHTMLWarning
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

    log("  純 reportlab 備援引擎啟動 …")
    title, html_chapters = _extract_chapters_html(epub_path)
    log(f"  共 {len(html_chapters)} 個章節")

    plain_chapters = [_html_to_plain(h) for h in html_chapters]

    if translation_mode != "none":
        from translator import translate_chapters
        _, plain_chapters = translate_chapters(plain_chapters, translation_mode, log)

    _build_pdf_from_texts(title, plain_chapters, pdf_path, log)


def _convert_with_calibre(
    epub_path: Path, pdf_path: Path, log,
    translation_mode: str = "none",
) -> None:
    """Calibre 主引擎。若需翻譯則先翻譯後用 reportlab 重建 PDF。"""
    if translation_mode != "none":
        # 翻譯後必須重建 PDF，直接走 reportlab 路徑
        log("  翻譯模式：跳過 Calibre，使用 reportlab 重建 PDF …")
        _convert_with_reportlab(epub_path, pdf_path, log, translation_mode)
        return

    log("  引擎：Calibre（備援：純 Python reportlab）")
    pdf_opts = [
        "--paper-size", "a4",
        "--margin-top", "20", "--margin-bottom", "20",
        "--margin-left", "25", "--margin-right", "25",
        "--pdf-default-font-size", "12",
        "--base-font-size", "12",
    ]
    log("  嘗試 1：Calibre EPUB → PDF …")
    rc = _calibre_run(epub_path, pdf_path, pdf_opts, log)
    if rc == 0 and pdf_path.exists():
        log(f"  完成！{pdf_path.name}  ({pdf_path.stat().st_size//1024:,} KB)")
        return
    log("  嘗試 1 失敗，改用純 Python 備援（reportlab）…")
    if pdf_path.exists():
        pdf_path.unlink()
    _convert_with_reportlab(epub_path, pdf_path, log, translation_mode="none")


def convert_to_pdf(
    epub_path: Path,
    pdf_path: Path,
    log,
    translation_mode: str = "none",
) -> None:
    if CALIBRE_PATH:
        _convert_with_calibre(epub_path, pdf_path, log, translation_mode)
    else:
        _convert_with_reportlab(epub_path, pdf_path, log, translation_mode)
