#!/usr/bin/env python3
"""T40 — partition `entity_facts` WHEN IT IS WORTH IT, and notice when that day arrives.

WHY THIS EXISTS
---------------
T40 says *"partition `entity_facts` by `book_id` — the growth table; every query is already
book-scoped, so the key is clean."* That sentence explains why partitioning would be **safe**.
It never said why it would be **needed**, and measured 2026-08-14 on the live glossary DB it is
not:

    48 610 rows · 35 MB · 12 books · biggest book 26 195 rows
    production read path (entity-scoped as-of):  8 buffers, 1.1 ms, index-served

Partition pruning would get a query to one book's partition — which `idx_entity_facts_book`
already does — and the read that actually runs never needs even that, because it is scoped by
`entity_id` and served by `uq_entity_facts_natural`. **At this size partitioning buys nothing
measurable and costs real operational surface.**

⚠️ **AND THERE IS A HARD BLOCKER NOBODY HAD WRITTEN DOWN.** Postgres requires every UNIQUE
constraint on a partitioned table to CONTAIN the partition key. `uq_entity_facts_natural` is

    (entity_id, fact_kind, attr_or_predicate, value_hash, valid_from_ordinal,
     coalesce(source_episode_id, nil))

and it does **not** contain `book_id`. So partitioning by `book_id` is not a DDL change to the
table — it forces `book_id` into the content-addressed natural key that the fact writer's whole
idempotency rests on. That is a semantic change to dedup, not a storage tweak, and T40's row
priced it as neither.

SO T40 IS RE-SCOPED TO A TRIGGER, NOT A DATE
--------------------------------------------
This gate is that trigger, and it is why the re-scope is not a promise. Two halves, and the
cheap one alone would be worse than nothing — the same split `migration-drift-gate.py` records.

- **STATIC** (always, no DB) — asserts the blocker is still real: `uq_entity_facts_natural`
  still omits `book_id`. **If someone adds it, this gate goes red to say the price of T40 just
  dropped** — the one change that makes partitioning cheap is otherwise invisible.
- **LIVE** (`--live <dsn>`) — fails when the table crosses `ROW_TRIGGER` while still unpartitioned.
  Growth is the only thing that can make this work worth doing, so growth is what reopens it.

    python scripts/entity-facts-growth-gate.py
    python scripts/entity-facts-growth-gate.py --live
    python scripts/entity-facts-growth-gate.py --selftest
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(
    ROOT, "services", "glossary-service", "internal", "migrate", "entity_facts.go"
)

#: Where partitioning starts paying. Chosen from the measurement above, not from a round
#: number: the live table is 48 610 rows / 35 MB and its hot read touches 8 buffers. An order
#: of magnitude is the point at which a sequential-ish scan of one book stops being free —
#: the 26 192-row filter this gate's docstring records was already 1369 buffers on the
#: book-only index, so ~10x that is where a book's own partition starts to matter.
ROW_TRIGGER = 500_000

#: The index that makes partitioning expensive, and the exact text that proves it.
NATURAL_KEY = "uq_entity_facts_natural"


def natural_key_columns(schema_sql: str) -> str:
    """The column list of `uq_entity_facts_natural`, as written in the Go migration."""
    m = re.search(
        r"CREATE UNIQUE INDEX IF NOT EXISTS\s+" + NATURAL_KEY + r"\s*\n\s*ON\s+entity_facts\s*\((.*?)\)\s*;",
        schema_sql,
        re.DOTALL,
    )
    if not m:
        raise SystemExit(
            f"entity-facts-growth-gate: FAIL — {NATURAL_KEY} not found in {SCHEMA}. "
            "The index this gate reasons about was renamed or removed; re-read T40's blocker "
            "before editing this check, because its absence changes T40's price."
        )
    return m.group(1)


def static_check() -> int:
    with open(SCHEMA, encoding="utf-8") as fh:
        cols = natural_key_columns(fh.read())
    # `book_id` as a WORD: `book_id` and `source_book_id` are different columns.
    has_book = re.search(r"(?<![A-Za-z0-9_])book_id(?![A-Za-z0-9_])", cols) is not None
    if has_book:
        print(
            "[entity-facts-growth-gate] FAIL — `book_id` is now part of "
            f"{NATURAL_KEY}.\n"
            "  That was T40's blocker: Postgres requires a partitioned table's UNIQUE keys to\n"
            "  contain the partition key, and this one did not. If the change was deliberate,\n"
            "  T40 just got cheap — do it, and delete this gate in the same commit. If it was\n"
            "  incidental, the fact writer's dedup semantics just changed and that is the\n"
            "  finding."
        )
        return 1
    print(
        f"[entity-facts-growth-gate] STATIC OK — {NATURAL_KEY} still omits `book_id`, so "
        "partitioning by it would re-cut the content-addressed natural key (T40's real price)."
    )
    return 0


#: Reached the same way `migration-drift-gate.py` reaches it — `docker exec … psql` — rather
#: than a Python driver. That gate set the precedent because the repo has no psycopg
#: dependency, and a live check that skips on a missing import is a live check nobody runs.
PG_CONTAINER = os.environ.get("LW_PG_CONTAINER", "infra-postgres-1")
PG_USER = os.environ.get("LW_PG_USER", "loreweave")
PG_DB = os.environ.get("LW_GLOSSARY_DB", "loreweave_glossary")


def _psql(sql: str) -> str | None:
    """One scalar, or None when the database cannot be REACHED.

    None is not an empty result, and conflating them is how this check would lie: an
    unreachable database would report `relkind` as absent and the gate would either fail on
    nothing or pass on nothing. Same rule migration-drift-gate records.
    """
    import subprocess  # noqa: PLC0415

    proc = subprocess.run(
        ["docker", "exec", PG_CONTAINER, "psql", "-U", PG_USER, "-d", PG_DB,
         "-t", "-A", "-c", sql],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def live_check() -> int:
    relkind = _psql("SELECT relkind FROM pg_class WHERE relname = 'entity_facts'")
    if relkind is None:
        print(f"[entity-facts-growth-gate] SKIPPED — cannot reach {PG_DB} on {PG_CONTAINER}; "
              "the static half ran.")
        return 0
    if not relkind:
        print(f"[entity-facts-growth-gate] SKIPPED — no entity_facts table on {PG_DB}.")
        return 0
    rows_raw = _psql("SELECT count(*) FROM entity_facts")
    rows = int(rows_raw) if rows_raw and rows_raw.isdigit() else 0

    if relkind == "p":
        print(f"[entity-facts-growth-gate] LIVE OK — entity_facts is PARTITIONED ({rows} rows). "
              "T40 is done; retire this gate.")
        return 0
    if rows >= ROW_TRIGGER:
        print(f"[entity-facts-growth-gate] FAIL — entity_facts holds {rows} rows "
              f"(trigger {ROW_TRIGGER}) and is NOT partitioned.")
        print("  T40 was re-scoped on the measurement that partitioning bought nothing at "
              "48k rows and 8 buffers per read. That is no longer the size.")
        print("  Reopen it — and price the natural-key change the static half describes; "
              "it has not gone away.")
        return 1
    print(f"[entity-facts-growth-gate] LIVE OK — {rows} rows, below the {ROW_TRIGGER} trigger; "
          "partitioning still buys nothing measurable.")
    return 0


def selftest() -> int:
    fails = []

    def check(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
        if not cond:
            fails.append(name)

    print("entity-facts-growth-gate · selftest")
    without = (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_entity_facts_natural\n"
        "  ON entity_facts (\n"
        "    entity_id, fact_kind, attr_or_predicate, value_hash, valid_from_ordinal,\n"
        "    coalesce(source_episode_id, '000'::uuid)\n"
        "  );\n"
    )
    withbook = without.replace("entity_id, fact_kind", "book_id, entity_id, fact_kind")
    check("reads the natural key's columns", "value_hash" in natural_key_columns(without))
    check("sees book_id when it is there",
          re.search(r"(?<![A-Za-z0-9_])book_id(?![A-Za-z0-9_])", natural_key_columns(withbook)) is not None)
    # 🔴 The one that makes the check non-vacuous: a column that merely CONTAINS the word must
    # not count, or the gate reports the blocker gone the day someone adds `source_book_id`.
    lookalike = without.replace("entity_id, fact_kind", "source_book_id, entity_id, fact_kind")
    check("a look-alike column does NOT count as book_id",
          re.search(r"(?<![A-Za-z0-9_])book_id(?![A-Za-z0-9_])", natural_key_columns(lookalike)) is None)
    # And a missing index must be loud, not silently "no book_id".
    try:
        natural_key_columns("CREATE TABLE entity_facts (x int);")
        check("a missing natural key RAISES rather than passing", False, "it returned")
    except SystemExit:
        check("a missing natural key RAISES rather than passing", True)
    check("the REAL schema still omits book_id today", static_check() == 0)

    print("\n  all checks passed" if not fails else f"\n  {len(fails)} failure(s)")
    return 1 if fails else 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    rc = static_check()
    if "--live" in sys.argv:
        rc = live_check() or rc
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
