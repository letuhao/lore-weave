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


# ── what the author KEPT actually has to reach the plan ──────────────────────────────────────────

def test_a_kept_STRING_kind_lands_in_its_slot_verbatim():
    from app.engine.plan_forge.material_review import apply_kept_material

    spec = _spec()
    out, report = apply_kept_material(spec, {
        "writing_principles": ["No omniscient narrator. Ever."],
        "open_questions": ["Does she remember the first cycle?"],
    })
    assert out["charter"]["style_constraints"] == ["No omniscient narrator. Ever."]
    assert out["meta"]["open_questions"] == ["Does she remember the first cycle?"]
    assert report["applied_to_slot"] == {"writing_principles": 1, "open_questions": 1}
    assert report["carried_as_author_notes"] == {}


def test_a_kept_STRUCTURED_kind_is_carried_as_a_note_not_guessed_into_shape():
    """A variable is {code, name} and an arc is {id, title}; a raw sentence is neither. Inventing the
    missing fields is how a quote stops being a quote — the exact move `post_normalize_spec` and
    `_pad_traits_from_analyze` were removed for."""
    from app.engine.plan_forge.material_review import apply_kept_material

    out, report = apply_kept_material(_spec(), {
        "planner_variables": ["Ký ức ↓ Nhân cách ↓ Ý chí ↓ Đạo tâm ↓ Chân Linh"],
    })
    assert out["layers"]["variables"] == [], "a raw line was guessed into a variable object"
    notes = out["author_notes"]
    assert notes[0]["text"] == "Ký ức ↓ Nhân cách ↓ Ý chí ↓ Đạo tâm ↓ Chân Linh"
    assert "planner_variables" in notes[0]["title"]
    assert report["carried_as_author_notes"] == {"planner_variables": 1}
    assert report["applied_to_slot"] == {}


def test_the_report_distinguishes_filed_from_added():
    """"We filed it as a note" must never read as "we added your variable"."""
    from app.engine.plan_forge.material_review import apply_kept_material

    _, report = apply_kept_material(_spec(), {
        "writing_principles": ["Cold, procedural."],
        "mechanics": ["Salt only moves by sea."],
    })
    assert report["applied_to_slot"] == {"writing_principles": 1}
    assert report["carried_as_author_notes"] == {"mechanics": 1}


def test_apply_is_idempotent_and_does_not_mutate_the_input():
    from app.engine.plan_forge.material_review import apply_kept_material

    spec = _spec()
    kept = {"writing_principles": ["Cold, procedural."], "mechanics": ["Salt only moves by sea."]}
    once, _ = apply_kept_material(spec, kept)
    twice, report2 = apply_kept_material(once, kept)
    assert twice["charter"]["style_constraints"] == ["Cold, procedural."]
    assert len(twice["author_notes"]) == 1
    assert report2 == {"applied_to_slot": {}, "carried_as_author_notes": {}}
    assert spec["charter"]["style_constraints"] == [], "the input spec was mutated"


def test_no_model_is_involved():
    """Deterministic by construction — the module must not reach for an LLM on this path."""
    import inspect

    from app.engine.plan_forge.material_review import apply_kept_material

    src = inspect.getsource(apply_kept_material)
    for tell in ("call_json", "await", "llm", "search_material"):
        assert tell not in src, f"apply_kept_material reaches for {tell!r}"


# ── the ONE field a structured kind needs, and nobody may invent ─────────────────────────────────

def test_a_LABELLED_keep_lands_STRUCTURALLY_in_its_slot():
    """Reading the schemas back, each structured kind is short exactly one field a human must decide:
    a label. The quote is the body; only the name/title takes judgement. So ask for that, never guess
    it — and then a kept variable really is a variable."""
    from app.engine.plan_forge.material_review import apply_kept_material

    out, report = apply_kept_material(_spec(), {
        "planner_variables": [{"quote": "Ký ức mất dần từng lớp.", "label": "Ký ức"}],
        "mechanics": [{"quote": "Salt only moves by sea.", "label": "Salt logistics"}],
        "character_seed": [{"quote": "She returns each cycle.", "label": "Seraphine"}],
        "arc_overview": [{"quote": "Three cycles, each worse.", "label": "The Cycles"}],
    })
    var = out["layers"]["variables"][0]
    assert var["name"] == "Ký ức" and var["transition_rules"] == ["Ký ức mất dần từng lớp."]
    assert var["code"] == var["code"].upper() and var["code"], "a variable's identity is a CODE"

    mech = out["layers"]["mechanics"][0]
    assert mech["name"] == "Salt logistics" and mech["rules"] == ["Salt only moves by sea."]

    char = out["layers"]["characters"][-1]
    assert char["name"] == "Seraphine" and char["baseline_notes"] == "She returns each cycle."
    assert char["id"]

    arc = out["arcs"][-1]
    assert arc["title"] == "The Cycles" and arc["summary"] == "Three cycles, each worse."

    assert report["applied_to_slot"] == {
        "planner_variables": 1, "mechanics": 1, "character_seed": 1, "arc_overview": 1,
    }
    assert report["carried_as_author_notes"] == {}


def test_an_UNLABELLED_keep_still_falls_back_to_a_note():
    """The fallback is now a real outcome, not a shrug: author notes reach the pass prompts through
    PassContext.grounding. But it is still not a structured row, and the report says which."""
    from app.engine.plan_forge.material_review import apply_kept_material

    out, report = apply_kept_material(_spec(), {"planner_variables": ["Ký ức mất dần."]})
    assert out["layers"]["variables"] == []
    assert report["carried_as_author_notes"] == {"planner_variables": 1}


def test_identity_never_collides_with_a_row_the_author_already_has():
    from app.engine.plan_forge.material_review import apply_kept_material

    spec = _spec(layers={"characters": [{"id": "seraphine", "name": "Someone else"}],
                         "mechanics": [], "variables": []})
    out, _ = apply_kept_material(spec, {
        "character_seed": [{"quote": "x", "label": "Seraphine"}]})
    ids = [c["id"] for c in out["layers"]["characters"]]
    assert len(ids) == len(set(ids)), f"identity collided: {ids}"


def test_a_label_the_author_ALREADY_used_is_not_duplicated():
    """Keeping the same line twice, or re-keeping after a reload, must not grow the cast."""
    from app.engine.plan_forge.material_review import apply_kept_material

    kept = {"character_seed": [{"quote": "x", "label": "Seraphine"}]}
    once, _ = apply_kept_material(_spec(), kept)
    twice, report = apply_kept_material(once, kept)
    assert len(twice["layers"]["characters"]) == len(once["layers"]["characters"])
    assert report["applied_to_slot"] == {}


def test_a_string_entry_and_a_labelled_entry_can_share_one_call():
    from app.engine.plan_forge.material_review import apply_kept_material

    out, report = apply_kept_material(_spec(), {
        "mechanics": ["unlabelled line", {"quote": "labelled line", "label": "A rule"}]})
    assert out["layers"]["mechanics"][0]["name"] == "A rule"
    assert any("unlabelled line" == n["text"] for n in out["author_notes"])
    assert report == {"applied_to_slot": {"mechanics": 1},
                      "carried_as_author_notes": {"mechanics": 1}}
