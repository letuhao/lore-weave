"""A2/A3 (ML-3) — unit tests for the shared script-range primitives that make
proper-noun / candidate detection script-aware (Vietnamese diacritics, Japanese
kana, Korean hangul) instead of English-only.
"""

from __future__ import annotations

import pytest

from app.extraction.scripts import (
    CJK_FAMILY_RUN_RE,
    LATIN_NAME_RE,
    is_cjk_family,
    split_cjk_run,
)


# ── LATIN_NAME_RE: Vietnamese-diacritic aware capitalized phrases ────────────

@pytest.mark.parametrize(
    "text,expected",
    [
        ("Master Kai met Lin", ["Master Kai", "Lin"]),          # English unchanged
        ("Nguyễn Văn gặp Trần Đường", ["Nguyễn Văn", "Trần Đường"]),  # vi diacritics
        ("Lê Thị Hương", ["Lê Thị Hương"]),                     # 3-word vi name
        ("Ước mơ của Đường", ["Ước", "Đường"]),                 # Ư/Đ initials, verb 'của' skipped
    ],
)
def test_latin_name_detects_vietnamese(text, expected):
    assert LATIN_NAME_RE.findall(text) == expected


def test_latin_name_does_not_shred_diacritic_name():
    # The old `[A-Z][a-z]+` captured only "Nguy" from "Nguyễn". The widened
    # class keeps the whole token.
    assert "Nguyễn" in LATIN_NAME_RE.findall("Nguyễn smiled")


# ── CJK_FAMILY_RUN_RE: Han + kana + hangul ──────────────────────────────────

def test_cjk_family_run_matches_kana_and_hangul():
    assert CJK_FAMILY_RUN_RE.findall("カイと田中") == ["カイと田中"]     # katakana + han
    assert CJK_FAMILY_RUN_RE.findall("김철수는 왔다") == ["김철수는", "왔다"]  # hangul
    assert CJK_FAMILY_RUN_RE.findall("こんにちは") == ["こんにちは"]        # hiragana


def test_cjk_family_run_ignores_single_char():
    # 2+ chars required — a lone ideograph between latin is not a run.
    assert CJK_FAMILY_RUN_RE.findall("a田b") == []


# ── split_cjk_run: soft particle segmentation (zh + ja, not ko) ──────────────

def test_split_cjk_run_splits_chinese_particle():
    assert split_cjk_run("告诉我关于李雲的故事") == ["告诉我关于李雲", "故事"]


def test_split_cjk_run_splits_japanese_hiragana_particle():
    assert split_cjk_run("田中は学校へ行った") == ["田中", "学校", "行った"]


def test_split_cjk_run_keeps_korean_whole():
    # Korean josa (는) is NOT a split particle — splitting would shred names
    # like 지은/서은. The whole run stays.
    assert split_cjk_run("김철수는") == ["김철수는"]


def test_split_cjk_run_drops_short_segments():
    # 凯 alone (len 1) after splitting on 了 is dropped.
    assert split_cjk_run("凯了") == []


# ── is_cjk_family ────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "ch,expected",
    [("田", True), ("カ", True), ("가", True), ("ひ", True),
     ("A", False), ("é", False), ("1", False), ("", False)],
)
def test_is_cjk_family(ch, expected):
    assert is_cjk_family(ch) is expected
