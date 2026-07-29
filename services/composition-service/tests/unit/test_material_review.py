"""The review step, and the three buckets it sorts into.

Measured basis (POC §6f): the loop's earlier version concluded by itself — searched for the one kind
it thought was missing, found three lines, treated them as the answer, and all three were wrong. The
retrieval is good enough to SHOW and not good enough to TRUST, and only a human tells those apart.
"""

from __future__ import annotations

import json

import pytest

from app.engine.plan_forge.material_review import (
    _QUESTION,
    find_missing_material,
    kinds_to_ask,
    question_for,
)

DOC = "# Plan\n\n## World\nSalt only moves by sea. Debt only goes up, never down.\n"


def _spec(**over):
    base = {
        "meta": {"open_questions": [], "ingest_unread": {"unclassified": [], "note": ""}},
        "charter": {"style_constraints": [], "forbids": [], "consistency_anchors": []},
        "layers": {"characters": [{"name": "Mira"}], "mechanics": [], "variables": []},
        "arcs": [{"title": "A"}], "events": [], "links": [],
    }
    base.update(over)
    return base


class _LLM:
    """Per-kind canned payloads, keyed off the extractor tag `material_search` sets."""

    def __init__(self, by_kind: dict[str, object], raise_on: set[str] | None = None):
        self._by_kind = by_kind
        self._raise_on = raise_on or set()

    async def submit_and_wait(self, **kwargs):
        from types import SimpleNamespace
        kind = (kwargs["job_meta"]["extractor"] or "").split(":")[-1]
        if kind in self._raise_on:
            raise RuntimeError("boom")
        payload = self._by_kind.get(kind, {"quotes": []})
        content = payload if isinstance(payload, str) else json.dumps(payload)
        return SimpleNamespace(
            status="completed",
            result={"messages": [{"role": "assistant", "content": content}]},
        )


async def _run(by_kind, raise_on=None, spec=None, doc=DOC):
    return await find_missing_material(
        _LLM(by_kind, raise_on), user_id="u", model_source="user_model", model_ref="m",
        spec=spec or _spec(), document_markdown=doc,
    )


async def test_found_candidates_go_to_REVIEW_not_straight_into_the_plan():
    packet = await _run({"mechanics": {"quotes": [
        {"quote": "Salt only moves by sea.", "why": "a world rule"},
    ]}})
    kinds = {r["kind"] for r in packet["review"]}
    assert "mechanics" in kinds
    row = next(r for r in packet["review"] if r["kind"] == "mechanics")
    assert row["candidates"][0]["quote"] == "Salt only moves by sea."
    assert "mechanics" not in {a["kind"] for a in packet["ask"]}


async def test_an_HONEST_empty_search_becomes_a_question():
    packet = await _run({})   # every kind returns {"quotes": []}
    asked = {a["kind"] for a in packet["ask"]}
    assert "mechanics" in asked and "planner_variables" in asked
    assert all(a["question"] for a in packet["ask"])
    assert packet["unavailable"] == []


async def test_a_FAILED_search_is_UNAVAILABLE_and_never_becomes_a_question():
    """The bucket that matters most. Asking an author to write something they may already have
    written, because a model call failed, is the exact failure this cycle has been removing."""
    packet = await _run({"mechanics": ""})   # call_json -> None -> "did not complete"
    assert "mechanics" not in {a["kind"] for a in packet["ask"]}
    row = next(r for r in packet["unavailable"] if r["kind"] == "mechanics")
    assert "NOT evidence" in row["reason"]


async def test_an_ALL_INVENTED_search_is_UNAVAILABLE_too():
    """Nothing survived the grounding gate, so the search told us nothing about the document."""
    packet = await _run({"mechanics": {"quotes": [{"quote": "Nothing like this is in the doc."}]}})
    assert "mechanics" not in {a["kind"] for a in packet["ask"]}
    assert "mechanics" in {r["kind"] for r in packet["unavailable"]}


async def test_ONE_kind_raising_does_not_lose_the_others():
    packet = await _run({}, raise_on={"mechanics"})
    assert "mechanics" in {r["kind"] for r in packet["unavailable"]}
    assert "planner_variables" in {a["kind"] for a in packet["ask"]}


async def test_a_recovered_kind_is_never_searched_or_asked():
    packet = await _run({})
    assert "character_seed" in packet["recovered"]
    for bucket in ("review", "ask", "unavailable"):
        assert "character_seed" not in {r["kind"] for r in packet[bucket]}


async def test_dropping_every_candidate_turns_the_kind_BACK_into_a_question():
    """The whole point of the review step. The POC's auto-conclude treated three wrong lines as an
    answer and never asked; a keep-or-drop that cannot re-open the question is the same bug."""
    packet = await _run({"mechanics": {"quotes": [{"quote": "Salt only moves by sea."}]}})
    kept_none = kinds_to_ask(packet, kept={"mechanics": []})
    row = next(r for r in kept_none if r["kind"] == "mechanics")
    assert row["after_review"] == "all candidates were dropped"

    kept_one = kinds_to_ask(packet, kept={"mechanics": ["Salt only moves by sea."]})
    assert "mechanics" not in {r["kind"] for r in kept_one}


async def test_kinds_to_ask_NEVER_returns_an_unavailable_kind():
    """Whatever the author did, we still do not know the material is missing."""
    packet = await _run({"mechanics": ""})
    for kept in ({}, {"mechanics": []}, {"mechanics": ["x"]}):
        assert "mechanics" not in {r["kind"] for r in kinds_to_ask(packet, kept=kept)}


async def test_no_kept_argument_means_nothing_was_reviewed_yet():
    packet = await _run({"mechanics": {"quotes": [{"quote": "Salt only moves by sea."}]}})
    assert "mechanics" in {r["kind"] for r in kinds_to_ask(packet)}


def test_every_askable_kind_has_a_question():
    from app.engine.plan_forge.material_search import _KIND_MEANING

    assert set(_QUESTION) == set(_KIND_MEANING)
    with pytest.raises(ValueError, match="no question for"):
        question_for("protagonist_seed")


def test_no_question_carries_a_worked_example():
    """An example in a QUESTION tells the author what answer is expected, which defeats asking."""
    for kind, q in _QUESTION.items():
        low = q.lower()
        for tell in ("for example", "e.g.", "such as", "like ", "(e.g"):
            assert tell not in low, f"{kind}: the question leads the author — {tell!r}"


async def test_the_read_block_is_carried_so_thin_is_distinguishable_from_unread():
    spec = _spec()
    spec["meta"]["ingest_unread"] = {"unclassified": ["Giọt nước tràn ly"], "note": "1 section..."}
    packet = await _run({}, spec=spec)
    assert packet["read"]["unclassified"] == ["Giọt nước tràn ly"]
    # every not-recovered kind is `unknown` here, and that status rides through to the question
    assert all(a["status"] == "unknown" for a in packet["ask"])
