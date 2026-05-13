"""
translator.py — 語言偵測 + Claude 翻譯引擎
============================================
依賴：langdetect、anthropic
模型：claude-haiku-4-5（速度快、成本低）

翻譯模式：
  none      — 不翻譯（直接輸出）
  bilingual — 雙語對照（原文 + 繁體中文）
  zh        — 全繁體中文
"""

from __future__ import annotations
import os, re

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ISO 639-1 → 中文名稱
_LANG_NAMES: dict[str, str] = {
    "en": "英文", "de": "德文", "fr": "法文", "ja": "日文",
    "ko": "韓文", "es": "西班牙文", "it": "義大利文", "pt": "葡萄牙文",
    "ru": "俄文", "ar": "阿拉伯文", "nl": "荷蘭文", "pl": "波蘭文",
    "zh-cn": "簡體中文", "zh-tw": "繁體中文", "zh": "中文",
}

_CHUNK_CHARS = 3000   # 每批次最大字元數（避免 token 超限）
_TRANSLATE_MODEL = "claude-haiku-4-5"


# ── 語言偵測 ──────────────────────────────────────────────────────────────────

def detect_language(text: str) -> str:
    """偵測語言，回傳 ISO 代碼（如 'en', 'de'）。偵測失敗回傳 'unknown'。"""
    try:
        from langdetect import detect, DetectorFactory
        DetectorFactory.seed = 0
        sample = text[:4000].strip()
        if not sample:
            return "unknown"
        return detect(sample) or "unknown"
    except Exception:
        return "unknown"


def is_cjk_lang(lang: str) -> bool:
    """判斷是否為 CJK 語言（中日韓）。"""
    return lang.startswith("zh") or lang in ("ja", "ko")


def lang_display(lang: str) -> str:
    """回傳語言的中文名稱。"""
    return _LANG_NAMES.get(lang, lang.upper())


# ── 翻譯工具 ──────────────────────────────────────────────────────────────────

def _split_paragraphs(text: str) -> list[str]:
    """將文字切割為段落列表（以空行為界）。"""
    return [p.strip() for p in re.split(r"\n{2,}", text.strip()) if p.strip()]


def _chunk_paragraphs(paras: list[str], max_chars: int = _CHUNK_CHARS) -> list[list[str]]:
    """將段落分批，每批不超過 max_chars 字元。"""
    chunks: list[list[str]] = []
    cur: list[str] = []
    cur_len = 0
    for p in paras:
        if cur and cur_len + len(p) > max_chars:
            chunks.append(cur)
            cur, cur_len = [], 0
        cur.append(p)
        cur_len += len(p)
    if cur:
        chunks.append(cur)
    return chunks


def translate_paragraphs(
    paras: list[str],
    mode: str,
    src_lang: str,
    log,
) -> list[str]:
    """
    翻譯段落列表。
    mode: 'zh'（全繁中）| 'bilingual'（雙語對照）
    回傳翻譯後段落（bilingual 回傳原文與譯文交錯）。
    """
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("未設定 ANTHROPIC_API_KEY 環境變數，無法翻譯")

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    lang_name = lang_display(src_lang)
    chunks = _chunk_paragraphs(paras)
    log(f"  翻譯中（{lang_name} → 繁體中文）：{len(paras)} 段落，共 {len(chunks)} 批次…")

    result: list[str] = []

    for ci, chunk in enumerate(chunks):
        char_count = sum(len(p) for p in chunk)
        log(f"  批次 {ci + 1}/{len(chunks)}  ({char_count:,} 字)…")
        joined = "\n\n".join(chunk)

        if mode == "zh":
            system = (
                "你是專業的繁體中文翻譯員。"
                "請將使用者提供的文字完整翻譯為繁體中文。"
                "規則：①保持段落結構（空行分隔）②只輸出譯文，不加任何說明"
                "③專有名詞首次出現時保留原文並括號附中文，之後只用中文。"
            )
            user_msg = f"以下是{lang_name}文字，請翻譯為繁體中文：\n\n{joined}"
        else:  # bilingual
            system = (
                "你是專業的雙語排版翻譯員。"
                "請將使用者提供的文字輸出為雙語對照格式："
                "每個段落先輸出原文，緊接著輸出繁體中文譯文（以【譯】開頭）。"
                "規則：①段落之間以空行分隔②只輸出對照文字，不加額外說明。"
            )
            user_msg = f"以下是{lang_name}文字，請輸出雙語對照：\n\n{joined}"

        msg = client.messages.create(
            model=_TRANSLATE_MODEL,
            max_tokens=8192,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        translated = msg.content[0].text.strip()
        translated_paras = [p.strip() for p in re.split(r"\n{2,}", translated) if p.strip()]
        result.extend(translated_paras)

    return result


def translate_chapters(
    chapters_text: list[str],
    mode: str,
    log,
) -> tuple[str, list[str]]:
    """
    偵測語言，並翻譯所有章節文字。
    回傳 (detected_lang, translated_chapters)。
    若語言為 CJK 或 mode=='none'，直接回傳原文。
    """
    # 偵測語言（取前兩章合併樣本）
    sample = "\n\n".join(chapters_text[:2])[:4000]
    lang = detect_language(sample)
    log(f"  偵測語言：{lang_display(lang)}（{lang}）")

    if mode == "none" or is_cjk_lang(lang):
        if mode != "none" and is_cjk_lang(lang):
            log("  書籍已是 CJK 語言，跳過翻譯。")
        return lang, chapters_text

    translated: list[str] = []
    for ci, text in enumerate(chapters_text):
        log(f"  翻譯章節 {ci + 1}/{len(chapters_text)}…")
        paras = _split_paragraphs(text)
        if not paras:
            translated.append(text)
            continue
        translated_paras = translate_paragraphs(paras, mode, lang, log)
        translated.append("\n\n".join(translated_paras))

    return lang, translated
