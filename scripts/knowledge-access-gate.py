#!/usr/bin/env python3
"""knowledge-access-gate.py — enforce INV-KAL's table-read half.

Part of the Incremental Temporal Knowledge Architecture (spec
docs/specs/2026-06-29-incremental-temporal-knowledge-architecture.md §6D, §12.5.5).

INV-KAL: no service reads or writes the glossary EAV or the KG (Neo4j) except
through the Knowledge Access Layer (the knowledge-gateway, KAL). This gate is the
TABLE-READ half (D6 mechanism i): it fails when a CONSUMER service reads the
owning substrates directly instead of going through the KAL —

  1. the glossary EAV table `entity_attribute_values` referenced outside
     glossary-service (its owner). Consumers must read entity/lore knowledge via
     the KAL (or, transitionally, glossary's own /internal HTTP routes), never by
     querying the EAV table directly.
  2. the Neo4j driver used outside knowledge-service (the KG owner). The KAL itself
     reaches the KG over HTTP, so it does NOT import the driver either.

The HTTP-SURFACE half of INV-KAL (no consumer client targets the owning services'
/internal/* knowledge endpoints — forcing KAL usage over bespoke HTTP) is mechanism
(ii), tracked as DEFERRED `D-KAL-HTTP-SURFACE-LINT` and NOT enforced here yet. Until
both exist, INV-KAL is "table-read-enforced, HTTP-surface tracked-for-migration."

Mirrors scripts/ai-provider-gate.py (cross-platform; allowlist + --staged).

Usage:
  python scripts/knowledge-access-gate.py            # full scan (CI / manual)
  python scripts/knowledge-access-gate.py --staged   # only git-staged files (pre-commit)

Exit 0 = clean (or allowlisted-only). Exit 1 = violation.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Only services do direct DB/Neo4j access; the frontend is HTTP-only (scanning it
# yields false positives on doc comments that merely name the table).
SEARCH_DIRS = ("services",)
SCAN_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".mjs")
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", ".next", ".git", "vendor", "coverage",
}

# Owning services where a direct read of the substrate is BY DESIGN.
EAV_OWNER = "services/glossary-service/"       # owns entity_attribute_values
KG_OWNER = "services/knowledge-service/"        # owns the Neo4j KG

# Allowlisted KNOWN outliers (tracked, not enforced) — keep tight + comment each.
# These are the spec's named pre-existing direct reads (§12.5.5); they earn a DEFERRED
# row to migrate onto the KAL, but the gate enforces NEW violations without blocking on
# them. Remove an entry when its read is migrated.
ALLOWLIST_PREFIXES = (
    # enrichment one-off maintenance/cleanup script (not the runtime read path); the
    # spec's named "enrichment direct read" outlier → D-KAL-HTTP-SURFACE-LINT migration.
    "services/lore-enrichment-service/scripts/",
)

# ── detection patterns ────────────────────────────────────────────────
# The glossary EAV table by name (a direct query reference). The KAL + consumers
# must not name it; glossary itself (the owner) may. The match is intentionally BROAD
# (any mention, incl. a comment) — over-matching is the safe default for an invariant gate:
# a missed ORM/query-builder read is a silent INV-KAL breach, whereas a comment false
# positive is fixed by rewording or an ALLOWLIST_PREFIXES entry. (frontend is excluded —
# it is HTTP-only and only ever names the table in docs.)
EAV_READ = re.compile(r"\bentity_attribute_values\b")

# Neo4j driver usage: import or session/GraphDatabase access.
NEO4J_USE = re.compile(
    r"""(?:from\s+neo4j\s+import|import\s+neo4j\b|require\(['"]neo4j['"]\)"""
    r"""|neo4j\.GraphDatabase|GraphDatabase\.driver|\.session\(\s*database)"""
)


def is_test_file(rel: str) -> bool:
    base = os.path.basename(rel)
    return (
        "/tests/" in rel or "/test/" in rel or "/fixtures/" in rel
        or "/__fixtures__/" in rel or "/__mocks__/" in rel
        or rel.endswith("_test.go")
        or base.startswith("test_")
        or base.endswith((".spec.ts", ".spec.tsx", ".test.ts", ".test.tsx"))
        or base == "conftest.py"
    )


def scan_file(path: str, rel: str, prefixes: tuple[str, ...] = ALLOWLIST_PREFIXES):
    """Return (violations, subjects, allow_used) for one file.

    `subjects` counts EVERY mention of each substrate, owner-side included — it is
    this gate's REACH. The rule's subject is the name `entity_attribute_values`
    and the Neo4j driver; rename either and the scan finds nothing everywhere and
    passes, which is byte-identical to compliance (BDR-82). Measured 2026-08-12:
    362 EAV mentions (359 owner-side) and 10 Neo4j uses (9 owner-side).

    `allow_used` is which ALLOWLIST_PREFIXES rows actually suppressed something,
    so a row that excuses nothing can be found (GT-F5)."""
    subjects = {"eav": 0, "neo4j": 0}
    allow_used: set[str] = set()
    out: list[tuple[str, int, str, str]] = []
    matched_prefix = next((p for p in prefixes if rel.startswith(p)), None)
    in_eav_owner = rel.startswith(EAV_OWNER)
    in_kg_owner = rel.startswith(KG_OWNER)
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for n, line in enumerate(fh, 1):
                hit_eav = bool(EAV_READ.search(line))
                hit_kg = bool(NEO4J_USE.search(line))
                if hit_eav:
                    subjects["eav"] += 1
                if hit_kg:
                    subjects["neo4j"] += 1
                if is_test_file(rel):
                    continue
                if matched_prefix is not None:
                    if hit_eav or hit_kg:
                        allow_used.add(matched_prefix)
                    continue
                if not in_eav_owner and hit_eav:
                    out.append(("eav-direct-read", n, rel, line.strip()[:160]))
                if not in_kg_owner and hit_kg:
                    out.append(("neo4j-direct-use", n, rel, line.strip()[:160]))
    except OSError:
        pass
    return out, subjects, allow_used


def iter_full_scan(repo_root: str = REPO_ROOT, search_dirs=SEARCH_DIRS):
    for d in search_dirs:
        root = os.path.join(repo_root, d)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIRS]
            for fn in filenames:
                if fn.endswith(SCAN_EXTS):
                    full = os.path.join(dirpath, fn)
                    yield full, os.path.relpath(full, repo_root).replace("\\", "/")


def iter_staged():
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    for rel in out.splitlines():
        rel = rel.strip().replace("\\", "/")
        if rel.endswith(SCAN_EXTS) and rel.startswith(SEARCH_DIRS):
            full = os.path.join(REPO_ROOT, rel)
            if os.path.isfile(full):
                yield full, rel


def check(repo_root: str = REPO_ROOT, search_dirs=SEARCH_DIRS,
          prefixes: tuple[str, ...] = ALLOWLIST_PREFIXES, staged: bool = False) -> int:
    """The REAL checker, parameterised so `--self-test` can drive it over a
    synthetic tree instead of re-implementing its rules."""
    it = iter_staged() if staged else iter_full_scan(repo_root, search_dirs)
    violations: list[tuple[str, int, str, str]] = []
    subjects = {"eav": 0, "neo4j": 0}
    allow_used: set[str] = set()
    n_files = 0
    for full, rel in it:
        n_files += 1
        v, sub, used = scan_file(full, rel, prefixes)
        violations.extend(v)
        subjects["eav"] += sub["eav"]
        subjects["neo4j"] += sub["neo4j"]
        allow_used |= used

    problems: list[str] = []
    if not staged:
        # ── REACH FLOOR (GT-F3), as a SUBJECT floor only. There is deliberately
        # no separate `n_files == 0` clause: zero files implies zero subjects, so
        # it would be strictly shadowed and deletable with the suite green
        # (`GTD-7`). That is the general rule, learned the hard way five times on
        # this board — **where a subject floor exists, a file-count floor is
        # always shadowed by it.** Renaming either substrate leaves this gate
        # matching nothing anywhere and exiting 0, and that is what the floor is
        # for.
        for name, label in (("eav", "entity_attribute_values"),
                            ("neo4j", "the Neo4j driver")):
            if subjects[name] == 0:
                print(f"[knowledge-access-gate] ERROR — {n_files} file(s) scanned and NOT ONE "
                      f"mentions {label}, not even its owning service. The detector has no "
                      f"subject, so its silence proves nothing.", file=sys.stderr)
                return 2
        # ── SHRINK ARM (GT-F5): a prefix that suppressed nothing.
        for pref in prefixes:
            if pref not in allow_used:
                problems.append(
                    f"ALLOWLIST_PREFIXES entry {pref!r} suppressed no direct read in this tree — "
                    f"it exempts nothing today and would exempt everything under that path the "
                    f"day one appears. Delete the row, or fix the path.")

    if not violations and not problems:
        print(f"[knowledge-access-gate] PASS — no direct EAV/Neo4j reads outside the owning "
              f"services ({n_files} file(s); {subjects['eav']} EAV mention(s), "
              f"{subjects['neo4j']} Neo4j use(s), {len(prefixes)} allowlisted prefix(es))")
        return 0

    if violations:
        print("[knowledge-access-gate] FAIL — INV-KAL table-read violations "
              "(read entity/KG knowledge through the KAL, not the substrate directly):\n")
        for kind, n, rel, line in violations:
            print(f"  [{kind}] {rel}:{n}\n      {line}")
        print("\nFix: route the read through knowledge-gateway (the KAL) / the owning service's "
              "internal API. If this is a legitimate owner-side read, confirm the file lives under "
              "the owning service.")
    for p in problems:
        print(f"[knowledge-access-gate] FAIL — {p}")
    return 1


# ── SELF-TEST ────────────────────────────────────────────────────────────────
# Every probe tree carries an owner-side mention of BOTH substrates, so the two
# subject floors stay quiet and each case tests exactly one rule.
OWNER_EAV = "SELECT * FROM entity_attribute_values WHERE x = 1\n"
OWNER_KG = "from neo4j import GraphDatabase\n"


def self_test() -> int:
    import contextlib
    import io
    import tempfile

    failures = 0

    def probe(name: str, want: int, files: dict[str, str], *,
              prefixes: tuple[str, ...] = (), seed: bool = True) -> None:
        nonlocal failures
        with tempfile.TemporaryDirectory() as d:
            if seed:
                files = {
                    "services/glossary-service/repo.py": OWNER_EAV,
                    "services/knowledge-service/kg.py": OWNER_KG,
                    **files,
                }
            for rel, body in files.items():
                full = os.path.join(d, *rel.split("/"))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(body)
            os.makedirs(os.path.join(d, "services"), exist_ok=True)
            try:
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    got = check(d, ("services",), prefixes)
            except Exception as e:  # noqa: BLE001 - a crash is what this asserts against
                failures += 1
                print(f"  FAIL {name}: raised {type(e).__name__}: {e} — it must return a code")
                return
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: rc={got} (want {want})")

    print("knowledge-access-gate --self-test")

    probe("owner-side reads of both substrates pass", 0, {})

    # the two rules
    probe("a consumer naming entity_attribute_values fails", 1, {
        "services/other/repo.py": OWNER_EAV})
    probe("a consumer importing the Neo4j driver fails", 1, {
        "services/other/kg.py": OWNER_KG})
    probe("...including the require() form", 1, {
        "services/other/kg.ts": "const neo4j = require('neo4j')\n"})
    probe("...and GraphDatabase.driver", 1, {
        "services/other/kg.py": "d = GraphDatabase.driver(uri)\n"})

    # …and the shapes that must NOT cry wolf
    probe("...but a test file is excluded", 0, {
        "services/other/tests/t.py": OWNER_EAV})
    probe("...and so is a test_*.py", 0, {
        "services/other/test_repo.py": OWNER_EAV})
    probe("...and an unrelated file is clean", 0, {
        "services/other/main.py": "x = 1\n"})

    # the allowlist + its shrink arm
    probe("an ALLOWLISTED prefix suppresses the read", 0, {
        "services/other/scripts/x.py": OWNER_EAV}, prefixes=("services/other/scripts/",))
    probe("...but a prefix that suppresses nothing fails", 1, {},
          prefixes=("services/ghost/scripts/",))

    # floors
    probe("no files at all is misuse (the subject floor catches it)", 2, {}, seed=False)
    probe("a tree that never mentions the EAV table is misuse", 2, {
        "services/knowledge-service/kg.py": OWNER_KG,
        "services/other/main.py": "x = 1\n"}, seed=False)
    probe("a tree that never uses the Neo4j driver is misuse", 2, {
        "services/glossary-service/repo.py": OWNER_EAV,
        "services/other/main.py": "x = 1\n"}, seed=False)

    if failures:
        print(f"knowledge-access-gate --self-test: {failures} rule(s) did not behave")
        return 2
    print("knowledge-access-gate --self-test: every rule bites, and none cries wolf")
    return 0


def main() -> int:
    if "--self-test" in sys.argv or "--selftest" in sys.argv:
        return self_test()
    rc = self_test()
    if rc:
        return rc
    print()
    return check(staged="--staged" in sys.argv)


if __name__ == "__main__":
    sys.exit(main())
