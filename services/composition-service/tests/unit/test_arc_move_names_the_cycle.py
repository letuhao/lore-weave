"""TOOLV2 LOOP #150 — a cycle was refused with the WRONG reason.

composition_arc_move's description promises four rejections: a saga given a parent, nesting past
saga→arc→sub-arc, a cycle, and a cross-book parent. All four hold — the write is correctly refused
every time, and the `detail` field carries the database's own message, which distinguishes three of
them:

    depth           -> "structure_node depth 3 exceeds saga→arc→sub-arc"
    unknown parent  -> "structure_node parent 019f0000-… not found"
    saga-with-parent-> violates check constraint "structure_saga_is_root"
    cycle           -> "structure_node depth 3 exceeds saga→arc→sub-arc"   <-- wrong cause

The trigger checks depth BEFORE it walks for a cycle, and the cap is depth 2, so moving a node
under its own descendant almost always trips the depth branch first. Measured: arc A (depth 1)
moved under its own child B (depth 2) was refused as a depth violation.

The data stays safe either way; what breaks is the caller. Told "depth 3 exceeds", a model looks
for a shallower parent — advice that cannot succeed, because the problem is that the target sits
beneath the node being moved. Misattributed blame is the failure mode that makes a model
unrecoverable: it will keep trying variations of the wrong fix.

The DB trigger remains the integrity SSOT. This adds a diagnosis for the one case its ordering
hides, and only that case.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"
BODY = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def _move_handler() -> str:
    start = BODY.index("async def composition_arc_move(")
    nxt = BODY.find("\nasync def ", start + 10)
    return BODY[start: nxt if nxt != -1 else len(BODY)]


def test_the_move_walks_for_a_cycle_before_letting_the_trigger_answer():
    h = _move_handler()
    assert "if walker == node.id:" in h, (
        "the cycle is no longer detected here, so the depth guard reports it as a depth problem"
    )
    # It must run BEFORE the repo call, or the trigger has already produced the wrong message.
    assert h.index("if walker == node.id:") < h.index("moved = await structures.move("), (
        "the pre-check must precede the move, not explain it afterwards"
    )


def test_the_cycle_message_names_the_relationship_and_a_way_out():
    h = _move_handler()
    assert "own descendant" in h, "the caller needs the actual relationship, not a rule list"
    # A refusal without a next action is what the depth message already failed at.
    assert "composition_arc_list" in h
    assert "detail" in h and "cycle:" in h


def test_the_walk_cannot_hang_on_pre_existing_bad_data():
    """The trigger prevents cycles, so the tree should be acyclic — but a guard that would spin
    forever if it ever were not is a worse failure than the one it fixes."""
    h = _move_handler()
    assert "seen: set = set()" in h
    assert "walker not in seen" in h


def test_a_move_with_no_new_parent_skips_the_walk_entirely():
    """new_parent_arc_id=None means 'make it a root', which can never be a cycle; paying for a
    tree walk there would tax the common reorder case."""
    h = _move_handler()
    guard = re.search(r"if args\.new_parent_arc_id:\n(\s+)walker = ", h)
    assert guard, "the walk must be conditional on a parent actually being supplied"
