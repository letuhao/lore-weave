"""C18 — unit tests for parse_time_cue_to_iso (D-K19e-α-02 closer).

Pure-function tests; no I/O. Covers the 5 priority patterns + edge
cases (None / empty / vague / fictional-era / out-of-range year).
"""

from __future__ import annotations

import pytest

from app.utils.event_date_parser import parse_time_cue_to_iso


# ── happy patterns ─────────────────────────────────────────────────


def test_iso_full_date_passes_through():
    assert parse_time_cue_to_iso("1880-06-15") == "1880-06-15"


def test_iso_full_date_with_surrounding_whitespace():
    assert parse_time_cue_to_iso("  2026-04-25  ") == "2026-04-25"


def test_month_day_year_us_ordering():
    """'June 15, 1880' (US convention)."""
    assert parse_time_cue_to_iso("June 15, 1880") == "1880-06-15"


def test_month_day_year_no_comma():
    assert parse_time_cue_to_iso("June 15 1880") == "1880-06-15"


def test_day_month_year_uk_ordering():
    """'15 June 1880' (UK / European convention)."""
    assert parse_time_cue_to_iso("15 June 1880") == "1880-06-15"


def test_month_year_only():
    assert parse_time_cue_to_iso("June 1880") == "1880-06"


def test_season_year_spring():
    assert parse_time_cue_to_iso("spring 1880") == "1880-03"


def test_season_year_with_of():
    assert parse_time_cue_to_iso("the summer of 1880") == "1880-06"


def test_season_year_autumn_fall_synonyms():
    assert parse_time_cue_to_iso("autumn 1880") == "1880-09"
    assert parse_time_cue_to_iso("fall 1880") == "1880-09"


def test_season_year_winter():
    assert parse_time_cue_to_iso("winter 1880") == "1880-12"


def test_bare_year_in_isolation():
    assert parse_time_cue_to_iso("1880") == "1880"


def test_bare_year_embedded():
    assert parse_time_cue_to_iso("the year was 1880 when it happened") == "1880"


# ── negative cases (return None) ───────────────────────────────────


def test_none_input_returns_none():
    assert parse_time_cue_to_iso(None) is None


def test_empty_string_returns_none():
    assert parse_time_cue_to_iso("") is None


def test_vague_phrase_returns_none():
    """Most time_cue strings the LLM emits are vague — these MUST NOT
    fabricate dates."""
    assert parse_time_cue_to_iso("the next morning") is None
    assert parse_time_cue_to_iso("at dawn") is None
    assert parse_time_cue_to_iso("in his youth") is None
    assert parse_time_cue_to_iso("years later") is None


def test_fictional_era_returns_none():
    """ADR §6 (1) explicitly out-of-scope. Fictional eras stay in
    time_cue free-text only."""
    assert parse_time_cue_to_iso("TA 3019") is None
    assert parse_time_cue_to_iso("Year of the Dragon") is None


def test_year_out_of_range_returns_none():
    """[1000, 2999] only. Earlier years (medieval) and very-future
    sci-fi skipped to avoid false-positives on chapter numbers, page
    counts, or character ages."""
    assert parse_time_cue_to_iso("the year 999") is None
    assert parse_time_cue_to_iso("year 3000") is None  # outside [12]\d{3}
    assert parse_time_cue_to_iso("year 30000") is None  # \b excludes digit-runs


# ── pattern priority ───────────────────────────────────────────────


def test_full_iso_beats_bare_year():
    """Whole-string ISO match takes priority over the bare-year
    fallback."""
    assert parse_time_cue_to_iso("1880-06-15") == "1880-06-15"


def test_month_year_beats_bare_year():
    """When 'June 1880' appears in text, the month-year pattern wins
    over bare-year so we get '1880-06' not '1880'."""
    assert parse_time_cue_to_iso("In June 1880, the war began") == "1880-06"


def test_season_year_beats_bare_year():
    assert parse_time_cue_to_iso("It was summer 1880") == "1880-06"


def test_month_day_year_beats_month_year():
    """Full date wins over month-year when both could match."""
    assert parse_time_cue_to_iso("December 25, 1880 brought snow") == "1880-12-25"


# ── invalid month/day calendar checks ──────────────────────────────


def test_iso_full_invalid_month_returns_none():
    """1880-13-01 — month out of range. Whole-string ISO match
    fails calendar check → None (not a partial fallback)."""
    assert parse_time_cue_to_iso("1880-13-01") is None


def test_iso_full_invalid_day_returns_none():
    """1880-06-32 — day out of range."""
    assert parse_time_cue_to_iso("1880-06-32") is None


def test_month_day_year_invalid_day_falls_back_to_month_year():
    """'June 32, 1880' — day out of [1-31] — fall back to month-year
    '1880-06' so we don't drop the temporal signal entirely."""
    assert parse_time_cue_to_iso("June 32, 1880") == "1880-06"


# ── case insensitivity ─────────────────────────────────────────────


def test_uppercase_month_name():
    assert parse_time_cue_to_iso("JUNE 1880") == "1880-06"


def test_capitalized_season():
    assert parse_time_cue_to_iso("Summer 1880") == "1880-06"


# ── REVIEW-IMPL MEDIUM-2: BC/AD ambiguity (documented limitation) ──


def test_bc_year_silently_converts_to_ad():
    """REVIEW-IMPL MEDIUM-2 lock: '1880 BC' → '1880' (the bare-year
    regex doesn't see 'BC'). This is a KNOWN limitation documented
    in the parser docstring + ADR §6.11. Test asserts the actual
    behavior so a future fixer (or false-fix) is forced to update
    the test deliberately. Recovery path: LLM re-extraction or
    manual edit produces the correct event_date."""
    assert parse_time_cue_to_iso("1880 BC") == "1880"
    assert parse_time_cue_to_iso("the year 1880 BC") == "1880"


def test_ad_suffix_ignored_correctly():
    """'1880 AD' → '1880' (correct — suffix is just decorative)."""
    assert parse_time_cue_to_iso("1880 AD") == "1880"
