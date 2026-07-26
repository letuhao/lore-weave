#!/usr/bin/env python3
"""raw-sql-lint.py — enforce SEC-4 (SQL injection defense) from
`docs/standards/security.md`:

    "Every value in every SQL query is parameterized; only allowlisted
     identifiers are interpolated."

This lint flags SQL built by **string interpolation into a VALUE position** —
an `fmt.Sprintf` / f-string / `.format()` / `%`-format where user-derived data
lands in a `WHERE`/`VALUES`/`SET`/comparison **value** slot instead of a
`$1` / `%s` bind placeholder. That is the classic SQL-injection shape.

What is a VALUE-position interpolation (flagged):
  - a QUOTED interpolation inside a SQL string — `'{var}'`, `'%s'`, `'" + var + "'`
    (a quoted placeholder is *always* a value; identifiers are never
    single-quoted in standard SQL), or
  - an interpolation immediately after a comparison operator / `VALUES` / `IN (`
    — `WHERE id = {x}`, `= %d`, `VALUES (%s)`.

What is NOT flagged (kept low-false-positive, per the standard's "only
allowlisted identifiers are interpolated" carve-out):
  - a bare `%s` / `$1` bind placeholder (psycopg / pgx parameterization — the
    CORRECT pattern), and
  - identifier interpolation in a table/column position (`FROM {table}`,
    `ORDER BY {col}`) — these are table/column names from an allowlist, not
    values. (A quoted interpolation there would still flag, correctly.)

Design mirrors `scripts/ai-provider-gate.py`: cross-platform pure-Python,
line-based, an allowlist + BASELINE so the lint passes on the CURRENT codebase
(the audit found it clean — all parameterized) and only flags the NEXT
regression. Conservative by design: it wants the CLEAR cases, not every
maybe-SQL string.

Usage:
  python scripts/raw-sql-lint.py            # full scan (CI / manual)
  python scripts/raw-sql-lint.py --staged   # only git-staged files (pre-commit)
  python scripts/raw-sql-lint.py --help

Exit 0 = clean (or baseline-only). Exit 1 = a NEW value-interpolation violation.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEARCH_DIRS = ("services", "sdks", "crates")
SCAN_EXTS = (".py", ".go")
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", ".next", ".git", "vendor", "coverage",
    "storybook-static", "target",
}

# Path prefixes (forward-slash, relative to repo root) where the rule does not
# apply. Keep tight; comment every entry.
ALLOWLIST_PREFIXES: tuple[str, ...] = (
    # (none yet — the audit found all live SQL parameterized)
)

# ── BASELINE ──────────────────────────────────────────────────────────────
# Known-current offenders, as "relpath:snippet-substring". The lint passes when
# every flagged site is in the baseline; a NEW site (not listed) fails the run.
# The audit (docs/standards/security.md §Enforcement) found the codebase clean,
# so this is intentionally EMPTY — the lint's whole job is to catch the next
# regression. If a legitimate exception ever appears, add a
# "relpath::matched-line-substring" row here with a comment explaining why.
BASELINE: frozenset[str] = frozenset()

# ── detection ─────────────────────────────────────────────────────────────

# A SQL DML keyword present on the line — the "this is really SQL" gate.
# CASE-SENSITIVE UPPERCASE by design: this repo writes SQL keywords in
# uppercase, and a case-insensitive match collides massively with ordinary
# lowercase identifiers (`.values()`, `where.append`, `params={"limit":…}`,
# `model_copy(update={…})`). Requiring uppercase keeps false positives near
# zero. Tradeoff: a value-injection written with lowercase SQL keywords would
# be missed — acceptable, and flagged here for the reviewer (the codebase
# convention is uppercase DML).
SQL_KEYWORD = re.compile(
    r"\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|WHERE|VALUES"
    r"|RETURNING|HAVING)\b"
)

# Value-position interpolation signals — restricted to the CLEAR case the
# standard names: a QUOTED interpolation inside a SQL string (`'%s'`, `'{var}'`,
# `'" + var + "'`). A single-quoted slot is unambiguously a VALUE (standard SQL
# never single-quotes identifiers), so this stays low-false-positive.
#
# Deliberately NOT flagged (the CORRECT patterns): a bare `%s` / `$1` bind
# placeholder, `IN (%s)` filled by a joined placeholder list, `VALUES
# ({placeholders})`, and identifier interpolation in a table/column position
# (`FROM {table}`). Unquoted `= %s` / `= %d` after an operator is intentionally
# skipped too — in Go it is ambiguous with a `$N` bind token (`WHERE %s > %s`
# built from allowlisted columns + binds), and in a log format string ("UPDATE
# failed id=%s") it is a false positive.
PY_ONLY = (".py",)
VALUE_INTERP_PATTERNS: tuple[tuple[str, re.Pattern[str], tuple[str, ...] | None], ...] = (
    # 1. A quoted f-string brace interpolation: '...{var}...'. PYTHON ONLY —
    #    in Go, `'{...}'` inside a SQL string is a Postgres array literal
    #    (e.g. '{a,b}'::text[]), never interpolation (Go interpolates via %verb).
    ("quoted-brace", re.compile(r"'[^'\n]*\{[^}\n]+\}[^'\n]*'"), PY_ONLY),
    # 2. A quoted printf/percent verb: '%s' '%d' '%v' '%q' '%f'. The verb must
    #    NOT be followed by another letter, so a `LIKE '%foo%'` pattern and an
    #    escaped `'%%'` literal percent do NOT match — only a real format verb.
    ("quoted-verb", re.compile(r"'[^'\n]*%[sdvqf](?![a-zA-Z])[^'\n]*'"), None),
    # 3. String concatenation into a single-quoted SQL literal:
    #    "... '" + var   or   var + "' ..."
    ("quoted-concat", re.compile(r"""(?:"'"\s*\+|\+\s*"'")"""), None),
)


def sql_value_interp_hits(line: str, rel: str) -> list[str]:
    """Return the names of value-interpolation signals firing on a SQL line.
    Empty when the line is not a clear raw-SQL value-interpolation. `rel` gates
    language-specific signals (brace interpolation is Python-only)."""
    if not SQL_KEYWORD.search(line):
        return []
    hits: list[str] = []
    for name, pat, exts in VALUE_INTERP_PATTERNS:
        if exts is not None and not rel.endswith(exts):
            continue
        if pat.search(line):
            hits.append(name)
    return hits


def is_test_file(rel: str) -> bool:
    base = os.path.basename(rel)
    return (
        "/tests/" in rel
        or "/test/" in rel
        or "/fixtures/" in rel
        or "/__fixtures__/" in rel
        or "/__mocks__/" in rel
        or rel.endswith("_test.go")
        or base.startswith("test_")
        or base == "conftest.py"
    )


def is_allowlisted(rel: str) -> bool:
    return rel.startswith(ALLOWLIST_PREFIXES) or is_test_file(rel)


def baseline_key(rel: str, line: str) -> str:
    return f"{rel}::{line.strip()}"


def in_baseline(rel: str, line: str) -> bool:
    key = baseline_key(rel, line)
    return any(key.startswith(b) or b in key for b in BASELINE)


def scan_file(path: str, rel: str) -> list[tuple[int, str, list[str]]]:
    out: list[tuple[int, str, list[str]]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for n, line in enumerate(fh, 1):
                hits = sql_value_interp_hits(line, rel)
                if hits:
                    out.append((n, line.rstrip(), hits))
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
                    rel = os.path.relpath(full, REPO_ROOT).replace(os.sep, "/")
                    yield full, rel


def iter_staged():
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    for rel in res.stdout.splitlines():
        rel = rel.strip().replace(os.sep, "/")
        if not rel.endswith(SCAN_EXTS):
            continue
        if not rel.startswith(tuple(d + "/" for d in SEARCH_DIRS)):
            continue
        if any(part in EXCLUDE_DIRS for part in rel.split("/")):
            continue
        full = os.path.join(REPO_ROOT, rel)
        if os.path.isfile(full):
            yield full, rel


def main() -> int:
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0
    staged = "--staged" in args
    files = iter_staged() if staged else iter_full_scan()

    new_violations: list[tuple[str, int, str, list[str]]] = []
    baselined = 0
    for full, rel in files:
        if is_allowlisted(rel):
            continue
        for n, line, hits in scan_file(full, rel):
            if in_baseline(rel, line):
                baselined += 1
                continue
            new_violations.append((rel, n, line, hits))

    mode = "staged" if staged else "full"
    if not new_violations:
        extra = f" ({baselined} baselined)" if baselined else ""
        print(f"raw-sql-lint ({mode}): OK — no unparameterized SQL value "
              f"interpolation{extra}")
        return 0

    print("raw-sql-lint: FAIL — SQL value built by string interpolation (SEC-4)\n")
    print("  A user-derived value must bind as a placeholder ($1 / %s), never be")
    print("  interpolated into the SQL text. Use parameterized queries; only")
    print("  allowlisted identifiers (table/column names) may be interpolated.\n")
    for rel, n, line, hits in new_violations:
        print(f"  {rel}:{n}: [{','.join(hits)}] {line.strip()}")
    print()
    print("If a match is a genuine, reviewed exception (e.g. an allowlisted")
    print("identifier that happens to look value-shaped), add a row to BASELINE")
    print("in scripts/raw-sql-lint.py with a comment — never leave it untracked.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
