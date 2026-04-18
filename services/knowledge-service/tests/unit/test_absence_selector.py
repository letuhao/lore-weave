"""K18.5 — unit tests for the absence selector."""
from __future__ import annotations

from app.context.selectors.absence import detect_absences
from app.context.selectors.facts import L2FactResult


def test_all_covered_returns_empty():
    l2 = L2FactResult(background=["Arthur — trusts — Lancelot"])
    assert detect_absences(["Arthur", "Lancelot"], l2) == []


def test_uncovered_entity_flagged():
    l2 = L2FactResult(background=["Arthur — trusts — Lancelot"])
    assert detect_absences(["Arthur", "Morgana"], l2) == ["Morgana"]


def test_all_uncovered_when_l2_empty():
    assert detect_absences(["Arthur", "Morgana"], L2FactResult()) == [
        "Arthur", "Morgana",
    ]


def test_negative_bucket_counts_as_coverage():
    """A negation ("X does not know Y") still means we HAVE info
    about the entity — don't ask the user to clarify."""
    l2 = L2FactResult(negative=["Morgana does not know Merlin"])
    assert detect_absences(["Morgana", "Merlin", "Arthur"], l2) == ["Arthur"]


def test_case_insensitive_matching():
    l2 = L2FactResult(background=["arthur — trusts — lancelot"])
    assert detect_absences(["Arthur", "LANCELOT"], l2) == []


def test_order_and_dedup_preserved():
    l2 = L2FactResult()
    result = detect_absences(["Morgana", "Arthur", "Morgana"], l2)
    assert result == ["Morgana", "Arthur"]  # dedup while preserving order


def test_l3_hits_count_as_coverage():
    """L3 passages cover entities the L2 facts don't reach."""
    l2 = L2FactResult()
    l3 = ["A passage mentioning Galahad defeats the green knight."]
    assert detect_absences(["Galahad", "Arthur"], l2, l3_hits=l3) == ["Arthur"]


def test_empty_mentioned_list_returns_empty():
    assert detect_absences([], L2FactResult()) == []


def test_whitespace_entity_ignored():
    assert detect_absences(["", "   ", "Arthur"], L2FactResult()) == ["Arthur"]


def test_partial_substring_matches_and_has_known_trade_off():
    """Documents the substring-match trade-off: 'Arthur' counts as
    covered when 'Arthuria' is the only fact. This is acceptable —
    the resulting hint-level UI block gets one fewer entry, and the
    alternative (word-boundary matching) wouldn't help CJK."""
    l2 = L2FactResult(background=["Arthuria — rules — Camelot"])
    # Arthur gets "coverage" from Arthuria. Test locks this behavior.
    assert detect_absences(["Arthur"], l2) == []
