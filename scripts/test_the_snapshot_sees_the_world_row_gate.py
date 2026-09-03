#!/usr/bin/env python3
"""The DATA bar must see a WORLD, not only a world's contents.

    python scripts/test_the_snapshot_sees_the_world_row_gate.py

🔴 THE DEFECT, and it is the seventh of its family and the first found INSIDE its own remedy.
`_world_counts` exists because the world/map store has no `book_id` and the DATA bar had therefore
never looked at it — its own docstring calls that "the worst thing this loop has found in its own
instrument". The function it produced counts `world_maps`, `map_regions` and `map_markers`: the
world's CONTENTS. It never counted the `worlds` row itself.

So deleting a MAP was visible and deleting a WORLD was not.

MEASURED 2026-08-23. The idempotency probe deleted a real world through `world_delete`, the tool
returned `{"deleted": true}`, and `store_diff` came back `{}`. The probe then reported "STRICTLY
IDEMPOTENT" and, to its credit, flagged its own verdict: *the first call changed nothing either, so
this probe measured two no-ops and proves nothing*. Without that warning the row would have been
recorded as an idempotency PASS for the most destructive tool in the cycle, on evidence that never
looked at the table the tool writes.

WHAT THIS PINS: `_world_counts` must report the `worlds` table for a world that exists. Asserted
against the live store rather than a string in the source, because the previous version of this
guard family was a source-text test that went red on a rename while the property it named still
held — a test that reads the code is not a test that runs it.
"""
from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAP = ROOT / "scripts" / "toolloop" / "store_snapshot.py"


def _load():
    spec = importlib.util.spec_from_file_location("ss", SNAP)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _a_real_world_id() -> str | None:
    r = subprocess.run(
        ["docker", "exec", "infra-postgres-1", "psql", "-U", "loreweave", "-d", "loreweave_book",
         "-tAc", "select id from worlds order by created_at desc limit 1;"],
        capture_output=True, text=True)
    wid = (r.stdout or "").strip()
    return wid or None


def main() -> int:
    ss = _load()
    wid = _a_real_world_id()
    if not wid:
        print("SKIP — no world row exists to measure against, so this gate cannot run.")
        print("      That is a skip, NOT a pass: it has verified nothing.")
        return 0

    got = ss._world_counts(wid)
    key = "loreweave_book.worlds"
    if key not in got:
        print(f"FAIL — _world_counts({wid[:8]}…) returned {got}")
        print(f"       it does not report {key!r}, so a DELETED WORLD is invisible to the DATA")
        print("       bar and 'store unchanged' means nothing for world_delete / world_update.")
        return 1

    rows = got[key].get("rows")
    if rows != 1:
        print(f"FAIL — {key} reports rows={rows!r} for a world that exists; expected 1")
        return 1

    # The control: the counts for a world that does NOT exist must not claim it is there.
    absent = ss._world_counts("00000000-0000-4000-8000-0000000000ff")
    if absent.get(key):
        print(f"FAIL — a nonexistent world still reports {key}: {absent[key]!r}")
        print("       the count is not scoped to the id, so it cannot attribute a change")
        return 1

    print(f"ok — _world_counts sees the world ROW ({key} rows=1), and reports nothing for an")
    print("     id that does not exist, so a world's deletion is attributable to the run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
