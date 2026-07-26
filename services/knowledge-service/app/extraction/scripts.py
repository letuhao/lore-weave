"""Shared Unicode script ranges for degrade-open, script-aware name detection.

Multilingual ML-3: proper-noun / candidate detection must not assume Latin
script. English-first heuristics (an ASCII-capitalized regex, Han-only CJK runs)
silently miss Vietnamese diacritics, Japanese kana, and Korean hangul. This is the
SINGLE definition of the script ranges so the two consumers — the context
candidate selector (`context/selectors/glossary.py`) and the extraction entity
detector (`extraction/entity_detector.py`) — can't drift apart.

Scope note: this is **degrade-open detection**, not a segmenter. Runs of an
unspaced script (Han/kana/hangul) are surfaced as bounded candidate runs and
soft-split on particles; a real jieba/MeCab segmenter is tracked separately
(D-ML-SEGMENTER) and only justified if this proves insufficient.
"""

from __future__ import annotations

import re

__all__ = [
    "HAN", "HIRAGANA", "KATAKANA", "HANGUL",
    "CJK_FAMILY", "CJK_FAMILY_RUN_RE", "is_cjk_family",
    "LATIN_UPPER", "LATIN_LOWER", "LATIN_NAME_RE",
    "CJK_SPLIT_PARTICLES", "split_cjk_run",
]

# ── unspaced-script ranges (BMP; degrade-open, not exhaustive) ──────────────
HAN = "一-鿿"          # CJK Unified Ideographs
HIRAGANA = "぀-ゟ"
KATAKANA = "゠-ヿ"     # incl. ー prolonged mark, ・ middle dot
HANGUL = "가-힯"       # Hangul syllables

# The CJK-family class: Han + kana + hangul — the unspaced scripts whose names
# the Latin capitalized-phrase heuristic can never see.
CJK_FAMILY = HAN + HIRAGANA + KATAKANA + HANGUL

# A run of 2+ CJK-family chars is a candidate span (soft-split on particles by
# the caller). 2+ avoids single stray ideographs (usually grammatical).
CJK_FAMILY_RUN_RE = re.compile(f"[{CJK_FAMILY}]{{2,}}")

_CJK_FAMILY_CHAR_RE = re.compile(f"[{CJK_FAMILY}]")


def is_cjk_family(ch: str) -> bool:
    """True if `ch` is a Han / kana / hangul character."""
    return bool(ch) and _CJK_FAMILY_CHAR_RE.match(ch[0]) is not None


# ── Latin letters incl. Vietnamese diacritics ──────────────────────────────
# Vietnamese uses ASCII + Latin-1 Supplement + a few Latin Extended-A letters +
# the full Latin Extended Additional block (Ạ-ỹ, where even codepoints
# are uppercase and odd are lowercase). We build the upper/lower classes exactly
# so a capitalized-name regex matches "Nguyễn", "Lê Văn", "Đường", "Trần".
_LEA_UPPER = "".join(chr(c) for c in range(0x1EA0, 0x1EFA, 2))  # Ạ Ả Ấ … Ỹ
_LEA_LOWER = "".join(chr(c) for c in range(0x1EA1, 0x1EFA, 2))  # ạ ả ấ … ỹ

# Latin-1 upper À-Ö Ø-Þ ; Extended-A: Ă Đ Ĩ Ũ Ơ Ư
LATIN_UPPER = "A-ZÀ-ÖØ-ÞĂĐĨŨƠƯ" + _LEA_UPPER
# Latin-1 lower à-ö ø-ÿ ; Extended-A: ă đ ĩ ũ ơ ư
LATIN_LOWER = "a-zà-öø-ÿăđĩũơư" + _LEA_LOWER

# Capitalized phrase (up to 5 words), Vietnamese-diacritic aware. Mirrors the old
# ASCII-only capitalized-phrase shape but with the widened upper/lower classes.
# Apostrophes allowed inside a token (O'Neill / d'Artagnan) but not word-initial.
#
# Sino-Vietnamese naming (D-BRIDGE-NAME-FRAGMENT, ML): transliterated cultivation
# names run 4-5 syllables and can carry a SINGLE-uppercase-letter INTERIOR syllable
# ("Cửu U Ma Cơ", "Booker T Washington"). The old shape broke on both — each word
# demanded ≥1 lowercase (so the bare "U" split the name in two) and the {0,2} cap
# truncated a 4-syllable name ("Hắc Sát Lão Nhân"). Fixes:
#   - a subsequent word may be a real word OR a single uppercase letter, but the
#     single-letter form is admitted ONLY as an INTERIOR connector — a lookahead
#     requires a real word to follow — so a trailing stray capital ("Paris U") is
#     NOT glued on and the resolvable name is preserved.
#   - cap raised {0,2} → {0,4} (up to 5 syllables).
_LN_WORD = rf"[{LATIN_UPPER}][{LATIN_LOWER}'’]+"
_LN_CONNECTOR = rf"[{LATIN_UPPER}](?=[\s\-]{_LN_WORD})"  # interior single-upper only
LATIN_NAME_RE = re.compile(
    rf"\b{_LN_WORD}"
    rf"(?:[\s\-](?:{_LN_WORD}|{_LN_CONNECTOR})){{0,4}}\b"
)


# ── soft segmentation for unspaced CJK-family runs ──────────────────────────
# The SINGLE source of the split particles (context/formatters/stopwords.py
# re-exports this as CJK_PARTICLES). Chinese function words + Japanese hiragana
# particles; Korean josa excluded — those syllables also occur inside Korean
# given names (지은/서은), so splitting on them would shred real names, so a
# hangul run stays whole (degrade-open).
_ZH_PARTICLES = "的是了在和与及或把被这那就也都还很"
_JA_PARTICLES = "はがをにへとものやでかしねよさ"
CJK_SPLIT_PARTICLES: str = _ZH_PARTICLES + _JA_PARTICLES

_CJK_SPLIT_RE = re.compile(f"[{CJK_SPLIT_PARTICLES}]+")


def split_cjk_run(run: str, *, min_len: int = 2) -> list[str]:
    """Soft-split a CJK-family run on particles into candidate segments.

    `告诉我关于李雲的故事` → split on 的 → ["告诉我关于李雲", "故事"];
    `田中は学校へ行った` → split on は/へ → ["田中", "学校", "行った"].
    Segments shorter than `min_len` are dropped. Still imperfect without a real
    segmenter (D-ML-SEGMENTER) but far better than one whole-sentence candidate.
    """
    return [seg for seg in (s.strip() for s in _CJK_SPLIT_RE.split(run)) if len(seg) >= min_len]
