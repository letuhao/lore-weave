#!/usr/bin/env python3
"""migration-drift-gate — a migration that shipped is not a migration that RAN.

WHY THIS EXISTS, and it is a real incident rather than a hypothetical. On 2026-08-11 the
D-T32 life-status producer went live and every write returned 500:

    new row for relation "entity_facts" violates check constraint "entity_facts_kind_chk"

The constraint did not admit `'status'` — the exact thing T32 had shipped a migration to
widen. `schema_migrations` on the running database topped out at **0062**, so steps
**0063, 0064 and 0065** had never run there. Three migrations, written, reviewed, merged,
green in every suite, and **absent from the database the services were talking to**. The
`entity_lifecycle_ledger` and `entity_fact_evidence` tables did not exist either.

Nothing detected it for days, and the reason is the point: **no other code had ever tried
to use them**. A migration's absence is invisible until a feature depends on it, so the
first thing to notice is always a user-facing 500. The unit suites were green throughout —
they prove the working tree, never the deployment.

── THE TWO CHECKS, and why the cheap one is not enough ──────────────────────────────────

STATIC (always, no database needed)
    Every `Up*` migration function defined in the package is registered in `chain`, ids are
    unique, and they ascend. Catches "wrote the migration, forgot to wire it" — a genuine
    class, and the only one CI can see without a database.

LIVE (only when a database is reachable)
    Diff `chain` against that database's `schema_migrations`. **This is the check that
    would have caught the incident**, and static mode would not have: all three steps were
    correctly registered. The gap was between the repo and one running Postgres.

A gate that only ran the static half would report green on the exact failure it is named
for, which is worse than not existing — it would carry the authority of a check without
the coverage.

    python scripts/migration-drift-gate.py                  # static only
    python scripts/migration-drift-gate.py --live           # + the dev stack
    python scripts/migration-drift-gate.py --live --db loreweave_glossary

Exit 0 = no drift · 1 = drift (unregistered step, or a registered step not applied live).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# One entry per ledgered service. `funcs_glob` is where the Up* functions live; `chain` is
# the file holding the registration list. Adding a service here is the whole integration.
SERVICES = {
    "glossary": {
        "chain_file": os.path.join(
            ROOT, "services", "glossary-service", "internal", "migrate", "ledger.go"),
        "pkg_dir": os.path.join(ROOT, "services", "glossary-service", "internal", "migrate"),
        "db": "loreweave_glossary",
        "ledger_table": "schema_migrations",
        "ledger_col": "name",
    },
}

PG_CONTAINER = os.environ.get("LW_PG_CONTAINER", "infra-postgres-1")
PG_USER = os.environ.get("LW_PG_USER", "loreweave")

# `{"0063_entity_lifecycle_ledger", UpEntityLifecycleLedger},`
_STEP_RE = re.compile(r'^\s*\{\s*"([^"]+)"\s*,\s*(\w+)\s*\}\s*,', re.M)
# `func UpEntityFactsStatusKind(` — the exported migration entry points.
_FUNC_RE = re.compile(r"^func (Up[A-Z]\w*)\s*\(", re.M)


def registered_steps(chain_file: str) -> list[tuple[str, str]]:
    src = open(chain_file, encoding="utf-8").read()
    start = src.find("var chain = []Step{")
    if start < 0:
        return []
    end = src.find("\n}", start)
    return _STEP_RE.findall(src[start:end if end > 0 else len(src)])


def defined_funcs(pkg_dir: str) -> set[str]:
    out: set[str] = set()
    for name in sorted(os.listdir(pkg_dir)):
        if not name.endswith(".go") or name.endswith("_test.go"):
            continue
        src = open(os.path.join(pkg_dir, name), encoding="utf-8").read()
        out.update(_FUNC_RE.findall(src))
    return out


def applied_steps(db: str, table: str, col: str) -> set[str] | None:
    """The ids that database says it has run, or None when it is unreachable.

    None is NOT an empty set, and conflating them is how this check would lie: an
    unreachable database would otherwise report every step as missing, and the reflex
    would be to ignore the gate.
    """
    proc = subprocess.run(
        ["docker", "exec", PG_CONTAINER, "psql", "-U", PG_USER, "-d", db,
         "-t", "-A", "-c", f"SELECT {col} FROM {table};"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="also diff against a reachable database (the check that matters)")
    ap.add_argument("--db", default=None, help="override the database name")
    args = ap.parse_args()

    failures: list[str] = []
    for svc, cfg in SERVICES.items():
        steps = registered_steps(cfg["chain_file"])
        if not steps:
            failures.append(f"{svc}: could not parse a migration chain from "
                            f"{os.path.relpath(cfg['chain_file'], ROOT)}")
            continue
        ids = [s[0] for s in steps]
        funcs = {s[1] for s in steps}

        # ── STATIC ──────────────────────────────────────────────────────────────────
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            failures.append(f"{svc}: duplicate step id(s): {', '.join(sorted(dupes))}")
        if ids != sorted(ids):
            failures.append(f"{svc}: chain is not in ascending id order — a ledger applies "
                            f"in list order, so an out-of-order id will mislead every reader")
        orphaned = defined_funcs(cfg["pkg_dir"]) - funcs
        if orphaned:
            failures.append(
                f"{svc}: {len(orphaned)} migration func(s) defined but NOT registered in "
                f"`chain` — they will never run: " + ", ".join(sorted(orphaned)))
        print(f"[migration-drift] {svc}: {len(ids)} registered step(s), "
              f"latest {ids[-1]}")

        # ── LIVE ────────────────────────────────────────────────────────────────────
        if not args.live:
            continue
        db = args.db or cfg["db"]
        applied = applied_steps(db, cfg["ledger_table"], cfg["ledger_col"])
        if applied is None:
            print(f"[migration-drift] {svc}: {db} unreachable — LIVE CHECK SKIPPED "
                  f"(this is the half that catches a shipped-but-unapplied migration)")
            continue
        missing = [i for i in ids if i not in applied]
        print(f"[migration-drift] {svc}: {len(applied)} applied in {db}, "
              f"{len(missing)} unapplied")
        if missing:
            failures.append(
                f"{svc}: {len(missing)} registered step(s) have NEVER RUN on {db}: "
                + ", ".join(missing)
                + " — restart/redeploy the service so its chain applies")

    print()
    if failures:
        print("[migration-drift] FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[migration-drift] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
