#!/usr/bin/env python3
"""test-dsn-coverage-gate.py — a gated test that no workflow arms has never run.

## Why this exists

Twice in one day, a sweep found DB-gated tests that had never executed anywhere:

  · **ROT-0** — `JOBS_TEST_PG_DSN` and `PIIKMS_TEST_PG_URL` were set by no workflow. 41
    test functions: PgKEKManager, PII erasure, admin-cli erasure/archive/drift,
    meta-worker's erased-writer, breach-notifier, the meta-outbox relay. They COMPILED —
    foundation-ci's module loop builds them — and compiling does not check SQL.

  · **ROT-1** — because ROT-0 swept only the two variables it happened to be holding and
    reported "41" as the answer. Sweeping every `*_TEST_*` variable afterwards found
    **eight more** and **159 further test functions**: provider-registry 54,
    usage-billing 37, auth 36, and five more services.

Both were invisible for the same reason: a skip is indistinguishable from a pass in the
summary line, and nothing ever compared the set of gating variables against the set of
variables CI arms. **200 never-run tests; 41 was reported.** This gate is the comparison,
so there is no ROT-2.

Its first run also proved the ROT-1 triage was worth doing rather than assuming: all three
failures were STALE TESTS, not product bugs — a hand-listed migration set missing the very
migration written for it; a test that predated a lease guard and so never claimed its row;
and a free-tier assertion colliding with an unrelated daily cap.

## The rule

Every `*_TEST_*`-shaped environment variable read by a test file must be set by some
workflow, **or** be declared here with the reason it cannot be. Declaring is honest;
silence is how 200 tests stopped running.

Usage:  python scripts/test-dsn-coverage-gate.py
"""
from __future__ import annotations

import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOWS = os.path.join(REPO_ROOT, ".github", "workflows")
SEARCH_DIRS = ("services", "sdks", "tests")

#: Env-var reads in a test file, across the languages that have gated suites here.
READ = re.compile(
    r"""(?:os\.Getenv|os\.getenv|os\.environ\.get|os\.environ\[|getenv|std::env::var)"""
    r"""\s*[(\[]\s*['"]([A-Z][A-Z0-9_]*)['"]"""
)
#: The shape of a gating variable: it names a TEST resource.
GATING = re.compile(r"(^|_)TEST(_|$)")

#: Variables that genuinely cannot be armed in CI, with the reason. An entry here is a
#: DECLARATION, not an exemption — the tests still do not run, and saying so keeps that
#: fact visible instead of letting a skip read as a pass.
DECLARED_UNARMED: dict[str, str] = {
    "PIIKMS_TEST_KMS_ENDPOINT": (
        "needs a LocalStack-KMS container. The test it gates "
        "(`TestLive_ErasePII_WritesRealAuditRow`) proves that ErasePII's meta_read_audit "
        "row satisfies the migration-014/029 CHECK constraints — and its own docstring "
        "notes a CHECK violation would otherwise surface only AFTER the KEK is "
        "irreversibly shredded. Wiring LocalStack is worth doing; it is declared rather "
        "than silently missing so it stays on the board."
    ),
}


def is_test_file(rel: str) -> bool:
    base = os.path.basename(rel)
    return (
        "/tests/" in rel or "/test/" in rel
        or base.startswith("test_")
        or base.endswith(("_test.go", "_test.rs", "_test.py"))
    )


def main() -> int:
    gating: dict[str, set[str]] = {}
    for d in SEARCH_DIRS:
        root = os.path.join(REPO_ROOT, d)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames
                           if x not in {"node_modules", "__pycache__", "target", ".venv", "vendor"}]
            for fn in filenames:
                if not fn.endswith((".go", ".py", ".rs")):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, REPO_ROOT).replace(os.sep, "/")
                if not is_test_file(rel):
                    continue
                try:
                    with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                        body = fh.read()
                except OSError:
                    continue
                for name in READ.findall(body):
                    if GATING.search(name):
                        gating.setdefault(name, set()).add(rel)

    armed: set[str] = set()
    if os.path.isdir(WORKFLOWS):
        for fn in os.listdir(WORKFLOWS):
            if not fn.endswith((".yml", ".yaml")):
                continue
            with open(os.path.join(WORKFLOWS, fn), "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            for name in gating:
                if name in text:
                    armed.add(name)

    unarmed = {n: fs for n, fs in gating.items() if n not in armed and n not in DECLARED_UNARMED}
    declared = [n for n in gating if n in DECLARED_UNARMED]

    print(f"test-dsn-coverage-gate: {len(gating)} gating variable(s)")
    print(f"  {len(armed)} armed by a workflow")
    for n in sorted(declared):
        print(f"  DECLARED UNARMED — {n}")
        print(f"      {DECLARED_UNARMED[n].splitlines()[0]}")

    if not unarmed:
        print("OK — every gating variable is armed in CI or declared with its reason")
        return 0

    print("\n[gated tests that NO workflow arms]")
    print("  → a skip is indistinguishable from a pass in the summary line. Arm it in a")
    print("    workflow, or add it to DECLARED_UNARMED with the reason it cannot be.\n")
    for n, files in sorted(unarmed.items()):
        print(f"  {n}  ({len(files)} test file(s))")
        for f in sorted(files)[:4]:
            print(f"      {f}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
