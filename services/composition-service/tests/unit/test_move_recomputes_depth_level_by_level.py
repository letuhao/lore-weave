"""TOOLV2 LOOP #150 — a move silently produced a subtree past the depth cap.

composition_arc_move promises it "recomputes the whole moved subtree's depth" and rejects nesting
past saga→arc→sub-arc. The recompute was ONE recursive UPDATE touching every descendant at once,
relying on the BEFORE trigger to derive each row's depth from its parent.

Within a single statement the trigger fires per row in an unspecified order, so a grandchild could
be processed before its parent's new depth had been written and derive its own depth from the stale
value.

Measured live. After moving arc C from root to depth 1 under a saga:

    i150 saga  depth 0  ROOT
    i150 C     depth 1  under saga
    i150 A     depth 2  under C
    i150 B     depth 2  under A      <-- must be 3

B's parent sat at depth 2, so B was genuinely at depth 3 — past the cap this very tool advertises
— while recording 2. The trigger never objected because the depth it validated was the wrong one.
1 of 8 parented rows in the database was inconsistent, and it was the one that move had just
created.

A silent cap breach is worse than the refusal it replaced: the invariant still reads as held
everywhere that trusts the column.

The fix issues one statement per level, so each completes — and its triggers run — before the next
begins, leaving every parent correct when its children are recomputed.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "db" / "repositories" / "structure.py"
BODY = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def _move() -> str:
    start = BODY.index("    async def move(")
    nxt = BODY.index("\n    async def ", start + 10)
    return BODY[start:nxt]


def test_the_subtree_is_no_longer_recomputed_in_one_statement():
    m = _move()
    assert "WITH RECURSIVE sub AS" not in m, (
        "the single recursive UPDATE is back — trigger order within one statement is unspecified, "
        "so a grandchild can derive its depth from its parent's stale value"
    )


def test_each_level_is_its_own_statement():
    m = _move()
    assert "parent_ids = [node_id]" in m
    assert "WHERE parent_id = ANY($1::uuid[])" in m, (
        "levels must be driven by the previous level's ids, not by a recursive CTE"
    )
    assert "RETURNING id" in m, "without the returned ids there is no next level to walk"


def test_the_cascade_terminates_and_is_bounded():
    """Two ways to hang: a level that never empties, and a cycle in bad data. Both are bounded."""
    m = _move()
    assert "for _ in range(_MAX_SUBTREE_LEVELS):" in m
    assert re.search(r"if not rows:\n\s+break", m), "an empty level must end the walk"
    assert "_MAX_SUBTREE_LEVELS = 10" in BODY


def test_the_bound_is_not_the_current_depth_cap():
    """Hardcoding 2 would make a future cap change truncate the cascade silently — the same class
    of failure as the bug being fixed, just moved."""
    assert "_MAX_SUBTREE_LEVELS = 2" not in BODY
