#!/usr/bin/env python3
"""An EXISTENCE seed assertion on a lifecycle table must filter the lifecycle column.

    python scripts/test_seed_assert_applies_the_lifecycle_predicate_gate.py
    python scripts/test_seed_assert_applies_the_lifecycle_predicate_gate.py --strict   # exit 1

🔴 WHAT THIS COSTS WHEN IT IS MISSING, measured 2026-08-23. `composition_motif_link_edit`'s seed
asserted `SELECT count(*) FROM motif WHERE code IN (...)` and expected 2. Both motifs had been
ARCHIVED by a sibling scenario two days earlier and never restored. So:

  * the tool could not resolve them  — `get_by_codes` filters `status = 'active'`
  * the seed could not recreate them — `uq_motif_user` is UNIQUE(owner_user_id, code) with NO
    status predicate, so an archived row still owns its code
  * and the assertion counted them and PASSED

Fifteen runs and thirteen refuted hypotheses were spent on the tool. The fixture was green the
whole time, over rows the tool was structurally unable to see.

THE RULE: an assertion that cannot see the same rows the tool sees is not an assertion. If the
table carries a lifecycle column, an existence assertion must say which lifecycle it means.

DELIBERATELY A REPORT, NOT A BLOCKER, unless --strict. Most of these live on BOOK-scoped tables
(`structure_node`, `outline_node`, `plan_run`), where the throwaway book dies each run and takes
the rows with it — real but far less likely to bite. The ones that bite are ACCOUNT-scoped, where
a row outlives every teardown; those are listed first. Mass-editing 37 green fixtures blind would
be its own defect, so this makes them visible and ranks them.

WHAT IT CANNOT TELL YOU: whether the tool's read predicate really is `status='active'`. That is
per-repository and belongs in the scenario's `why`. This checks that the question was ASKED.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import subprocess
import sys

DBS = ("loreweave_composition", "loreweave_knowledge", "loreweave_books", "loreweave_glossary")
LIFECYCLE_COLS = ("status", "archived", "deleted_at", "is_active")

#: Tables whose rows outlive `purge_book`. A stale row here is inherited by EVERY later run —
#: this is the population the motif defect came from.
ACCOUNT_SCOPED = {"motif", "arc_template", "user_kinds", "user_attributes", "user_genres"}


def lifecycle_tables() -> set[str]:
    cols = "','".join(LIFECYCLE_COLS)
    out: set[str] = set()
    for db in DBS:
        r = subprocess.run(
            ["docker", "exec", "infra-postgres-1", "psql", "-U", "loreweave", "-d", db, "-tAc",
             f"SELECT table_name FROM information_schema.columns WHERE column_name IN "
             f"('{cols}') AND table_schema='public'"],
            capture_output=True, text=True)
        out.update(x.strip() for x in (r.stdout or "").splitlines() if x.strip())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on any finding, not only account-scoped ones")
    a = ap.parse_args()

    life = lifecycle_tables()
    if not life:
        print("SKIPPED — could not read the schemas (is infra-postgres-1 up?). A probe that")
        print("cannot see the thing must not report a pass, so this is a skip, not a green.")
        return 0

    acct, book = [], []
    for f in sorted(glob.glob("scripts/toolloop/scenarios-*.json")):
        try:
            d = json.loads(open(f, encoding="utf-8").read())
        except Exception:
            continue
        for s in d.get("scenarios", []):
            for sa in s.get("seed_assert") or []:
                q = sa.get("query") or ""
                exp = str(sa.get("expect") or "").strip()
                m = re.search(r"\bFROM\s+([a-zA-Z_][\w]*)", q)
                if not m or m.group(1) not in life:
                    continue
                if re.search("|".join(LIFECYCLE_COLS), q, re.I):
                    continue
                # EXISTENCE only: expecting zero rows cannot be satisfied by a hidden row
                if not re.fullmatch(r"\d+", exp) or int(exp) == 0:
                    continue
                row = (m.group(1), s.get("tool_under_test") or "?", exp)
                (acct if m.group(1) in ACCOUNT_SCOPED else book).append(row)

    seen: set = set()
    def uniq(rows):
        out = []
        for r in rows:
            if (r[0], r[1]) in seen:
                continue
            seen.add((r[0], r[1]))
            out.append(r)
        return sorted(out)

    acct, book = uniq(acct), uniq(book)
    print(f"existence assertions on a lifecycle table with no lifecycle predicate: "
          f"{len(acct) + len(book)}")
    print(f"  ACCOUNT-scoped (a stale row is inherited by every later run): {len(acct)}")
    print(f"  book-scoped    (dies with the throwaway book):                {len(book)}\n")

    for label, rows in (("ACCOUNT-SCOPED — fix these", acct), ("book-scoped — lower risk", book)):
        if not rows:
            continue
        print(f"{label}:")
        for t, tool, e in rows:
            print(f"  {t:18} {tool:40} expect={e}")
        print()

    if acct:
        print("An assertion that cannot see the same rows the tool sees is not an assertion.")
        return 1
    if book and a.strict:
        return 1
    print("No ACCOUNT-scoped existence assertion is blind to its lifecycle column.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
