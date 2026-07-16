"""ACP A1 / RW-2 — characterization GOLDEN for the extracted pure functions.

These pin the EXACT current behavior of the rail verdict-machine + the executive
state-merge as they were in chat-service / knowledge-service, so the extraction is
proven byte-identical AND any future edit that changes an output REDs here. Expected
values are hand-derived from the (verbatim-moved) source — a true characterization test.
"""
from __future__ import annotations

from loreweave_agent_control import (
    DRIVE,
    STOP_DONE,
    BookState,
    build_messages,
    compute_rail_progress,
    merge_state,
    next_actionable_step,
    parse_done_when,
    redrive_directive,
    render_book_state,
    render_progress_block,
    user_abandoned_rail,
)

_CHARTER = {"goal": "g", "phases": ["warmup", "technical", "wrap"], "checklist": ["a", "b", "c"]}


# ── merge_state (executive core) ──────────────────────────────────────────────

def test_golden_merge_state_monotonic_union_and_phase_gate():
    old = {"phase": "technical", "covered": ["a", "b"]}
    llm = {"phase": "wrap", "covered": ["b", "c"], "redirect_hint": "hint", "drift_note": ""}
    assert merge_state(_CHARTER, old, llm) == {
        "phase": "wrap",            # in charter phases → accepted
        "covered": ["a", "b", "c"], # union, order-preserving, monotonic
        "elapsed_min": None,        # preserved (never computed here)
        "drift_note": None,         # "" → None
        "redirect_hint": "hint",
    }


def test_golden_merge_state_rejects_off_charter_phase():
    old = {"phase": "technical", "covered": []}
    llm = {"phase": "ESCAPED", "covered": [123, None, "x"]}
    got = merge_state(_CHARTER, old, llm)
    assert got["phase"] == "technical"  # kept
    assert got["covered"] == ["x"]       # non-strings dropped


# ── rail verdict machine ──────────────────────────────────────────────────────

_STEPS = [
    {"id": "s1", "tool": "t1", "done_when": "cast > 0"},
    {"id": "s2", "tool": "t2", "done_when": "plan > 0"},
]


def test_golden_compute_progress_artifact_wins():
    prog = compute_rail_progress("demo", _STEPS, BookState(cast=3, plan=0), set())
    assert [s.done for s in prog.steps] == [True, False]
    assert prog.next_index == 2
    verdict, step = next_actionable_step(prog, _STEPS, set())
    assert verdict == DRIVE
    assert step.step_id == "s2"


def test_golden_all_done_is_stop_done():
    prog = compute_rail_progress("demo", _STEPS, BookState(cast=3, plan=1), set())
    assert prog.all_done
    assert next_actionable_step(prog, _STEPS, set()) == (STOP_DONE, None)


def test_golden_parse_done_when():
    assert parse_done_when("cast > 0") == ("cast", ">", 0)
    assert parse_done_when("suggestions <= 1") == ("suggestions", "<=", 1)
    assert parse_done_when("nonsense") is None
    assert parse_done_when("unknown_key > 1") is None


def test_golden_render_book_state_labels_and_order():
    got = render_book_state(BookState(cast=3, plan=0))
    assert got == "characters/places saved: 3 · arc plan proposed (1 = yes): 0"


def test_golden_render_progress_block_shape():
    prog = compute_rail_progress("demo", _STEPS, BookState(cast=3, plan=0), set())
    block = render_progress_block(prog)
    assert "WHERE THE BOOK ACTUALLY IS" in block
    assert "ALREADY DONE for this book" in block and "s1" in block
    assert 'step 2 of 2, "s2" → `t2`' in block


def test_golden_redrive_directive_confirm_token_hint():
    from loreweave_agent_control.rail import StepProgress

    plain = redrive_directive(StepProgress(1, "s2", "t2", False, ""))
    assert "call `t2`" in plain and "confirmation token" not in plain
    conf = redrive_directive(StepProgress(1, "s3", "glossary_confirm_action", False, ""))
    assert "EXACT confirmation" in conf


def test_golden_user_abandoned_rail_matcher():
    assert user_abandoned_rail("skip the plan") is True
    assert user_abandoned_rail("just write") is True
    assert user_abandoned_rail("let's keep building the world") is False


def test_golden_build_messages_caps_turn():
    msgs = build_messages(_CHARTER, {"phase": "", "covered": []}, [{"role": "user", "content": "x" * 50000}])
    assert msgs[0]["role"] == "system"
    assert len(msgs[1]["content"]) < 10000  # the 2000-char per-turn cap bounds it
