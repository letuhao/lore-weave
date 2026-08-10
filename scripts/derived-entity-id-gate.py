#!/usr/bin/env python3
"""derived-entity-id-gate — `Entity.id = hash(name, kind)` gains no NEW callers (plan T35).

WHY THE DERIVED ID IS BEING RETIRED
-----------------------------------
`entity_canonical_id(user_id, project_id, name, kind)` (sdks/python/loreweave_extraction/
canonical.py) derives an entity's node id as a truncated SHA-256 of its canonicalised **name
and kind**. `glossary_sync.py` recomputes it on every sync — but the MERGE's `ON MATCH SET`
never rewrites `e.id`. So a rename or a re-kind leaves a node whose id contradicts its own
properties, and that id is what the graph joins on.

**The failure is silent.** A stale derived id does not raise: it joins to nothing, or to the
wrong node. Nothing errors, a query simply returns less than it should — which is why the
2026-08-02 kind backfill could leave 77 disagreeing nodes without anyone noticing.

WHY A GATE INSTEAD OF THE MIGRATION
-----------------------------------
T35 replaces this with opaque identity keyed on the stable glossary anchor. Re-measured on the
live graph 2026-08-11: **6297 Entity nodes carry an id, 5776 already carry the anchor** — ~92 %
of the target already exists. What remains is retiring the derived id and repointing the join
sites, across a live graph, with the silent failure mode above.

That is a whole-context change, and starting it without finishing it is the one outcome worse
than not starting: a half-migrated graph gives no way to tell which half is which. So the
blast radius is frozen instead — **the caller set can only shrink**, and the list below is the
migration checklist. See `D-T35-OPAQUE-IDENTITY` in the plan.

    python scripts/derived-entity-id-gate.py

Exit 0 = the caller set is unchanged or smaller · 1 = it grew, or the baseline is stale.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_ROOT = os.path.join(ROOT, "services", "knowledge-service", "app")

# Every non-test caller of the derived id, with what it does. Each entry must eventually move
# onto the opaque anchor; the list IS the T35 checklist.
# ⚠️ This list started at ELEVEN and the gate corrected it to FIVE on its first run. A plain
# `grep entity_canonical_id` matches imports, comments and docstrings — six of the eleven only
# MENTION the function. Sizing T35 off the grep would have over-stated the migration by 2.2x,
# and an over-stated checklist hides the real remainder inside noise (the same mistake T17's
# "still owed" paragraph made). These five actually CALL it.
BASELINE = {
    os.path.join("adapters", "fake_graph_store.py"):            "test double — mirrors the real adapter's key, so it must move WITH it",
    os.path.join("db", "migrations", "recanon_honorifics.py"):  "one-shot backfill (Phase 7 owns it — D-T17-BACKFILL-CYPHER)",
    os.path.join("db", "neo4j_repos", "entities.py"):           "the entity MERGE + reads — the join sites",
    os.path.join("extraction", "glossary_sync.py"):             "THE defect site: computes it, ON MATCH SET never rewrites e.id",
    os.path.join("routers", "internal_enrichment.py"):          "enrichment write-back anchor",
}

CALL_RE = re.compile(r"(?<![A-Za-z0-9_])entity_canonical_id(?![A-Za-z0-9_])")


def strip_py_comments(text: str) -> str:
    """Blank `#` comments and triple-quoted docstrings — a module that DESCRIBES the derived
    id in prose is not a caller of it, and a gate that cannot tell those apart gets silenced."""
    text = re.sub(r'"""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\'',
                  lambda m: "\n" * m.group(0).count("\n"), text)
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'":
            q = ch
            out.append(ch); i += 1
            while i < n:
                if text[i] == "\\":
                    out.append(text[i:i + 2]); i += 2; continue
                out.append(text[i])
                if text[i] == q:
                    i += 1; break
                i += 1
            continue
        if ch == "#":
            while i < n and text[i] != "\n":
                out.append(" "); i += 1
            continue
        out.append(ch); i += 1
    return "".join(out)


def main() -> int:
    if not os.path.isdir(SCAN_ROOT):
        print(f"[derived-entity-id-gate] SKIP — {SCAN_ROOT} not present")
        return 0

    found: set[str] = set()
    for base, subdirs, files in os.walk(SCAN_ROOT):
        subdirs[:] = [s for s in subdirs if s != "__pycache__"]
        for f in files:
            if not f.endswith(".py") or f.startswith("test_"):
                continue
            path = os.path.join(base, f)
            rel = os.path.relpath(path, SCAN_ROOT)
            # The re-export shim is the definition site, not a caller.
            if rel == os.path.join("db", "neo4j_repos", "canonical.py"):
                continue
            try:
                raw = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            if CALL_RE.search(strip_py_comments(raw)):
                found.add(rel)

    baseline = set(BASELINE)
    added, gone = sorted(found - baseline), sorted(baseline - found)
    failed = False

    if added:
        failed = True
        print("[derived-entity-id-gate] FAIL — NEW caller(s) of the derived `Entity.id`:\n")
        for p in added:
            print(f"  {p}")
        print("\n  `entity_canonical_id` hashes name+kind, and `ON MATCH SET` never rewrites")
        print("  `e.id` — so a rename or re-kind silently orphans the node from its own joins.")
        print("  T35 retires it in favour of the stable glossary anchor. If this call is")
        print("  genuinely required first, add it to BASELINE with a reason.")

    if gone:
        failed = True
        print("[derived-entity-id-gate] FAIL — baseline names file(s) that no longer call it:\n")
        for p in gone:
            print(f"  {p}")
        print("\n  Remove them from BASELINE — that is T35 progress. A stale baseline also")
        print("  leaves a slot a future caller can occupy without the gate noticing.")

    if not failed:
        print(f"[derived-entity-id-gate] PASS — {len(found)} file(s) call the derived "
              f"`entity_canonical_id`, exactly the pinned set; the baseline can only shrink")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
