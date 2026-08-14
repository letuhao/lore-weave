#!/usr/bin/env python
"""A superseded tool must not out-declare its successor.

🔴 THE DEFECT THIS CATCHES, MEASURED LIVE 2026-08-14. "Rename the chapter called The Ember Codex
in my outline to The Ember Codex Opens" routed to `composition_outline_node_update`, which is
marked `superseded_by: composition_outline_node_edit`. The DEPRECATED tool declares the words a
person actually types — "rename chapter", "edit scene", "update node". Its SUCCESSOR, the unified
entry point that exists to serve exactly those requests, declares "edit outline node", "manage
outline node" and a handful of CREATE verbs. So the successor was surfaced on 0 of 3 runs and the
request naming its precise job could not reach it.

Swept across the live federated catalogue: **59 of 62 supersession pairs orphan at least one
phrasing.** `book_get` → `book_read` loses "open book" and "show book". `book_scene_list` →
`book_list` loses "scenes" and "scene index". `composition_arc_create` → `composition_arc_edit`
loses "create story arc" and "start a saga". This is not a scatter of per-tool slips; it is the
predictable consequence of splitting or unifying a tool and leaving the synonyms on the old name.

Why a LINT and not 59 edits: an edit is correct the day it is made and silent the next time a tool
is superseded. The runtime union in `tool_surface.answerable_tools` keeps the surface correct
today; this makes the DECLARATIONS converge and fails the next pair automatically.

Usage:
    python scripts/lint_superseded_synonyms.py                  # against the cached catalogue
    python scripts/lint_superseded_synonyms.py --max-orphans 0  # enforce (exit 1 on any orphan)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "contracts" / "tool-catalog-cache.json"


def _syn(entry: dict) -> set[str]:
    meta = entry.get("meta") or {}
    for holder in (meta, meta.get("loreweave") or {}):
        v = holder.get("synonyms") if isinstance(holder, dict) else None
        if isinstance(v, list) and v:
            return {str(x).strip().lower() for x in v if isinstance(x, str)}
    return set()


def audit(cat: dict) -> list[dict]:
    out = []
    for name, entry in sorted(cat.items()):
        succ = (entry.get("meta") or {}).get("superseded_by")
        if not isinstance(succ, str) or not succ:
            continue
        old = _syn(entry)
        if succ not in cat:
            out.append({"tool": name, "successor": succ, "why": "successor not in the catalogue",
                        "orphans": sorted(old)})
            continue
        orphans = sorted(old - _syn(cat[succ]))
        if orphans:
            out.append({"tool": name, "successor": succ,
                        "why": "phrasings only the DEPRECATED tool claims", "orphans": orphans})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default=str(CACHE))
    ap.add_argument("--max-orphans", type=int, default=None,
                    help="fail when more pairs than this orphan a phrasing (0 = strict)")
    a = ap.parse_args()

    p = pathlib.Path(a.catalog)
    if not p.exists():
        print(f"no catalogue at {p} — run: python scripts/toolloop/catalog.py --refresh")
        return 2
    cat = json.loads(p.read_text(encoding="utf-8"))
    pairs = sum(1 for e in cat.values() if (e.get("meta") or {}).get("superseded_by"))
    bad = audit(cat)

    for b in bad:
        print(f"{b['tool']} -> {b['successor']}: {b['why']}")
        print(f"    {b['orphans']}")
    print(f"\n{pairs} supersession pair(s); {len(bad)} orphan at least one phrasing.")
    if not bad:
        print("Every superseded tool's vocabulary is claimed by its successor.")

    if a.max_orphans is None:
        # Report-only by default: 59 of 62 fail today, so a strict gate would block every
        # commit before the declarations are fixed. Pin --max-orphans in CI and ratchet it
        # down; a number that only ever decreases is a fix in progress, and a silent report
        # nobody enforces is not.
        return 0
    if len(bad) > a.max_orphans:
        print(f"FAIL: {len(bad)} > --max-orphans {a.max_orphans}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
