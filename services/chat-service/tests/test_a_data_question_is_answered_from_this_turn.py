"""DQ-T30 — a question naming stored data must be answered from a tool call in THIS turn.

MEASURED LIVE 2026-08-13, session 019ff929, book 019ff8f5, with TWO active canon_rule rows:

    'Sat khi luon tieu hao tuoi tho — magic always costs lifespan'
    'The Obsidian Trench never appears on two maps at once'

  Turn A (the rail drove):  tool called, answer correct.
  Turn B (rail now 3/3, "guards held but no actionable step"):
        ZERO tool calls -> answered "one rule"  (the count from the earlier turn)
  Turn C (told a rule had been added):
        ZERO tool calls -> "I have checked your consistency rules again", and INVENTED
        'The world is constantly rewriting itself through shifting geography'

The store was untouched on both turns, so every write-side guard is silent BY CONSTRUCTION —
`_narrated_uncalled_writes` intersects prose with WRITE tools, and its docstring used to call a
named-but-uncalled read "harmless: nothing was claimed to have changed". The harm is not in the
store. It is in the ANSWER: the author is told something false about their own book.

THE INVARIANT: an answer that states stored data must come from a read performed in THIS turn.

Owner's decision on DQ-T30, 2026-08-14: option (c), the general fix — independent of any rail.
The two rail-scoped options ((a) a read step never latches done, (b) a freshness window) were
rejected because a COMPLETED rail is exactly the failing case: it is right for a finished rail to
stop driving, and wrong for the turn to stop reading.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.stream_service import (  # noqa: E402
    DATA_QUESTION_NUDGE_CAP,
    _unanswered_data_question_reads,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
SRC = (pathlib.Path(__file__).resolve().parents[1]
       / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")

#: The tool's REAL declaration, copied from the live federated catalogue (see
#: `test_the_fixture_still_matches_the_live_declaration`, which fails if it drifts).
CANON_SYNONYMS = ["canon rules", "invariants", "lore rules", "constraints", "list canon"]

#: The author's words on the measured turn.
MEASURED_QUESTION = "What canon rules have I declared for this book?"


def _tool(name: str, tier: str, synonyms: list[str]) -> dict:
    """The OpenAI-shaped def `_catalog_index` builds: name and _meta live under `function`."""
    return {"type": "function", "function": {
        "name": name, "description": name + " description",
        "_meta": {"tier": tier, "synonyms": synonyms, "scope": "book"},
    }}


CATALOG = {
    "composition_list_canon_rules": _tool("composition_list_canon_rules", "R", CANON_SYNONYMS),
    # A WRITE that the SAME words reach — the sister guard's business, never this one's.
    "composition_declare_canon_rule": _tool(
        "composition_declare_canon_rule", "W", ["declare canon rule", "add canon rules"]),
}


def test_the_measured_turn_is_caught():
    """THE FALSIFIER. Turn B/C exactly: the question declares a read, and nothing ran."""
    assert _unanswered_data_question_reads(
        MEASURED_QUESTION, catalog_index=CATALOG, attempted=set(),
    ) == ["composition_list_canon_rules"], (
        "the turn answered a data question from conversation memory and nothing was "
        "accountable for re-reading the store"
    )


def test_a_read_that_ran_satisfies_the_rule():
    """Turn A — the rail drove, the tool ran, the answer was right. (c) is satisfied by ANY of
    the answering reads having run, so this must stay silent or it would nudge a correct turn."""
    assert _unanswered_data_question_reads(
        MEASURED_QUESTION, catalog_index=CATALOG,
        attempted={"composition_list_canon_rules"},
    ) == []


def test_a_read_that_was_tried_and_failed_is_not_nudged():
    """`attempted` counts failures too, exactly as the sister guard counts them: a model that
    called and got a real error already has honest feedback, and nudging there is noise. The
    guard cannot tell the two apart, and that is deliberate — it is why this test names the
    failed case separately from the succeeded one above."""
    assert _unanswered_data_question_reads(
        MEASURED_QUESTION, catalog_index=CATALOG,
        attempted={"composition_list_canon_rules"},
    ) == []


def test_a_write_matched_by_the_same_words_is_never_nudged():
    """Nudging a WRITE out of a QUESTION would be this loop's own worst defect — it is how a
    read-intent turn ends up changing the store. Only the READ may ever be returned."""
    out = _unanswered_data_question_reads(
        "Add canon rules to this book", catalog_index=CATALOG, attempted=set(),
    )
    assert "composition_declare_canon_rule" not in out


def test_chitchat_forces_nothing():
    """Precision comes from the declarations, not from tuning. A request that names no stored
    data matches no synonym and must leave the turn alone."""
    assert _unanswered_data_question_reads(
        "thanks, that is great", catalog_index=CATALOG, attempted=set(),
    ) == []
    assert _unanswered_data_question_reads(
        None, catalog_index=CATALOG, attempted=set()) == []


def test_a_withheld_read_is_STILL_named_and_is_armed_by_the_call_site():
    """🔴 THE FIRST VERSION OF THIS GUARD REQUIRED THE TOOL TO BE ON THE WIRE, AND MEASUREMENT
    KILLED THAT. Live 2026-08-14, session 019ffff4: turn 1 called composition_list_canon_rules
    and answered correctly; the RE-ASK did not, and that turn's `advertised_tools` did NOT
    contain the tool. So the guard fired, named a tool the model could not call, and the model
    took the honest-disclosure branch — "I did not re-read the book on this turn, so my answer
    may be stale" — after thrashing through TWELVE other composition tools hunting for it.

    The sister guard already carries the lesson: a directive to call it now is empty if the tool
    is not on the wire, and OFF-SURFACE is the usual reason the model did not call it. So the
    guard names it regardless of the wire and the CALL SITE arms it.

    A withheld answerable read remains a SURFACING defect with its own row — arming is a repair
    at the answer boundary, never a substitute for putting the tool on the wire."""
    assert _unanswered_data_question_reads(
        MEASURED_QUESTION, catalog_index=CATALOG, attempted=set(),
    ) == ["composition_list_canon_rules"]


def test_the_call_site_arms_what_it_names():
    """CALL-SITE GUARD for the arming, because the helper cannot express it. Without this the
    directive is ceremony in exactly the case the guard exists for."""
    i = SRC.index("_unread = _unanswered_data_question_reads(")
    block = SRC[i:i + 3000]
    assert "_dq_armed = [" in block
    # 🔴 RETARGETED 2026-08-22, and the INTENT is unchanged: this site must still arm what it
    # names. It asserted the mutation inline (`active_tool_names.update(_dq_armed)` +
    # `merge_activated_tools(`) — three copies of that mutation existed and a fourth path, the
    # missing-argument refusal, had none, so a refusal saying "call world_map_list first" armed
    # nothing and the model was told to call a tool that was not on the turn (measured: supplier
    # advertised on 0/5 runs). The mutation now lives in `_arm_tools`, so pinning its old inline
    # spelling here would pin the shape that made the omission possible.
    assert "_arm_tools(" in block, "the DQ-T30 arm names tools it never puts on the wire"
    assert "_dq_armed, active_tool_names=active_tool_names" in block, (
        "it arms SOMETHING, but not the set it just computed and is about to name"
    )


def test_the_fixture_still_matches_the_live_declaration():
    """The whole guard keys on the tool's OWN declared vocabulary. If that declaration changes
    and this fixture does not, every test above would keep passing against words the platform no
    longer ships — green over a surface that cannot answer."""
    cache = REPO / "contracts" / "tool-catalog-cache.json"
    if not cache.exists():
        return
    live = json.loads(cache.read_text(encoding="utf-8")).get("composition_list_canon_rules")
    if not live:
        return
    meta = live.get("meta") or {}
    assert meta.get("tier") == "R", "the guard only ever returns READS"
    assert "canon rules" in (meta.get("synonyms") or []), (
        "the measured question reaches this tool through the synonym 'canon rules'"
    )


def test_the_cap_is_one():
    """Capped for the same reason its write twin is: a guard that exists to stop a model
    answering without looking must never become the loop it prevents."""
    assert DATA_QUESTION_NUDGE_CAP == 1


def test_the_chokepoint_calls_it_and_takes_no_rail_input():
    """CALL-SITE GUARD. The pure function above stays green even if it is never wired in — and
    'independent of any rail' is the substance of decision (c), so the call must not be gated on
    rail state the way the write-side stalled-step arm deliberately is."""
    i = SRC.index("_unread = _unanswered_data_question_reads(")
    call = SRC[i:i + 400]
    assert "request_text" in call and "attempted=turn_attempted" in call
    for railish in ("rail_progress", "rail_specs", "rail_intent_slugs", "rail_book_id"):
        assert railish not in call, (
            "the guard must not read " + railish + ": a COMPLETED rail is the case DQ-T30 "
            "measured, so gating on rail state would reintroduce the defect"
        )


def test_it_runs_only_when_the_write_guards_did_not_claim_the_turn():
    """A narrated write is the more damaging failure and owns the single directive slot when
    both fire — the two must not both append a directive in one pass."""
    i = SRC.index("_unread = _unanswered_data_question_reads(")
    assert SRC.index("if _narrated:") < i, (
        "the narrated-write block must be evaluated first; it `continue`s when it fires"
    )
