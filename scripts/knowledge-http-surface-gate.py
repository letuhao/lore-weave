#!/usr/bin/env python3
"""knowledge-http-surface-gate.py — enforce INV-KAL's HTTP-surface half (D6 mechanism ii).

Part of the Incremental Temporal Knowledge Architecture (spec
docs/specs/2026-06-29-incremental-temporal-knowledge-architecture.md §6D, §12.5.5).
Companion to scripts/knowledge-access-gate.py (the TABLE-READ half).

INV-KAL: entity/lore KNOWLEDGE is read through the Knowledge Access Layer (the
knowledge-gateway, KAL), never by a consumer reaching the owning services' bespoke
`/internal/*` KNOWLEDGE routes over HTTP. This gate is the HTTP-SURFACE half: it
FAILS when a CONSUMER service references one of the owning services' bi-temporal
knowledge-read `/internal/*` endpoints that the KAL federates —

  glossary-service:  /internal/books/{book}/entities/{entity}/facts
                     /internal/books/{book}/entities/{entity}/canonical-snapshot
                     /internal/books/{book}/entities/{entity}/timeline
                     /internal/books/{book}/entities/{entity}/attr-values
                     /internal/books/{book}/entities/search        (KAL `search`)
  knowledge-service: /internal/books/{book}/kg/neighborhood        (KAL `neighborhood`)
                     /internal/books/{book}/retrieve               (KAL `retrieve`)

— read these through `KNOWLEDGE_GATEWAY_URL` (`/v1/kal/...`) instead.

SCOPE (deliberately matched to the table-read gate): INV-KAL governs the DERIVED
bi-temporal knowledge substrate — the EAV-projected facts + the KG. The AUTHORED
entity CATALOG (`glossary_entities`: name / kind / short_description, served by the
`/internal/books/{book}/entities` LIST endpoint that KAL `roster` thins to id+name)
is NOT part of that substrate — it is the authored source consumers may read
directly, exactly as the table-read gate exempts `glossary_entities`. So the LIST
endpoint is NOT flagged here; only the bi-temporal reads above are.

The owning services (glossary, knowledge) themselves and the KAL (knowledge-gateway)
are exempt — they ARE the endpoints / the federator.

Mirrors scripts/knowledge-access-gate.py (cross-platform; allowlist + --staged).

Usage:
  python scripts/knowledge-http-surface-gate.py            # full scan (CI / manual)
  python scripts/knowledge-http-surface-gate.py --staged   # only git-staged files (pre-commit)

Exit 0 = clean (or allowlisted-only). Exit 1 = violation.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEARCH_DIRS = ("services",)
SCAN_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".mjs")
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", ".next", ".git", "vendor", "coverage",
}

# Owners + the KAL itself are exempt: they ARE the endpoints / the federator.
EXEMPT_SERVICE_PREFIXES = (
    "services/glossary-service/",     # owns the glossary /internal routes
    "services/knowledge-service/",    # owns the knowledge /internal routes
    "services/knowledge-gateway/",    # the KAL — the SANCTIONED federator of these routes
)

# Allowlisted KNOWN outliers (tracked, not enforced) — keep tight + comment each.
ALLOWLIST_PREFIXES: tuple[str, ...] = (
    # (none — the bi-temporal knowledge reads are fully migrated to the KAL.)
)

# ── detection patterns ────────────────────────────────────────────────
# The owning services' bi-temporal knowledge-read /internal endpoints the KAL
# federates. Matched as a path fragment in a string literal / URL build. The
# entity/book ids are templated, so the patterns tolerate any non-slash/quote run
# (f-string interpolation, path params) between the fixed segments. The authored
# entities-LIST endpoint is intentionally NOT here (authored catalog, see header).
_BOOK = r"/internal/books/[^\s\"'`]*"
KAL_COVERED = re.compile(
    r"(?:"
    rf"{_BOOK}/entities/[^\s\"'`]*/(?:facts|canonical-snapshot|timeline|attr-values)\b"
    rf"|{_BOOK}/entities/search\b"
    rf"|{_BOOK}/kg/neighborhood\b"
    rf"|{_BOOK}/retrieve\b"
    r")"
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


def scan_file(path: str, rel: str) -> list[tuple[int, str, str]]:
    if is_test_file(rel) or rel.startswith(ALLOWLIST_PREFIXES) or rel.startswith(EXEMPT_SERVICE_PREFIXES):
        return []
    out: list[tuple[int, str, str]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for n, line in enumerate(fh, 1):
                if KAL_COVERED.search(line):
                    out.append((n, rel, line.strip()[:160]))
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
    violations: list[tuple[int, str, str]] = []
    for full, rel in it:
        violations.extend(scan_file(full, rel))

    if not violations:
        print("[knowledge-http-surface-gate] PASS — no consumer hits the owning services' "
              "bi-temporal knowledge /internal endpoints (read them through the KAL)")
        return 0

    print("[knowledge-http-surface-gate] FAIL — INV-KAL HTTP-surface violations "
          "(read bi-temporal knowledge through the KAL, not the owning service's /internal route):\n")
    for n, rel, line in violations:
        print(f"  [kal-covered-internal-read] {rel}:{n}\n      {line}")
    print("\nFix: call KNOWLEDGE_GATEWAY_URL /v1/kal/... (get_facts / get_canonical / timeline / "
          "list_attr_values / search / neighborhood / retrieve) instead of the owning service's "
          "/internal/* route.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
