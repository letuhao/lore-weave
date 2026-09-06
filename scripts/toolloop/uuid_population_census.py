#!/usr/bin/env python
"""Census every UUID identifier the platform holds — the population a fabrication guard filters.

WHY IT EXISTS. Two rows and one shipped guard argue about what an id-shape rule would cost, and
each quotes a number from a different sample: 38,314 real ids here, 12,276 recorded arguments
there, "its 20" hand-authored sentinels somewhere else. A ledger claim is a lead, not a fact, and
a rule that would refuse identifiers deserves the whole population rather than a slice of it.

    D-FABRICATION-GUARD-IS-BLIND-TO-A-VALID-LOOKING-UUID   the `version != 7` rejection
    DQ-T76                                                 option (c), "change the sentinel"

🔴 IT COUNTS DISTINCT IDS, NOT COLUMN VALUES, AND THAT IS THE WHOLE POINT. Every foreign key
repeats an id, so an occurrence count inflates exactly the numbers people reach for: measured
2026-08-30, occurrences said 5,328,486 non-v7 of 6,002,461 and 4,130 sentinel-shaped, while the
distinct population is 1,073,328 of 1,296,259 and TWENTY-ONE sentinels. Both errors flatter the
rule being argued about, which is the direction a measurement is least likely to be questioned in.

WHAT IT MEASURES, per database and in total:
  * distinct ids               the denominator any refusal rate is a fraction of
  * not version 7 / version 4  the `version != 7` rule's false-refusal population
  * <= 2 distinct hex digits   the hand-authored sentinel family (the rule's other candidate),
                               listed in full, because "exclude by identity" needs the identities

SCOPE, stated because it bounds every figure it prints: columns named `id` or `*_id` of type
`uuid` in the five main stores. It does NOT see uuids held as TEXT, nor the auth / jobs /
registry databases. So every count is a FLOOR, which is the safe direction for an argument about
how much a refusal rule would break.

Usage:  python scripts/toolloop/uuid_population_census.py [--db loreweave_glossary ...]
"""
from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys

DBS = ["loreweave_book", "loreweave_glossary", "loreweave_composition",
       "loreweave_chat", "loreweave_knowledge"]
PG = ["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave"]

#: The 32-hex body has at most this many DISTINCT characters → a hand-authored sentinel.
#: Not a shipped rule: the guard REJECTED it precisely because these values resolve.
SENTINEL_MAX_DISTINCT_HEX = 2


def _psql(db: str, sql: str) -> str:
    r = subprocess.run(PG + ["-d", db, "-tAf", "-"], input=sql,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  {db}: {r.stderr.strip()[:160]}", file=sys.stderr)
        return ""
    return r.stdout.strip()


def id_columns(db: str) -> list[tuple[str, str]]:
    sql = ("SELECT c.table_name||'|'||c.column_name FROM information_schema.columns c "
           "JOIN information_schema.tables t ON t.table_name=c.table_name "
           "  AND t.table_schema='public' AND t.table_type='BASE TABLE' "
           "WHERE c.data_type='uuid' AND c.table_schema='public' "
           "  AND c.column_name ~ '(^id$|_id$)';")
    return [tuple(l.split("|")) for l in _psql(db, sql).splitlines() if "|" in l]


def _union(cols: list[tuple[str, str]]) -> str:
    return " UNION ALL ".join(
        f"SELECT {c}::text AS v FROM {t} WHERE {c} IS NOT NULL" for t, c in cols)


def census(db: str) -> dict | None:
    cols = id_columns(db)
    if not cols:
        return None
    distinct_hex = ("(SELECT count(DISTINCT ch) FROM "
                    "regexp_split_to_table(replace(v,'-',''),'') ch)")
    sql = (f"WITH allids AS ({_union(cols)}), d AS (SELECT DISTINCT v FROM allids) "
           "SELECT count(*), "
           "count(*) FILTER (WHERE substring(v,15,1) <> '7'), "
           "count(*) FILTER (WHERE substring(v,15,1) = '4'), "
           f"count(*) FILTER (WHERE {distinct_hex} <= {SENTINEL_MAX_DISTINCT_HEX}) FROM d;")
    out = _psql(db, sql)
    if not out or "|" not in out:
        return None
    total, not7, v4, sent = (int(x) for x in out.split("|"))
    ids = _psql(db, f"WITH allids AS ({_union(cols)}), d AS (SELECT DISTINCT v FROM allids) "
                    f"SELECT v||'|'||substring(v,15,1) FROM d "
                    f"WHERE {distinct_hex} <= {SENTINEL_MAX_DISTINCT_HEX} ORDER BY v;")
    return {"columns": len(cols), "distinct_ids": total, "not_v7": not7, "v4": v4,
            "sentinel_shaped": sent,
            "sentinels": [l.split("|") for l in ids.splitlines() if "|" in l]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", nargs="*", default=DBS)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    per = {}
    for db in a.db:
        r = census(db)
        if r:
            per[db] = r
    if a.json:
        print(json.dumps(per, indent=1))
        return 0

    tot = collections.Counter()
    print(f"{'database':24s} {'columns':>8s} {'distinct':>10s} {'not v7':>10s} "
          f"{'v4':>10s} {'sentinel':>9s}")
    for db, r in per.items():
        for k in ("distinct_ids", "not_v7", "v4", "sentinel_shaped", "columns"):
            tot[k] += r[k]
        print(f"{db:24s} {r['columns']:8d} {r['distinct_ids']:10,d} {r['not_v7']:10,d} "
              f"{r['v4']:10,d} {r['sentinel_shaped']:9d}")
    print(f"{'TOTAL':24s} {tot['columns']:8d} {tot['distinct_ids']:10,d} "
          f"{tot['not_v7']:10,d} {tot['v4']:10,d} {tot['sentinel_shaped']:9d}")
    if tot["distinct_ids"]:
        print(f"\n  a `version != 7` refusal would reject "
              f"{tot['not_v7'] / tot['distinct_ids']:.1%} of every id the platform holds")
    print("\n  THE SENTINEL FAMILY — what 'exclude by identity' would have to list:")
    for db, r in per.items():
        for v, ver in r["sentinels"]:
            print(f"    {v}  v{ver}  ({db.replace('loreweave_', '')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
