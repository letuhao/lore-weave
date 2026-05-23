"""Plaintext parser tests — spec §4.1 plaintext rows + D5 regex sets + M3 fix."""

from __future__ import annotations

from loreweave_parse import detect_language, parse, parse_plain

# ─── EN ──────────────────────────────────────────────────────────────────────

_EN_NUMERIC = """\
Chapter 1
Body of chapter 1.

* * *

Body of chapter 1 scene 2.

Chapter 2
Body of chapter 2.
"""

_EN_ROMAN = """\
I.
Body of chapter one.

II.
Body of chapter two.
"""

_EN_ROMAN_WITH_FALSE_POSITIVE = """\
Preamble: I. understand the rule.

I.
Real chapter one body. Also, I. is mid-sentence here too.

II.
Real chapter two body.
"""

_EN_MULTI_PART = """\
Part 1
Chapter 1
Part 1 ch 1 body.

Chapter 2
Part 1 ch 2 body.

Part 2
Chapter 1
Part 2 ch 1 body.
"""

# ─── ZH ──────────────────────────────────────────────────────────────────────

_ZH_BASIC = """\
第一卷 序章
第一章 起源
卷一章一正文。

※ ※ ※

卷一章一第二景。

第二章 旅途
卷一章二正文。
"""

# ─── VI ──────────────────────────────────────────────────────────────────────

_VI_BASIC = """\
Phần I
Chương 1
Văn bản chương một.

– – –

Cảnh hai của chương một.

Chương 2
Văn bản chương hai.
"""

_VI_HOI = """\
Hồi 1
Văn bản hồi một.

Hồi 2
Văn bản hồi hai.
"""

# ─── JA ──────────────────────────────────────────────────────────────────────

_JA_BASIC = """\
第一巻 序
第一章 始まり
本文第一章。

※ ※ ※

第一章の第二場面。

その二
本文「その二」。
"""

# ─── Mixed: no markers ──────────────────────────────────────────────────────

_NO_MARKERS = """\
This is just prose.
Nothing structural here at all.
"""


# ─── tests ───────────────────────────────────────────────────────────────────


def test_plaintext_english_chapter():
    tree = parse_plain(_EN_NUMERIC, language="en")
    assert tree.source_format == "plain"
    assert tree.walker_path == "headings"
    assert len(tree.parts) == 1
    chapters = tree.parts[0].chapters
    assert len(chapters) == 2
    assert chapters[0].title and "Chapter 1" in chapters[0].title
    # Scene split on dinkus.
    assert len(chapters[0].scenes) == 2


def test_plaintext_english_roman_numeral():
    tree = parse_plain(_EN_ROMAN, language="en")
    chapters = tree.parts[0].chapters
    assert len(chapters) == 2
    assert chapters[0].title == "I."
    assert chapters[1].title == "II."


def test_plaintext_english_roman_no_false_positives_m3():
    """M3 regression: 'I. understand' mid-paragraph must NOT be parsed as a chapter."""
    tree = parse_plain(_EN_ROMAN_WITH_FALSE_POSITIVE, language="en")
    chapters = tree.parts[0].chapters
    # Should find exactly 2 chapters (the standalone-line I. and II.), not more.
    assert len(chapters) == 2
    assert chapters[0].title == "I."
    assert chapters[1].title == "II."
    # The "I. understand" preamble should NOT have become a chapter title.
    titles = [c.title for c in chapters]
    assert "I. understand the rule." not in titles


def test_plaintext_english_multi_part():
    tree = parse_plain(_EN_MULTI_PART, language="en")
    assert len(tree.parts) == 2
    assert tree.parts[0].title and "Part 1" in tree.parts[0].title
    assert len(tree.parts[0].chapters) == 2
    assert tree.parts[1].title and "Part 2" in tree.parts[1].title
    assert len(tree.parts[1].chapters) == 1


def test_plaintext_chinese_chapter():
    tree = parse_plain(_ZH_BASIC, language="zh")
    assert len(tree.parts) == 1  # 第一卷
    assert tree.parts[0].title and "第一卷" in tree.parts[0].title
    chapters = tree.parts[0].chapters
    assert len(chapters) == 2
    assert chapters[0].title and "第一章" in chapters[0].title
    # scene split on ※ ※ ※
    assert len(chapters[0].scenes) == 2


def test_plaintext_vietnamese_chuong():
    tree = parse_plain(_VI_BASIC, language="vi")
    assert len(tree.parts) == 1
    assert tree.parts[0].title and "Phần I" in tree.parts[0].title
    chapters = tree.parts[0].chapters
    assert len(chapters) == 2
    assert chapters[0].title and "Chương 1" in chapters[0].title
    assert len(chapters[0].scenes) == 2


def test_plaintext_vietnamese_hoi():
    tree = parse_plain(_VI_HOI, language="vi")
    chapters = tree.parts[0].chapters
    assert len(chapters) == 2
    assert chapters[0].title and "Hồi 1" in chapters[0].title


def test_plaintext_japanese_chapter():
    tree = parse_plain(_JA_BASIC, language="ja")
    assert len(tree.parts) == 1
    chapters = tree.parts[0].chapters
    assert len(chapters) == 2
    assert chapters[0].title and "第一章" in chapters[0].title
    assert chapters[1].title and "その二" in chapters[1].title


def test_plaintext_no_markers_fallback_single():
    tree = parse_plain(_NO_MARKERS, language="en")
    assert tree.walker_path == "fallback_single"
    assert len(tree.parts) == 1
    assert len(tree.parts[0].chapters) == 1
    assert len(tree.parts[0].chapters[0].scenes) == 1


def test_detect_language_picks_chinese():
    assert detect_language(_ZH_BASIC) == "zh"


def test_detect_language_picks_vietnamese():
    assert detect_language(_VI_BASIC) == "vi"


def test_detect_language_picks_japanese():
    assert detect_language(_JA_BASIC) == "ja"


def test_detect_language_picks_english():
    assert detect_language(_EN_NUMERIC) == "en"


def test_detect_language_none_on_pure_prose():
    assert detect_language(_NO_MARKERS) is None


def test_plaintext_auto_routes_to_detected_language():
    """language='auto' (or None) -> detector picks ZH -> chapters parsed via zh regex."""
    tree = parse_plain(_ZH_BASIC, language="auto")
    assert tree.detected_language == "zh"
    assert len(tree.parts[0].chapters) == 2


def test_plaintext_unknown_language_falls_back_single():
    tree = parse_plain(_NO_MARKERS, language="xx")
    assert tree.walker_path == "fallback_single"


def test_dispatcher_routes_plain():
    tree = parse("plain", _EN_NUMERIC, language="en")
    assert tree.source_format == "plain"


def test_detect_language_dict_order_is_loadbearing():
    """L1 regression-lock: _PATTERNS insertion order is the final tie-break
    for ZH-vs-JA ambiguous CJK input (both languages share `第N章`).
    Alphabetising or reordering this dict silently flips detection.
    """
    from loreweave_parse.plaintext_parser import _PATTERNS

    assert list(_PATTERNS.keys()) == ["en", "zh", "vi", "ja"], (
        "_PATTERNS dict order is load-bearing for tie-break in detect_language; "
        "do NOT reorder without updating test_detect_language_picks_chinese and friends"
    )
