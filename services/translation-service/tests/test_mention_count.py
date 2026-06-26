"""Tests for M7 per-chapter mention_count: the CJK-aware matcher, the alias-form
parsing, the window-merge SUM, presence-gating, and the recount core."""
from __future__ import annotations

from app.workers.mention_backfill import recount_chapter
from app.workers.mention_count import (
    build_surface_forms,
    count_entity_mentions,
    count_surface_form_mentions,
)


# ── matcher: CJK longest-match + span-dedup ──────────────────────────

def test_cjk_basic_count():
    # 林动 appears 3× in CJK prose with no spaces.
    text = "林动走进山洞，林动看见一把剑，林动拿起了它。"
    assert count_entity_mentions(text, "林动", []) == 3


def test_cjk_simplified_traditional_fold():
    # canonical traditional 張若塵; text uses simplified 张若尘 → folded match.
    text = "张若尘是主角，张若尘很强。"
    assert count_entity_mentions(text, "張若塵", []) == 2


def test_longest_match_span_dedup():
    # "Jonathan Harker" contains "Harker"; the full name must count ONCE, not twice.
    text = "Jonathan Harker arrived."
    assert count_entity_mentions(text, "Jonathan Harker", ["Harker"]) == 1


def test_alias_counted_when_standalone():
    # The short alias counts where the full name is absent.
    text = "Jonathan Harker arrived. Later, Harker left."
    # full name once + standalone alias once = 2.
    assert count_entity_mentions(text, "Jonathan Harker", ["Harker"]) == 2


def test_case_and_fullwidth_insensitive():
    text = "KAI and ｋａｉ and kai."  # uppercase, full-width, lowercase
    assert count_entity_mentions(text, "Kai", []) == 3


def test_no_match_returns_zero():
    assert count_entity_mentions("nothing here", "林动", ["Kai"]) == 0


def test_empty_inputs():
    assert count_entity_mentions("", "林动", []) == 0
    assert count_entity_mentions("林动", "", []) == 0


# ── surface-form building ────────────────────────────────────────────

def test_surface_forms_dedup_and_order():
    # Alias equal to the casefolded name collapses; forms sorted longest-first.
    forms = build_surface_forms("Kai", ["kai", "Kai the Brave"])
    assert forms[0] == "kai the brave"  # longest first
    assert forms.count("kai") == 1      # "Kai" and "kai" fold to one


def test_surface_forms_skip_blank():
    assert build_surface_forms("  ", ["", "  "]) == []


def test_count_surface_form_mentions_requires_prefolded():
    forms = build_surface_forms("林动", [])
    assert count_surface_form_mentions("林动林动", forms) == 2


# ── window-merge SUM (presence-gated by construction) ────────────────

def test_merge_sums_mention_count_across_windows():
    from app.workers.extraction_worker import _merge_window_entities

    chap = "11111111-1111-1111-1111-111111111111"
    # Same (kind, name) surfaced in two windows of the SAME chapter with counts 3 and 2.
    win_a = {"kind_code": "character", "name": "林动", "chapter_links": [
        {"chapter_id": chap, "chapter_index": 1, "relevance": "major", "mention_count": 3}]}
    win_b = {"kind_code": "character", "name": "林动", "chapter_links": [
        {"chapter_id": chap, "chapter_index": 1, "relevance": "major", "mention_count": 2}]}
    merged = _merge_window_entities([win_a, win_b])
    assert len(merged) == 1
    links = merged[0]["chapter_links"]
    assert len(links) == 1               # one chapter → one link
    assert links[0]["mention_count"] == 5  # 3 + 2 summed


def test_merge_keeps_distinct_chapters_separate():
    from app.workers.extraction_worker import _merge_window_entities

    ch1 = "11111111-1111-1111-1111-111111111111"
    ch2 = "22222222-2222-2222-2222-222222222222"
    e1 = {"kind_code": "character", "name": "林动", "chapter_links": [
        {"chapter_id": ch1, "chapter_index": 1, "mention_count": 4}]}
    e2 = {"kind_code": "character", "name": "林动", "chapter_links": [
        {"chapter_id": ch2, "chapter_index": 2, "mention_count": 7}]}
    merged = _merge_window_entities([e1, e2])
    assert len(merged) == 1
    by_chapter = {l["chapter_id"]: l["mention_count"] for l in merged[0]["chapter_links"]}
    assert by_chapter == {ch1: 4, ch2: 7}  # NOT summed across distinct chapters


# ── alias-form extraction from a parsed entity dict ──────────────────

def test_entity_alias_forms_list_and_string():
    from app.workers.extraction_worker import _entity_alias_forms

    assert _entity_alias_forms({"attributes": {"aliases": ["A", "B"]}}) == ["A", "B"]
    # delimiter-joined string forms (CJK + ascii separators).
    assert _entity_alias_forms({"attributes": {"aliases": "甲、乙，丙"}}) == ["甲", "乙", "丙"]
    assert _entity_alias_forms({"attributes": {}}) == []
    assert _entity_alias_forms({}) == []


# ── recount core (backfill) ──────────────────────────────────────────

def test_recount_chapter_returns_nonzero_only():
    forms = {
        "e-lin": build_surface_forms("林动", []),
        "e-absent": build_surface_forms("青檀", []),
    }
    text = "林动走进山洞，林动看见一把剑。"
    counts = recount_chapter(text, forms)
    assert counts == {"e-lin": 2}  # e-absent (0) omitted


def test_recount_chapter_empty_text():
    forms = {"e-lin": build_surface_forms("林动", [])}
    assert recount_chapter("", forms) == {}
