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


def scan_file(path: str, rel: str) -> list[tuple[str, int, str, str]]:
    """Return (kind, lineno, rel, line) INV-KAL violations for one file."""
    if is_test_file(rel) or rel.startswith(ALLOWLIST_PREFIXES):
        return []
    in_eav_owner = rel.startswith(EAV_OWNER)
    in_kg_owner = rel.startswith(KG_OWNER)
    out: list[tuple[str, int, str, str]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for n, line in enumerate(fh, 1):
                if not in_eav_owner and EAV_READ.search(line):
                    out.append(("eav-direct-read", n, rel, line.strip()[:160]))
                if not in_kg_owner and NEO4J_USE.search(line):
                    out.append(("neo4j-direct-use", n, rel, line.strip()[:160]))
    except OSError:
        pass
    return out


def iter_full_scan():
    for d in SEARCH_DIRS:
        root = os.path.join(REPO_ROOT, d)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIRS]
            for fn in filenames:
                if fn.endswith(SCAN_EXTS):
                    full = os.path.join(dirpath, fn)
                    yield full, os.path.relpath(full, REPO_ROOT).replace("\\", "/")


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


def main() -> int:
    staged = "--staged" in sys.argv
    it = iter_staged() if staged else iter_full_scan()
    violations: list[tuple[str, int, str, str]] = []
    for full, rel in it:
        violations.extend(scan_file(full, rel))

    if not violations:
        print("[knowledge-access-gate] PASS — no direct EAV/Neo4j reads outside the owning services")
        return 0

    print("[knowledge-access-gate] FAIL — INV-KAL table-read violations "
          "(read entity/KG knowledge through the KAL, not the substrate directly):\n")
    for kind, n, rel, line in violations:
        print(f"  [{kind}] {rel}:{n}\n      {line}")
    print("\nFix: route the read through knowledge-gateway (the KAL) / the owning service's "
          "internal API. If this is a legitimate owner-side read, confirm the file lives under "
          "the owning service.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
