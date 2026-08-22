#!/usr/bin/env python3
"""Every ACCOUNT-SCOPED fixture a seed can create must have a teardown that removes it.

    python scripts/test_teardown_purges_account_scoped_fixtures_gate.py

🔴 THE CLASS, THREE TIMES OVER. A throwaway BOOK dies with `purge_book`. Anything the seed creates
that is NOT book-scoped survives it, lands on the harness account, and becomes a plausible,
wrongly-scoped target for the next batch:

    worlds          35 leaked behind a name-prefix guard that never matched
    user models     the same shape, one scope over
    arc templates   measured 2026-08-23 — 51 of 57 rows carry book_id NULL

The arc-template case is the one that shows the real cost. Batch 15's `throwaway-loop-skeleton-b15`
was created 2026-08-20, ARCHIVED by the model on a later run (archiving is what that scenario asks
for) and never restored. Every run afterwards failed its own seed assertion — `status <> 'archived'`
reading 0 — so the scenario provision-failed 5 of 5 and the report showed
`composition_arc_template_edit` at "0/5 called, 0/5 surfaced", which reads as a SURFACING failure of
the tool. It took a direct DB query to find; the tool's own listing showed nothing, with and without
`include_archived`.

WHAT THIS PINS, and deliberately not more: for each account-scoped creator a seed may call, teardown
has a purge, that purge is REACHED from `teardown`, and it selects by PROVENANCE rather than by a
name prefix. The last clause is the whole lesson of `_purge_worlds`, whose guard required a
TITLE_PREFIX the seeds deliberately do not use — so it matched nothing, for 35 worlds.

WHAT IT CANNOT TELL YOU: whether the purge SUCCEEDS at runtime. That is `is_gone()`'s job, asked of
the database. This is a wiring check, and a wiring check that passes is not evidence the store is
clean.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROV = ROOT / "scripts" / "toolloop" / "provision.py"

#: the seed-callable creator -> the purge that must remove what it made
ACCOUNT_SCOPED = {
    "world_create": "_purge_worlds",
    "settings_model_register": "_purge_models",
    "composition_arc_extract_template": "_purge_arc_templates",
}


def main() -> int:
    src = PROV.read_text(encoding="utf-8")
    body_start = src.find("    def teardown(")
    if body_start < 0:
        body_start = src.find("    def _teardown(")
    fail = 0

    for creator, purge in sorted(ACCOUNT_SCOPED.items()):
        if f"def {purge}(" not in src:
            print(f"FAIL — {creator} can be seeded but {purge}() does not exist; whatever it")
            print("       creates outlives the throwaway book and lands on the harness account")
            fail += 1
            continue
        # It must be CALLED, not merely defined — a purge nothing reaches is the same leak.
        if len(re.findall(rf"self\.{purge}\(\)", src)) == 0:
            print(f"FAIL — {purge}() is defined but never called; a teardown that is not")
            print("       reached is indistinguishable from one that does not exist")
            fail += 1
            continue
        # PROVENANCE, not a name prefix. _purge_worlds required TITLE_PREFIX, the seeds
        # deliberately do not use it, and 35 worlds leaked behind a guard that never matched.
        seg_start = src.find(f"def {purge}(")
        seg_end = src.find("\n    def ", seg_start + 1)
        seg = src[seg_start:seg_end if seg_end > 0 else len(src)]
        if "self.seeded" not in seg:
            print(f"FAIL — {purge}() does not select from self.seeded, so it is not selecting by")
            print("       PROVENANCE. A name- or prefix-based guard is what leaked 35 worlds.")
            fail += 1
            continue
        print(f"ok — {creator:34} -> {purge}() exists, is called, and selects by provenance")

    if fail:
        print(f"\n{fail} account-scoped creator(s) have no working teardown.")
        return 1
    print("\nall account-scoped seed creators have a reachable, provenance-based purge.")
    print("NOTE: this is a WIRING check. Whether a purge actually empties the store is is_gone()'s")
    print("      job, asked of the database — a green here is not a clean account.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
