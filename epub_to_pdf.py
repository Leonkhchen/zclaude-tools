"""
epub_to_pdf.py — 將 EPUB 檔案轉換為 PDF

依賴套件：
    pip install ebooklib beautifulsoup4 xhtml2pdf pillow lxml

用法：
    python epub_to_pdf.py input.epub              # 輸出同目錄 input.pdf
    python epub_to_pdf.py input.epub output.pdf   # 指定輸出路徑
    python epub_to_pdf.py *.epub                  # 批次轉換
"""

import sys
import os
import re
import argparse
from pathlib import Path
from io import BytesIO

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from xhtml2pdf import pisa


# ── CSS 基礎樣式（處理中文字型與排版）──────────────────────────────────────
BASE_CSS = """
@page {
    size: A4;
    margin: 2cm 2.5cm;
}

body {
    font-family: "Microsoft JhengHei", "Microsoft YaHei", "SimSun",
                 "Noto Sans CJK TC", "Arial Unicode MS", Arial, sans-serif;
    font-size: 12pt;
    line-height: 1.8;
    color: #1a1a1a;
    word-wrap: break-word;
    overflow-wrap: break-word;
}

h1, h2, h3, h4, h5, h6 {
    font-weight: bold;
    margin-top: 1.2em;
    margin-bottom: 0.4em;
    page-break-after: avoid;
}
h1 { font-size: 20pt; }
h2 { font-size: 16pt; }
h3 { font-size: 14pt; }
h4 { font-size: 13pt; }

p {
    margin: 0.4em 0 0.6em 0;
    text-align: justify;
}

img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0.8em auto;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 0.8em 0;
    font-size: 10pt;
}
td, th {
    border: 1px solid #ccc;
    padding: 4px 8px;
}
th { background-color: #f0f0f0; font-weight: bold; }

blockquote {
    margin: 0.8em 2em;
    padding: 0.4em 1em;
    border-left: 3px solid #aaa;
    color: #555;
}

pre, code {
    font-family: "Courier New", monospace;
    font-size: 10pt;
    background-color: #f5f5f5;
    padding: 0.2em 0.4em;
    border-radius: 2px;
}
pre {
    padding: 0.8em;
    overflow-x: auto;
    white-space: pre-wrap;
}

a { color: #1a5cb5; text-decoration: none; }

hr {
    border: none;
    border-top: 1px solid #ccc;
    margin: 1em 0;
}

.chapter-title {
    font-size: 18pt;
    font-weight: bold;
    text-align: center;
    margin: 2em 0 1em 0;
    page-break-before: always;
}
.chapter-title:first-child {
    page-break-before: avoid;
}
"""


def extract_chapters(book: epub.EpubBook) -> list[dict]:
    """從 EPUB 讀取所有章節的 HTML 內容與圖片資源。"""
    chapters = []

    # 依照 spine 順序取出章節（保持書籍原始排列）
    for item_id, _ in book.spine:
        item = book.get_item_with_id(item_id)
        if item is None:
            continue
        if item.get_type() not in (ebooklib.ITEM_DOCUMENT, ebooklib.ITEM_XHTML):
            continue
        content = item.get_content()
        if content:
            chapters.append({
                "id": item_id,
                "name": item.get_name(),
                "html": content.decode("utf-8", errors="replace"),
            })

    if not chapters:
        # spine 為空時回退：取全部 XHTML 文件
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            content = item.get_content()
            if content:
                chapters.append({
                    "id": item.get_id(),
                    "name": item.get_name(),
                    "html": content.decode("utf-8", errors="replace"),
                })

    return chapters


def get_image_map(book: epub.EpubBook) -> dict[str, bytes]:
    """回傳 {路徑 → 二進位資料} 的圖片字典。"""
    images = {}
    for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
        images[item.get_name()] = item.get_content()
        # 也加入只有檔名的索引（EPUB 路徑可能有前綴）
        images[os.path.basename(item.get_name())] = item.get_content()
    return images


def clean_html(raw_html: str, image_map: dict[str, bytes], chapter_name: str) -> str:
    """清理 HTML：移除不必要的 script/style，將圖片轉為 data URI。"""
    soup = BeautifulSoup(raw_html, "lxml")

    # 移除不需要的標籤
    for tag in soup(["script", "link", "meta", "base"]):
        tag.decompose()

    # 將 <style> 保留但過濾掉 @import（避免找不到字型檔出錯）
    for style_tag in soup.find_all("style"):
        css_text = style_tag.string or ""
        css_text = re.sub(r"@import[^;]+;", "", css_text)
        style_tag.string = css_text

    # 嵌入圖片為 base64 data URI
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if not src or src.startswith("data:"):
            continue
        # 解碼 URL 編碼後取檔名
        from urllib.parse import unquote
        src_decoded = unquote(src)
        basename = os.path.basename(src_decoded)

        img_data = image_map.get(src_decoded) or image_map.get(basename)
        if img_data:
            import base64
            ext = Path(basename).suffix.lower().lstrip(".")
            mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png",
                    "gif": "gif", "svg": "svg+xml", "webp": "webp"}.get(ext, "png")
            b64 = base64.b64encode(img_data).decode()
            img["src"] = f"data:image/{mime};base64,{b64}"
        else:
            img.decompose()  # 找不到圖片就移除，避免 xhtml2pdf 出錯

    # 取出 body 內容（若有 body 標籤）
    body = soup.find("body")
    inner = str(body) if body else str(soup)

    return inner


def build_combined_html(book: epub.EpubBook) -> str:
    """將所有章節合併成單一 HTML 字串供 xhtml2pdf 使用。"""
    chapters = extract_chapters(book)
    image_map = get_image_map(book)

    title = book.title or "Untitled"

    parts = [
        f"<!DOCTYPE html><html><head>",
        f"<meta charset='utf-8'/>",
        f"<title>{title}</title>",
        f"<style>{BASE_CSS}</style>",
        f"</head><body>",
        f"<h1 class='chapter-title' style='page-break-before:avoid'>{title}</h1>",
    ]

    for i, ch in enumerate(chapters):
        cleaned = clean_html(ch["html"], image_map, ch["name"])
        # 每章加分頁（第一章除外）
        divider = "<div style='page-break-before:always'></div>" if i > 0 else ""
        parts.append(divider + cleaned)

    parts.append("</body></html>")
    return "\n".join(parts)


def link_callback(uri: str, rel: str):
    """xhtml2pdf 的資源解析回調 — 只處理本機檔案路徑，data URI 直接回傳。"""
    if uri.startswith("data:"):
        return uri
    # 嘗試當作絕對路徑
    if os.path.isabs(uri) and os.path.exists(uri):
        return uri
    return uri


def convert(epub_path: str, pdf_path: str | None = None) -> str:
    """
    轉換單一 EPUB 檔案。
    回傳輸出的 PDF 路徑字串。
    """
    epub_path = Path(epub_path).resolve()
    if not epub_path.exists():
        raise FileNotFoundError(f"找不到檔案：{epub_path}")

    if pdf_path is None:
        pdf_path = epub_path.with_suffix(".pdf")
    pdf_path = Path(pdf_path).resolve()

    print(f"  讀取 EPUB：{epub_path.name}")
    book = epub.read_epub(str(epub_path), options={"ignore_ncx": True})

    print(f"  合併章節中…")
    html_content = build_combined_html(book)

    print(f"  轉換為 PDF…")
    with open(pdf_path, "wb") as f:
        result = pisa.CreatePDF(
            src=html_content,
            dest=f,
            encoding="utf-8",
            link_callback=link_callback,
        )

    if result.err:
        raise RuntimeError(f"PDF 生成時發生 {result.err} 個錯誤，請檢查 EPUB 內容。")

    size_kb = pdf_path.stat().st_size // 1024
    print(f"  完成：{pdf_path}  ({size_kb} KB)")
    return str(pdf_path)


# ── CLI 入口 ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="將 EPUB 轉換為 PDF（支援中文）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""範例：
  python epub_to_pdf.py book.epub
  python epub_to_pdf.py book.epub output.pdf
  python epub_to_pdf.py *.epub
""",
    )
    parser.add_argument("inputs", nargs="+", help="EPUB 輸入檔案（可多個）")
    parser.add_argument("-o", "--output", help="PDF 輸出路徑（僅單一輸入時有效）")
    args = parser.parse_args()

    if len(args.inputs) > 1 and args.output:
        parser.error("批次模式（多個輸入）不能指定 -o 輸出路徑")

    success, failed = 0, []
    for epub_file in args.inputs:
        try:
            print(f"\n[{epub_file}]")
            convert(epub_file, args.output if len(args.inputs) == 1 else None)
            success += 1
        except Exception as e:
            print(f"  ✗ 失敗：{e}")
            failed.append(epub_file)

    print(f"\n{'='*40}")
    print(f"完成 {success} 個，失敗 {len(failed)} 個")
    if failed:
        print("失敗清單：" + ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
