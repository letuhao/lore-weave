"""T12 (partial) — the soft cap must be able to SAY what it dropped.

WHY THIS EXISTS. A 2026-09-06 human-sim run wrote 8 steering rules for a book and the model
generated against 3 of them for the entire run. The 5 dropped included the locked arc outline and
the corruption-tier mechanics — precisely the plot-critical content steering exists to protect.
Nothing in the UI said so; it was found only by reading container logs.

Issue #223 raised the cap 2000→8000, which fixes THAT book, and explicitly deferred the real
problem: a bible that genuinely outgrows the cap still loses rules silently. MCP Tool I/O's OUT-5
already states the rule — "never silently truncate: report the cap".

SCOPE OF THIS FILE: it covers the reporting PRIMITIVE only. Nothing user-visible has changed yet,
so T12 remains open — see the plan's row. These tests exist so the primitive is not untested code
sitting in the tree, and so the contract is pinned before anything is built on it.
"""
from __future__ import annotations

from app.services.steering import (
    STEERING_TOKEN_CAP,
    SteeringTruncation,
    select_steering,
    select_steering_ex,
)


def _rule(name: str, words: int = 5, mode: str = "always") -> dict:
    return {"name": name, "body": "word " * words, "inclusion_mode": mode}


def test_nothing_dropped_reports_no_truncation():
    """NV-7 — a signal that is always present carries no information."""
    selected, truncation = select_steering_ex([_rule("tone")], message="hello")
    assert len(selected) == 1
    assert truncation is None, "a fitting bible reported a truncation"


def test_a_dropped_rule_is_reported_with_its_NAME():
    """The count alone is not actionable. An author needs to know WHICH rules went missing —
    "5 dropped" does not tell you the arc outline was one of them."""
    big = [_rule(f"rule{i}", words=4000) for i in range(6)]
    selected, truncation = select_steering_ex(big, message="hello")

    assert isinstance(truncation, SteeringTruncation)
    assert truncation.dropped > 0
    assert len(truncation.dropped_names) == truncation.dropped
    assert all(n.startswith("rule") for n in truncation.dropped_names)
    # Dropping is from the TAIL, so the survivors are the head — `always` outlives the rest.
    kept_names = {e["name"] for e in selected}
    assert kept_names.isdisjoint(set(truncation.dropped_names))
    assert truncation.kept == len(selected)


def test_the_report_carries_the_budget_it_was_measured_against():
    """"Rules were dropped" is not actionable without the number they were measured against."""
    big = [_rule(f"rule{i}", words=4000) for i in range(6)]
    _selected, truncation = select_steering_ex(big, message="hello")
    assert truncation is not None
    assert truncation.cap_tokens == STEERING_TOKEN_CAP
    assert 0 < truncation.kept_tokens <= truncation.cap_tokens


def test_as_dict_is_serialisable_for_the_wire():
    big = [_rule(f"rule{i}", words=4000) for i in range(6)]
    _selected, truncation = select_steering_ex(big, message="hello")
    assert truncation is not None
    payload = truncation.as_dict()
    assert set(payload) == {"dropped", "dropped_names", "kept", "cap_tokens", "kept_tokens"}
    assert isinstance(payload["dropped_names"], list)


def test_the_list_only_wrapper_is_unchanged_for_existing_callers():
    """The whole point of keeping it: no existing caller or test had to change."""
    big = [_rule(f"rule{i}", words=4000) for i in range(6)]
    assert select_steering(big, message="hello") == select_steering_ex(big, message="hello")[0]
    assert isinstance(select_steering([_rule("tone")], message="hi"), list)


def test_an_empty_bible_is_not_a_truncation():
    assert select_steering_ex([], message="hi") == ([], None)
