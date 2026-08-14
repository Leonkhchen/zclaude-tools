"""
grading.py — 把 OCR 辨識出來的文字跟標準詩句逐字比對，標出錯字、漏字、
多字。

用 difflib 做字元級的 diff，不依賴任何外部服務，所以這部分不管 Colab 端
換成什麼模型都不用改。
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

_PUNCTUATION = "，。、；：？！「」『』（）　 \n\t"


def _normalize(text: str) -> str:
    """比對前先拿掉標點與空白，避免辨識出來的標點符號差異被誤判成錯字。"""
    return "".join(ch for ch in text if ch not in _PUNCTUATION)


@dataclass
class DiffSegment:
    op: str          # "equal" | "wrong" | "missing" | "extra"
    expected: str     # 標準詩句裡的字（missing/equal 才有）
    got: str          # 辨識出來的字（wrong/extra 才有）


@dataclass
class GradeResult:
    poem_id: str
    poem_title: str
    expected_text: str
    recognized_text: str
    segments: list[DiffSegment] = field(default_factory=list)
    correct_count: int = 0
    total_count: int = 0
    accuracy: float = 0.0


def grade(recognized_text: str, poem_id: str, poem_title: str, poem_text: str) -> GradeResult:
    expected = _normalize(poem_text)
    got = _normalize(recognized_text)

    matcher = difflib.SequenceMatcher(a=expected, b=got, autojunk=False)
    segments: list[DiffSegment] = []

    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag == "equal":
            for ch in expected[a0:a1]:
                segments.append(DiffSegment("equal", ch, ch))
        elif tag == "replace":
            exp_chunk = expected[a0:a1]
            got_chunk = got[b0:b1]
            length = max(len(exp_chunk), len(got_chunk))
            for i in range(length):
                e = exp_chunk[i] if i < len(exp_chunk) else ""
                g = got_chunk[i] if i < len(got_chunk) else ""
                if e and g:
                    segments.append(DiffSegment("wrong", e, g))
                elif e:
                    segments.append(DiffSegment("missing", e, ""))
                else:
                    segments.append(DiffSegment("extra", "", g))
        elif tag == "delete":
            for ch in expected[a0:a1]:
                segments.append(DiffSegment("missing", ch, ""))
        elif tag == "insert":
            for ch in got[b0:b1]:
                segments.append(DiffSegment("extra", "", ch))

    total = len(expected)
    correct = sum(1 for s in segments if s.op == "equal")
    accuracy = round(correct / total * 100, 1) if total else 0.0

    return GradeResult(
        poem_id=poem_id,
        poem_title=poem_title,
        expected_text=poem_text,
        recognized_text=recognized_text,
        segments=segments,
        correct_count=correct,
        total_count=total,
        accuracy=accuracy,
    )


def to_dict(result: GradeResult) -> dict:
    return {
        "poem_id": result.poem_id,
        "poem_title": result.poem_title,
        "expected_text": result.expected_text,
        "recognized_text": result.recognized_text,
        "segments": [
            {"op": s.op, "expected": s.expected, "got": s.got} for s in result.segments
        ],
        "correct_count": result.correct_count,
        "total_count": result.total_count,
        "accuracy": result.accuracy,
    }
