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

#: A child with no timeout hangs the pre-commit hook forever, with no
#: output and nothing to kill but the terminal. Surfaced by the bite
#: harness's unbounded-child survey when this gate joined its table.
GIT_TIMEOUT_S = 60

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


def scan_file(path: str, rel: str, prefixes: tuple[str, ...] = ALLOWLIST_PREFIXES):
    """Return (violations, n_subjects, allow_used).

    `n_subjects` counts EVERY reference to a KAL-covered endpoint, owner-side
    included — this gate's reach is its DETECTOR, not its walk. Rename or
    restructure those routes and the pattern matches nothing anywhere, which
    exits 0 in the same bytes as compliance (BDR-82). Measured 2026-08-12: 8
    references, all 8 inside the exempt owning services."""
    subjects = 0
    allow_used: set[str] = set()
    out: list[tuple[int, str, str]] = []
    matched_prefix = next((pf for pf in prefixes if rel.startswith(pf)), None)
    exempt_owner = rel.startswith(EXEMPT_SERVICE_PREFIXES)
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for n, line in enumerate(fh, 1):
                if not KAL_COVERED.search(line):
                    continue
                subjects += 1
                if is_test_file(rel) or exempt_owner:
                    continue
                if matched_prefix is not None:
                    allow_used.add(matched_prefix)
                    continue
                out.append((n, rel, line.strip()[:160]))
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
            timeout=GIT_TIMEOUT_S,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
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
    violations: list[tuple[int, str, str]] = []
    subjects = 0
    allow_used: set[str] = set()
    n_files = 0
    for full, rel in it:
        n_files += 1
        v, sub, used = scan_file(full, rel, prefixes)
        violations.extend(v)
        subjects += sub
        allow_used |= used

    problems: list[str] = []
    if not staged:
        # ── SUBJECT FLOOR (GT-F3). Not a file count: zero files implies zero
        # subjects, so a file floor would be strictly shadowed by this one. What
        # can actually go wrong is the ROUTE SHAPE changing under the pattern.
        if subjects == 0:
            print(f"[knowledge-http-surface-gate] ERROR — {n_files} file(s) scanned and NOT ONE "
                  f"references a KAL-covered /internal endpoint, not even the owning services "
                  f"that serve them. The detector has no subject, so its silence proves "
                  f"nothing.", file=sys.stderr)
            return 2
        # ── SHRINK ARM (GT-F5).
        for pref in prefixes:
            if pref not in allow_used:
                problems.append(
                    f"ALLOWLIST_PREFIXES entry {pref!r} suppressed nothing in this tree — it "
                    f"exempts no read today and would exempt every one under that path the day "
                    f"one appears.")

    if not violations and not problems:
        print(f"[knowledge-http-surface-gate] PASS — no consumer hits the owning services' "
              f"bi-temporal knowledge /internal endpoints ({n_files} file(s); {subjects} "
              f"covered-endpoint reference(s), all owner-side; {len(prefixes)} allowlisted)")
        return 0

    if violations:
        print("[knowledge-http-surface-gate] FAIL — INV-KAL HTTP-surface violations "
              "(read bi-temporal knowledge through the KAL, not the owning service's "
              "/internal route):\n")
        for n, rel, line in violations:
            print(f"  [kal-covered-internal-read] {rel}:{n}\n      {line}")
        print("\nFix: call KNOWLEDGE_GATEWAY_URL /v1/kal/... (get_facts / get_canonical / "
              "timeline / list_attr_values / search / neighborhood / retrieve) instead of the "
              "owning service's /internal/* route.")
    for pr in problems:
        print(f"[knowledge-http-surface-gate] FAIL — {pr}")
    return 1


# ── SELF-TEST ────────────────────────────────────────────────────────────────
# Every probe tree carries an owner-side reference, so the subject floor stays
# quiet and each case below tests exactly one rule.
OWNER_ROUTE = 'ROUTE = "/internal/books/{book}/entities/{eid}/facts"\n'


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
                files = {"services/glossary-service/routes.py": OWNER_ROUTE, **files}
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

    print("knowledge-http-surface-gate --self-test")

    probe("an owner-side route definition passes", 0, {})

    # each covered endpoint, from a consumer
    for frag, label in (
        ("entities/e1/facts", "facts"),
        ("entities/e1/canonical-snapshot", "canonical-snapshot"),
        ("entities/e1/timeline", "timeline"),
        ("entities/e1/attr-values", "attr-values"),
        ("entities/search", "entities/search"),
        ("kg/neighborhood", "kg/neighborhood"),
        ("retrieve", "retrieve"),
    ):
        probe(f"a consumer calling {label} fails", 1, {
            "services/other/client.py": f'URL = "/internal/books/b1/{frag}"\n'})

    # …and the shapes that must NOT cry wolf
    probe("...but the authored entities LIST endpoint is not covered", 0, {
        "services/other/client.py": 'URL = "/internal/books/b1/entities"\n'})
    probe("...nor the KAL's own /v1/kal route", 0, {
        "services/other/client.py": 'URL = "/v1/kal/facts"\n'})
    probe("...nor a test file", 0, {
        "services/other/tests/t.py": 'URL = "/internal/books/b1/retrieve"\n'})
    probe("...nor the KAL federator itself", 0, {
        "services/knowledge-gateway/fed.py": 'URL = "/internal/books/b1/retrieve"\n'})

    # allowlist + shrink arm
    probe("an ALLOWLISTED prefix suppresses the read", 0, {
        "services/other/legacy/c.py": 'URL = "/internal/books/b1/retrieve"\n'},
        prefixes=("services/other/legacy/",))
    probe("...but a prefix that suppresses nothing fails", 1, {},
          prefixes=("services/ghost/",))

    # the subject floor
    probe("a tree with NO covered-endpoint reference is misuse", 2, {
        "services/other/main.py": "x = 1\n"}, seed=False)

    if failures:
        print(f"knowledge-http-surface-gate --self-test: {failures} rule(s) did not behave")
        return 2
    print("knowledge-http-surface-gate --self-test: every rule bites, and none cries wolf")
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
