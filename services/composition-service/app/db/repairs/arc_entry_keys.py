"""D-ARC-TRACKS-ROSTER-SCHEMA (spec 32a §A.3) — on-demand, idempotent repair of legacy
`structure_node.tracks`/`.roster` entries whose `key` is missing, empty, or duplicated
within a node.

WHY a script and not a boot migration: reads already tolerate the garbage (`_merge_by`
keeps un-keyable entries individually), the write doors now REJECT new garbage (arc.py +
server.py), so the only thing a legacy garbage row blocks is a re-SAVE. A once-off repair
belongs on-demand, not on every service boot. The dev DB scanned clean (4 nodes, 0 bad)
on 2026-07-16; this exists for a real deployment that scans dirty.

NON-DESTRUCTIVE BY CONSTRUCTION: an entry is never dropped. A missing/empty key becomes a
stable positional key (`<prefix>_<ord>`); a genuine within-node duplicate is suffixed
(`_2`, `_3`). Re-running finds nothing to change (idempotent).

Usage:
    python -m app.db.repairs.arc_entry_keys --scan       # read-only report
    python -m app.db.repairs.arc_entry_keys --apply      # repair + report
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any


def repair_entries(entries: list[dict[str, Any]], *, prefix: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (repaired_entries, notes). Pure: no I/O. `prefix` is 'track'/'role'.

    - a missing or empty `key` → a positional `<prefix>_<ord>` (0-based, by position);
    - a within-node duplicate `key` → the 2nd+ occurrence is suffixed `_2`, `_3`, …;
    - every other entry is untouched, and NO entry is ever removed.
    Idempotent: applied to an already-repaired list it makes no change and returns [] notes.
    """
    out: list[dict[str, Any]] = []
    notes: list[str] = []
    seen: set[str] = set()
    for ord_, entry in enumerate(entries):
        e = dict(entry)  # never mutate the caller's dict
        key = e.get("key")
        if not isinstance(key, str) or key == "":
            key = f"{prefix}_{ord_}"
            notes.append(f"[{ord_}] missing/empty key → '{key}'")
        if key in seen:
            base, n = key, 2
            while f"{base}_{n}" in seen:
                n += 1
            new_key = f"{base}_{n}"
            notes.append(f"[{ord_}] duplicate key '{key}' → '{new_key}'")
            key = new_key
        seen.add(key)
        e["key"] = key
        out.append(e)
    return out, notes


def _repair_node(tracks: list[dict], roster: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    rt, nt = repair_entries(tracks or [], prefix="track")
    rr, nr = repair_entries(roster or [], prefix="role")
    return rt, rr, [*(f"tracks{n}" for n in nt), *(f"roster{n}" for n in nr)]


async def _run(apply: bool) -> int:
    # Imported lazily so the pure `repair_entries` above stays import-cheap + unit-testable
    # without the DB stack.
    from app.db.pool import get_pool

    pool = get_pool()
    touched: list[dict[str, Any]] = []
    async with pool.acquire() as c:
        rows = await c.fetch(
            "SELECT id, tracks, roster FROM structure_node "
            "WHERE jsonb_typeof(tracks)='array' OR jsonb_typeof(roster)='array'"
        )
        for r in rows:
            tracks = json.loads(r["tracks"]) if isinstance(r["tracks"], str) else (r["tracks"] or [])
            roster = json.loads(r["roster"]) if isinstance(r["roster"], str) else (r["roster"] or [])
            rt, rr, notes = _repair_node(tracks, roster)
            if not notes:
                continue
            touched.append({"id": str(r["id"]), "notes": notes})
            if apply:
                await c.execute(
                    "UPDATE structure_node SET tracks=$2::jsonb, roster=$3::jsonb, updated_at=now() WHERE id=$1",
                    r["id"], json.dumps(rt), json.dumps(rr),
                )
    verb = "REPAIRED" if apply else "WOULD REPAIR"
    print(f"{verb} {len(touched)} node(s):")
    print(json.dumps(touched, indent=2, ensure_ascii=False))
    return len(touched)


def main() -> None:
    ap = argparse.ArgumentParser(description="Repair legacy arc track/roster entry keys (non-destructive).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--scan", action="store_true", help="read-only report of what would change")
    g.add_argument("--apply", action="store_true", help="repair the rows and report")
    args = ap.parse_args()
    asyncio.run(_run(apply=args.apply))


if __name__ == "__main__":
    main()
