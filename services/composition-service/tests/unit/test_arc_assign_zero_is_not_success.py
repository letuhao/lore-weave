"""TOOLV2 LOOP #143 — composition_arc_assign_chapters reported doing nothing as success.

Measured on the tool's first ever invocation, against a real arc in a real book:

    unknown chapter_node_id   -> {"assigned": 0, "structure_node_id": "<arc>"}
    unknown structure_node_id -> {"assigned": 0, "structure_node_id": "<garbage>"}
    empty chapter_node_ids    -> {"assigned": 0, "structure_node_id": "<arc>"}

Three different mistakes, one success-shaped answer, mutually indistinguishable. A caller that
mistypes one uuid out of the two it must supply is told the write went through, having changed
nothing — and the repeated-failure breaker never fires either, because nothing failed.

The repository is right to no-op: its EXISTS guard is what stops an arc adopting another book's
chapters. What was missing is the handler saying so. The empty list stays a success on purpose —
asking to move no chapters is satisfied by moving none.

composition_arc_edit(op=assign_chapters) delegates to this same handler, so both surfaces are
covered by the one fix.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"
BODY = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def _handler() -> str:
    start = BODY.index("async def composition_arc_assign_chapters")
    end = BODY.index("\nasync def ", start + 10)
    return BODY[start:end]


def test_a_zero_with_chapters_named_is_not_returned_as_success():
    h = _handler()
    assert "if count == 0 and args.chapter_node_ids:" in h, (
        "a no-op assign is reported as success again — the caller cannot tell a typo from a write"
    )
    # The bare return must no longer be reachable for that case: the guard has to sit BEFORE it.
    guard = h.index("if count == 0 and args.chapter_node_ids:")
    ret = h.index('"assigned": count')
    assert guard < ret, "the diagnosis must precede the success return"


def test_the_two_causes_are_told_apart():
    """One message for both causes would only move the ambiguity into the sentence."""
    h = _handler()
    assert "structure_node_id is not an arc in this book" in h
    assert "none of those chapter_node_ids is an active CHAPTER-kind outline node" in h
    # Each names a satisfier, or the caller is stuck in the same place with a longer sentence.
    assert "composition_arc_list" in h
    assert "composition_list_outline" in h
    # The id-confusion this tool invites by name: these are OUTLINE NODE ids, not book chapter ids.
    assert "not book " in h and "chapter ids" in h


def test_an_empty_request_stays_a_success():
    """Asking to move no chapters is satisfied by moving none — erroring there would break the
    idempotent 'ensure unassigned' shape and give the model a failure it cannot act on."""
    h = _handler()
    assert re.search(r"if count == 0 and args\.chapter_node_ids:", h), "the empty case is guarded"
    assert "if count == 0:" not in h, (
        "an unconditional zero-check turns an empty request into an error"
    )
