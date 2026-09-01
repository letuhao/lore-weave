"""A migration step's SQL may only reach a database through the ledger.

D-GLOSSARY-READS-RETURN-ok-true-result-null-ON-A-SEEDED-BOOK was fixed on 2026-08-26 by chain step
0060_glossary_recalc_restore, proven live, and REGRESSED by 2026-08-31: the deployed
`recalculate_entity_snapshot` was byte-identical to the pre-fix body again (103 lines, zero
mentions of `cached_name`) while 0060 was still recorded applied.

    THE MECHANISM. A Go test called the migration STEP FUNCTIONS directly --
    `{"UpSnapshot", migrate.UpSnapshot}, ...` -- against `os.Getenv("GLOSSARY_TEST_DB_URL")`.
    A direct call bypasses ApplyOnce and re-executes that step's SQL unconditionally. UpSnapshot
    is 0004's body, which does NOT maintain cached_name/search_vector, and the hand-copied list
    did not include 0060. So the test silently reverted the fix -- and because the LEDGER still
    recorded 0060 as applied, re-running the chain could never put it back.

WHY THIS GUARD IS DERIVED AND NOT A NAME LIST. The forbidden set is computed by reading the
migrate package: any exported step function whose SQL redefines `recalculate_entity_snapshot`.
A future step that redefines it under a new name is caught without editing this file. Hard-coding
`UpSnapshot` would guard the instance and miss the class -- and the class is the point, because
the repo already fixed this once in internal/api (entity_revisions_handler_test.go: "migrate.
RunChain, NOT a hand-copied list") and internal/events was missed anyway.

WHAT IS ALLOWED. `migrate.RunChain` -- it is ApplyOnce-backed, so it is a no-op on an
already-migrated database and still builds a fresh one. And any test that provisions its own
EPHEMERAL database (internal/migrate/g4_cutover_test.go) may call whatever it likes: it cannot
reach a shared database by construction.

WHAT THIS DOES NOT COVER, stated because the invariant is broader than the guard. Other tests
call other step functions directly on an env DSN (UpOutbox, UpShortDescAuto, UpEntityEnrichments).
Those are the same CLASS of hazard, and this guard does not fail them, because it has only been
DEMONSTRATED for the snapshot function -- a step that redefines an object no later step redefines
is harmless today. Widening it to every direct step call is a judgement about ~6 more call sites
that has not been measured, and a bar should not be set by a guess.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATE = ROOT / "services" / "glossary-service" / "internal" / "migrate"
SERVICE = ROOT / "services" / "glossary-service"

#: The object whose redefinition is the demonstrated harm.
GUARDED_OBJECT = "recalculate_entity_snapshot"

#: Ledger-aware entry point. Safe by construction.
ALLOWED = {"RunChain", "ApplyOnce", "EnsureLedger"}


def _migrate_source() -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="replace")
                     for p in sorted(MIGRATE.glob("*.go"))
                     if not p.name.endswith("_test.go"))


def forbidden_step_functions() -> set[str]:
    """Exported step funcs whose SQL redefines the guarded object.

    Derived: find the SQL consts containing `CREATE OR REPLACE FUNCTION <object>`, then find the
    functions that execute those consts.
    """
    src = _migrate_source()
    consts = set()
    for m in re.finditer(r"const\s+(\w+)\s*=\s*`(.*?)`", src, re.S):
        if re.search(rf"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+{GUARDED_OBJECT}", m.group(2), re.I):
            consts.add(m.group(1))
    if not consts:
        pytest.fail(
            f"no SQL const in {MIGRATE} redefines {GUARDED_OBJECT}. Either the function was "
            "renamed or this guard's derivation is broken — it must not silently pass by finding "
            "nothing to forbid.")
    out = set()
    for fm in re.finditer(r"func\s+([A-Z]\w*)\s*\(ctx context\.Context[^)]*\)\s*error\s*\{(.*?)\n\}",
                          src, re.S):
        name, body = fm.group(1), fm.group(2)
        if name in ALLOWED:
            continue
        if any(c in body for c in consts):
            out.add(name)
    return out


def strip_go_comments(src: str) -> str:
    """Code only.

    🔴 THIS FUNCTION EXISTS BECAUSE THE GUARD'S FIRST RUN WENT RED ON A COMMENT — the one written
    into revision_consumer_test.go explaining why the hand-copied list was removed, which quotes
    `migrate.UpSnapshot` verbatim. A substring guard that reads comments is red when the code is
    correct and can never be made green except by deleting the explanation, which is the worst
    possible incentive. Strings are kept: a step name passed as a string is not a call.
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", line) for line in src.splitlines())


def env_dsn_test_files() -> list[pathlib.Path]:
    """Test files that can reach a database named by the ENVIRONMENT — i.e. possibly a shared,
    already-migrated one.

    🔴 SCOPED BY PACKAGE, NOT BY FILE, AND THE FIRST VERSION OF THIS GUARD GOT THAT WRONG. Go
    tests share a package-level pool helper: `canon_content_test.go` calls `migrate.UpOutbox`
    and contains no `os.Getenv` of its own, because a sibling file in the same package reads the
    DSN. A per-file filter therefore saw 3 files where package scope sees 7, and a future test
    calling a superseded step through a shared helper would have passed unnoticed — the exact
    blind spot that let this defect ship twice.

    A file that provisions its OWN ephemeral database is still excluded individually: it cannot
    reach a shared database whatever its package siblings do (internal/migrate/g4_cutover_test.go
    legitimately calls step functions this way).
    """
    env_packages = set()
    by_package: dict[pathlib.Path, list[pathlib.Path]] = {}
    for p in SERVICE.rglob("*_test.go"):
        by_package.setdefault(p.parent, []).append(p)
        src = p.read_text(encoding="utf-8", errors="replace")
        if "os.Getenv(" in src and "ephemeralPool(" not in src:
            env_packages.add(p.parent)

    out = []
    for pkg in env_packages:
        for p in by_package[pkg]:
            if "ephemeralPool(" in p.read_text(encoding="utf-8", errors="replace"):
                continue
            out.append(p)
    return out


def test_the_derivation_found_something_to_forbid():
    """Non-vacuity. A guard whose forbidden set is empty passes on everything."""
    fns = forbidden_step_functions()
    assert fns, (
        f"no migrate step function was found to redefine {GUARDED_OBJECT}, so this guard forbids "
        "nothing and would pass with the defect fully present.")
    assert "UpSnapshot" in fns, (
        f"the derivation found {sorted(fns)} but not UpSnapshot, which is the ORIGINAL INSTANCE — "
        "the derivation has drifted off the thing this row was opened on.")


def test_no_env_dsn_test_calls_a_step_that_redefines_the_snapshot_function():
    """THE INVARIANT. A step's SQL may only reach a shared database through the ledger."""
    forbidden = forbidden_step_functions()
    files = env_dsn_test_files()
    assert files, (
        "no test file reads a DSN from the environment — the population this guard protects is "
        "empty, which means the guard is measuring nothing rather than passing.")

    offenders = []
    for p in files:
        src = strip_go_comments(p.read_text(encoding="utf-8", errors="replace"))
        for fn in sorted(forbidden):
            # `migrate.UpSnapshot` as a VALUE or a CALL both re-execute it: the hand-copied list
            # stored the function in a struct and called it in a loop, so matching only `(` would
            # have missed the original instance entirely.
            if re.search(rf"\bmigrate\.{fn}\b", src):
                offenders.append(f"{p.relative_to(ROOT)} -> migrate.{fn}")
    assert not offenders, (
        "a test reaches a shared database with a migration step's SQL, bypassing the ApplyOnce "
        "ledger. That re-executes an OLD definition of "
        f"{GUARDED_OBJECT} on a database whose ledger records a NEWER one, and nothing detects it "
        "because the ledger still says the newer step is applied — the exact regression of "
        "0060_glossary_recalc_restore observed on 2026-09-01.\n  "
        + "\n  ".join(offenders)
        + "\n\nUse `migrate.RunChain`, which is ApplyOnce-backed: a no-op on a migrated database "
          "and still builds a fresh one.")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
