"""V3 romanization policy (M1c) — prompt-level instruction for un-glossaried names.

PO decision: prompt-level only (no lexicon). For zh→vi, instruct the model to use
Sino-Vietnamese (Hán-Việt) readings rather than pinyin for proper names the glossary
doesn't pin. Other language pairs get no instruction (empty string). The verifier
does NOT check romanization (no lexicon to verify against) — this is a nudge.
"""
from __future__ import annotations

_HAN_VIET = (
    "PROPER NAMES: For Chinese personal and place names NOT listed in the glossary, "
    "transliterate using Sino-Vietnamese (Hán-Việt) readings, NOT pinyin — e.g. "
    "王 → Vương (not Wang), 李 → Lý (not Li), 北京 → Bắc Kinh (not Beijing). "
    "Render each such name consistently throughout."
)


def _primary(code: str) -> str:
    """Primary language subtag, lowercased (BCP-47): 'zh-Hans-CN' → 'zh', 'vi-VN' → 'vi'."""
    return (code or "").lower().split("-")[0]


def romanization_instruction(source_lang: str, target_lang: str) -> str:
    """Return the romanization-policy instruction for a language pair, or '' if none.

    Matches on the primary subtag so region/script variants (zh-Hans, zh-CN, vi-VN)
    are all covered (review-impl LOW-1)."""
    if _primary(source_lang) == "zh" and _primary(target_lang) == "vi":
        return _HAN_VIET
    return ""
