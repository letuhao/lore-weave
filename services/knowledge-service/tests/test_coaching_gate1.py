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


def _literal_members(tp) -> tuple:
    """Flatten a Literal — or a UNION of Literals — to its member strings.

    T48b: `get_args(FactType)` returned the member strings while `FactType` was ONE Literal.
    `:Fact` then gained the story extractor's vocabulary and the type became
    `Union[Literal[memory…], Literal[story…]]`, at which point `get_args` returns the two
    LITERAL TYPES and `"commitment" in …` is false against a registry that carries it.

    The widening was correct and the tests were stale — but nobody saw it, because these two
    ran only with the rest of the file and this file had been red on every run for weeks
    while 728 other tests were dark (T48a).
    """
    out: list = []
    for arg in get_args(tp):
        out.extend(_literal_members(arg) if get_args(arg) else [arg])
    return tuple(out)


def test_commitment_is_a_valid_fact_type_across_registries():
    # SoT Literal + its runtime-derived tuple + the models.py mirror all carry 'commitment'.
    assert "commitment" in _literal_members(FactType)
    assert "commitment" in FACT_TYPES
    assert "commitment" in _literal_members(ModelFactType)
    # The flattener must not pass by returning everything: a type that does NOT carry it
    # has to come back without it, or the three assertions above are unfalsifiable.
    from typing import Literal as _L
    assert "commitment" not in _literal_members(_L["description", "attribute"])


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


def test_kg_propose_fact_enum_derives_from_sot_no_drift():
    # cold-review MED-1 — the advertised kg_propose_fact enum must equal the SoT (it had drifted
    # to a stale 4-type tuple missing 'statement' + 'commitment').
    from app.db.neo4j_repos.facts import MEMORY_FACT_TYPES, STORY_FACT_TYPES
    from app.tools.graph_schema_tools import _PROPOSE_FACT_TYPES

    # T48b — this asserted `== set(FACT_TYPES)` and went stale on 2026-08-11, when `:Fact`
    # gained the story vocabulary and the enum was DELIBERATELY narrowed. The adapter says
    # why in its own comment: "this enum advertises what the pending-facts INBOX accepts,
    # and that path stayed memory-only". So the SoT this derives from is MEMORY_FACT_TYPES,
    # and asserting the wider set demanded a drift the code had decided against.
    assert set(_PROPOSE_FACT_TYPES) == set(MEMORY_FACT_TYPES)
    assert "commitment" in _PROPOSE_FACT_TYPES
    # The narrowing is the POINT, so it gets its own assertion: advertising a story type on
    # the memory inbox is the drift in the other direction, and the original defect this
    # test was written for was exactly a hand-kept tuple disagreeing with its source.
    assert not set(_PROPOSE_FACT_TYPES) & set(STORY_FACT_TYPES), (
        "the pending-facts inbox is advertising story-extractor types it does not accept"
    )
