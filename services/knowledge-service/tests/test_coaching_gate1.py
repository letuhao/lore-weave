"""WS-5.7/5.8/5.9 — Gate-1 commitment schema + overdue detector.

The load-bearing test is `test_commitment_is_a_valid_fact_type_across_registries`: adding a
FactType member that misses ANY registry 500s at merge_fact (the WS-2.1 'statement' drift).
This asserts the SoT Literal + its derived tuple carry 'commitment' in lockstep.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.coaching import (
    OverdueCommitment, THREAD_OPEN, THREAD_RESOLVED,
    find_overdue_commitments, validate_thread_status,
)
from app.db.neo4j_repos.facts import FACT_TYPES, FactType
from app.db.models import FactType as ModelFactType
from typing import get_args


def test_commitment_is_a_valid_fact_type_across_registries():
    # SoT Literal + its runtime-derived tuple + the models.py mirror all carry 'commitment'.
    assert "commitment" in get_args(FactType)
    assert "commitment" in FACT_TYPES
    assert "commitment" in get_args(ModelFactType)


def test_overdue_detector_flags_past_due_unresolved_sorted():
    today = date(2026, 7, 15)
    commitments = [
        {"content": "ship the report", "due_date": "2026-07-10", "resolved": False},  # 5 overdue
        {"content": "book review", "due_date": "2026-07-14", "resolved": False},       # 1 overdue
        {"content": "already done", "due_date": "2026-07-01", "resolved": True},        # resolved → skip
        {"content": "future task", "due_date": "2026-07-20", "resolved": False},        # not yet due
    ]
    out = find_overdue_commitments(commitments, today)
    assert [o.content for o in out] == ["ship the report", "book review"]  # most-overdue first
    assert out[0].days_overdue == 5


def test_overdue_detector_skips_undated_and_malformed():
    today = date(2026, 7, 15)
    out = find_overdue_commitments(
        [{"content": "no date", "due_date": None}, {"content": "junk", "due_date": "not-a-date"}],
        today,
    )
    assert out == []


def test_due_today_is_not_overdue():
    out = find_overdue_commitments([{"content": "x", "due_date": "2026-07-15"}], date(2026, 7, 15))
    assert out == []  # strictly before today


def test_thread_status_closed_set():
    validate_thread_status(THREAD_OPEN)
    validate_thread_status(THREAD_RESOLVED)
    with pytest.raises(ValueError):
        validate_thread_status("in_progress")


def test_merge_fact_defaults_maintain_chain_false_for_new_writers():
    # WS-5.9 — the new commitment/thread writers go through the diary path and rely on the
    # SAFE DEFAULT (maintain_chain=False). Flipping it True would collapse the (subject,
    # fact_type) chain (every 'commitment' about a subject into one) — this guards the default.
    import inspect
    from app.db.neo4j_repos.facts import merge_fact
    assert inspect.signature(merge_fact).parameters["maintain_chain"].default is False
