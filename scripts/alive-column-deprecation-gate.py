#!/usr/bin/env python3
"""alive-column-deprecation-gate — `glossary_entities.alive` gains no NEW readers (plan T32).

WHY THE COLUMN IS DEPRECATED
----------------------------
Design D1: *"Liveness becomes a fact, not a column."* The column form was tried and measured,
and the measurement is the argument — re-measured on the dev database 2026-08-11:

    SELECT count(*) FILTER (WHERE alive), count(*) FILTER (WHERE NOT alive), count(*)
      FROM glossary_entities;
    ->  7345 |  0 |  7345

**7345 true, 0 false.** A boolean that has never once been false is not recording anything; it
is a column-shaped assumption. Meanwhile `:EntityStatus`, which IS modelled correctly — a
transition at a reading position — sits on the wrong side of the identity seam at 0 of 21
reachable. Death is a story event at a position, and that is what a bitemporal fact is.

WHY THE READERS ARE NOT MIGRATED YET, AND WHY THAT IS NOT A CHOICE
------------------------------------------------------------------
    SELECT count(*) FROM entity_facts
     WHERE fact_kind='status' OR attr_or_predicate='life_status';
    ->  0

**There are no liveness facts.** T32 widened `entity_facts_kind_chk` to admit `'status'`, which
is the schema half; nothing produces such facts yet. Migrating a reader today gives it a choice
between failing closed (every entity reads as not-alive — a total outage of the canon reads)
and failing open (identical behaviour to `alive=true`, proving nothing). Neither is a
migration. See `D-T32-ALIVE-NO-FACTS` in the plan.

WHAT THIS GATE DOES
-------------------
It freezes the blast radius. The reader set is pinned exactly: **a new file reading `alive`
fails this gate**, and a file that stops reading it must be removed from the list, so the
baseline can only shrink. That is the difference between a column that is deprecated and a
column that is merely described as deprecated — the plan's own warning is that introducing
liveness-as-a-fact *while leaving the column read* recreates the two-sources-of-truth
condition the design diagnosed.

    python scripts/alive-column-deprecation-gate.py

Exit 0 = the reader set is unchanged or smaller · 1 = it grew, or the baseline is stale.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_ROOT = os.path.join(ROOT, "services", "glossary-service", "internal")

# The reader set as of T32, with what each one is doing. Every entry is a file that must
# eventually move onto the as-of liveness fact; the list IS the migration checklist.
BASELINE = {
    os.path.join("api", "entity_handler.go"):            "CRUD + list filters",
    os.path.join("api", "extraction_handler.go"):        "extraction writeback",
    os.path.join("api", "entity_search.go"):             "search filter",
    os.path.join("api", "entity_revisions_handler.go"):  "revision history",
    os.path.join("api", "entities_by_ids_handler.go"):   "bulk read",
    os.path.join("api", "canon_at_chapter_handler.go"):  "T52 rewrites this one — canon as-of chapter N",
    os.path.join("migrate", "migrate.go"):               "schema definition + backfill (not a runtime read)",
}

# `alive` as a WORD, not as a substring: `aliveness`, `keepalive` and a comment saying "alive"
# are all different things. Matched on the identifier boundary so the gate reports column
# reads rather than prose.
ALIVE_RE = re.compile(r"(?<![A-Za-z0-9_])alive(?![A-Za-z0-9_])")


def strip_comments(text: str) -> str:
    """Blank // and /* */ comments, keep string literals (SQL lives in raw strings)."""
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'`":
            quote = ch
            out.append(ch)
            i += 1
            while i < n:
                if text[i] == "\\" and quote != "`":
                    out.append(text[i:i + 2]); i += 2; continue
                out.append(text[i])
                if text[i] == quote:
                    i += 1; break
                i += 1
            continue
        if text.startswith("//", i):
            while i < n and text[i] != "\n":
                out.append(" "); i += 1
            continue
        if text.startswith("/*", i):
            while i < n and not text.startswith("*/", i):
                out.append("\n" if text[i] == "\n" else " "); i += 1
            out.append("  "); i += 2
            continue
        out.append(ch); i += 1
    return "".join(out)


def main() -> int:
    if not os.path.isdir(SCAN_ROOT):
        print(f"[alive-deprecation-gate] SKIP — {SCAN_ROOT} not present")
        return 0

    found: set[str] = set()
    for base, subdirs, files in os.walk(SCAN_ROOT):
        subdirs[:] = [s for s in subdirs if s != "testdata"]
        for f in files:
            if not f.endswith(".go") or f.endswith("_test.go"):
                continue
            path = os.path.join(base, f)
            try:
                raw = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            if ALIVE_RE.search(strip_comments(raw)):
                found.add(os.path.relpath(path, SCAN_ROOT))

    baseline = set(BASELINE)
    added = sorted(found - baseline)
    gone = sorted(baseline - found)
    failed = False

    if added:
        failed = True
        print("[alive-deprecation-gate] FAIL — NEW reader(s) of the deprecated "
              "`glossary_entities.alive`:\n")
        for p in added:
            print(f"  {p}")
        print("\n  `alive` is 7345 true / 0 false — it records nothing, and D1 replaces it with")
        print("  an as-of liveness FACT. Adding a reader now deepens the two-sources-of-truth")
        print("  condition the design diagnosed. If this read is genuinely required before")
        print("  liveness facts exist (D-T32-ALIVE-NO-FACTS), add it to BASELINE with a reason.")

    if gone:
        failed = True
        print("[alive-deprecation-gate] FAIL — baseline names file(s) that no longer read "
              "`alive`:\n")
        for p in gone:
            print(f"  {p}")
        print("\n  Remove them from BASELINE. A stale baseline understates progress and, worse,")
        print("  leaves a slot a future reader can occupy without the gate noticing.")

    if not failed:
        print(f"[alive-deprecation-gate] PASS — {len(found)} file(s) read the deprecated "
              f"`alive` column, exactly the pinned set; the baseline can only shrink")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
