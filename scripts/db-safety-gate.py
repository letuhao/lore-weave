#!/usr/bin/env python3
"""db-safety-gate.py — block destructive DB operations in TEST code.

THE INCIDENT THIS EXISTS TO PREVENT (2026-07): a migration test's cleanup ran an
UNSCOPED `DELETE FROM books` (no WHERE), and its `BOOK_TEST_DATABASE_URL` was pointed
at the REAL `loreweave_book` dev database. Running the test HARD-DELETED every user's
books — no trash, no owner scope, unrecoverable. Nothing stopped it.

This gate is the mechanical layer of a three-part defense (CLAUDE.md › "Destructive DB
ops in tests"): the CLAUDE.md rule (agents read it) + this commit gate + the runtime
`testsafe.EnsureThrowawayDB` guard in the test helpers.

Flags, in TEST files only (*_test.go, test_*.py / *_test.py / conftest.py, test *.sh):
  - an UNSCOPED `DELETE FROM <table>`  (no WHERE on the statement line)
  - any `TRUNCATE`
  - `DROP TABLE | DATABASE | SCHEMA`
and, in CI/compose/env config, a `*_TEST_*_URL` pointing at a BARE production DB name
(`loreweave_<svc>` with no test/smoke/audit/... marker) — the exact CI misconfig that
armed the incident.

Each finding must be FIXED (scope the statement with a WHERE; point the URL at a
throwaway DB whose name carries a marker; guard the helper with
`testsafe.EnsureThrowawayDB(current_database())`) OR consciously EXEMPTED with a pragma:
  - inline    `db-safety-gate: ok — <reason>`   on the finding line or the line above
  - file-wide `db-safety-gate: file-ok — <reason>` within the first 60 lines (for a pure
              sqlmock / SQL-string-assertion test file that never touches a real DB)
False positives are expected and fine — exempt them with a one-line reason.

Usage:
  python scripts/db-safety-gate.py            # full scan (CI / manual)
  python scripts/db-safety-gate.py --staged   # only git-staged files (pre-commit)
Exit 0 = clean (or all findings exempted). Exit 1 = an un-exempted finding.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEARCH_DIRS = ("services", "scripts", "infra", "sdks", "contracts", "crates")
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", ".next", ".git", "vendor", "coverage",
}

PRAGMA = "db-safety-gate:"            # inline / file-level exemption marker
FILE_PRAGMA = "db-safety-gate: file-ok"

# ── what counts as a TEST file (only there is unscoped destruction a landmine) ──
def is_test_file(path: str) -> bool:
    p = path.replace("\\", "/")
    base = p.rsplit("/", 1)[-1]
    if p.endswith("_test.go"):
        return True
    if base == "conftest.py" or (base.startswith("test_") and base.endswith(".py")) or base.endswith("_test.py"):
        return True
    if base.endswith(".sh") and ("test" in base):
        return True
    return False


# ── destructive statement detectors (SQL is case-insensitive) ──────────────────
# Anchored to an EXECUTED SQL string: the keyword must immediately follow an opening
# quote (", ', or backtick). This separates a real `DELETE FROM x` / "TRUNCATE y" /
# "DROP TABLE z" from the English words (a test message "should not truncate", a
# comment "hard-truncate") and from Go's time.Truncate()/text-truncate helpers.
_Q = r"""['"`]\s*"""
RE_DELETE = re.compile(_Q + r"DELETE\s+FROM\s+[\w\".`]+", re.I)
RE_WHERE = re.compile(r"\bWHERE\b", re.I)
RE_TRUNCATE = re.compile(_Q + r"TRUNCATE\b", re.I)
RE_DROP = re.compile(_Q + r"DROP\s+(TABLE|DATABASE|SCHEMA)\b", re.I)

# Lines that provably do NOT execute SQL against a DB — a string assertion or a
# sqlmock expectation. Skipped to keep the signal on real executions.
RE_NON_EXEC = re.compile(
    r"\bassert\b|ExpectExec|ExpectQuery|\bmock\b|in sql\b|in src\b|getMessage\(|\.args\[",
    re.I,
)

# ── config: a *_TEST_*_URL pointing at a BARE production DB name ───────────────
RE_TEST_URL = re.compile(r"(?i)\b[A-Z][A-Z0-9_]*TEST[A-Z0-9_]*(?:_URL|_DSN|_DB|_DATABASE_URL)\b")
RE_DBNAME = re.compile(r"/(loreweave_[a-z0-9_]+)")
RE_THROWAWAY = re.compile(r"(?i)(test|smoke|audit|scratch|throwaway|tmp|sandbox|ephemeral)")
CONFIG_EXT = (".yml", ".yaml", ".env", ".toml")


def _is_config(path: str) -> bool:
    p = path.replace("\\", "/")
    base = p.rsplit("/", 1)[-1]
    return p.endswith(CONFIG_EXT) or base.startswith(".env") or "docker-compose" in base or "/.github/" in p


class Finding:
    __slots__ = ("path", "line", "kind", "text")

    def __init__(self, path, line, kind, text):
        self.path, self.line, self.kind, self.text = path, line, kind, text

    def __str__(self):
        rel = os.path.relpath(self.path, REPO_ROOT).replace("\\", "/")
        return f"  {rel}:{self.line}  [{self.kind}]  {self.text.strip()[:120]}"


def _lines(path: str) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []


GUARDED_DIR = "db-safety-gate: guarded-dir"   # dir-level: fixtures here refuse a non-throwaway DSN
_dir_guard_cache: dict[str, bool] = {}


def _dir_is_guarded(path: str) -> bool:
    """True when the file's directory (or an ancestor up to the repo root) declares
    `db-safety-gate: guarded-dir` in a conftest.py or a `.db-safety-gate` sentinel —
    i.e. every DB fixture under it already refuses a non-throwaway DSN at runtime. One
    declaration exempts a whole guarded test tree (vs a pragma on every destructive line)."""
    d = os.path.dirname(os.path.abspath(path))
    root = os.path.abspath(REPO_ROOT)
    while d and d.startswith(root):
        if d not in _dir_guard_cache:
            found = False
            for cand in ("conftest.py", ".db-safety-gate"):
                fp = os.path.join(d, cand)
                if os.path.isfile(fp) and any(GUARDED_DIR in ln for ln in _lines(fp)):
                    found = True
                    break
            _dir_guard_cache[d] = found
        if _dir_guard_cache[d]:
            return True
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return False


def scan_test_file(path: str) -> list[Finding]:
    lines = _lines(path)
    if any(FILE_PRAGMA in ln for ln in lines[:60]):
        return []
    if _dir_is_guarded(path):
        return []
    out: list[Finding] = []
    for i, ln in enumerate(lines):
        if RE_NON_EXEC.search(ln):
            continue
        exempt = (PRAGMA in ln) or (i > 0 and PRAGMA in lines[i - 1])
        kind = None
        if RE_TRUNCATE.search(ln):
            kind = "TRUNCATE-in-test"
        elif RE_DROP.search(ln):
            kind = "DROP-in-test"
        elif RE_DELETE.search(ln) and not RE_WHERE.search(ln):
            kind = "unscoped-DELETE-in-test"
        if kind and not exempt:
            out.append(Finding(path, i + 1, kind, ln))
    return out


def scan_config_file(path: str) -> list[Finding]:
    out: list[Finding] = []
    for i, ln in enumerate(_lines(path)):
        if PRAGMA in ln:
            continue
        if not RE_TEST_URL.search(ln):
            continue
        m = RE_DBNAME.search(ln)
        if m and not RE_THROWAWAY.search(m.group(1)):
            out.append(Finding(path, i + 1, "test-URL→production-DB", ln))
    return out


def iter_files_full():
    for d in SEARCH_DIRS:
        root = os.path.join(REPO_ROOT, d)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIRS]
            for fn in filenames:
                yield os.path.join(dirpath, fn)
    # top-level configs (.github handled via walk of repo root's .github)
    gh = os.path.join(REPO_ROOT, ".github")
    for dirpath, _, filenames in os.walk(gh):
        for fn in filenames:
            yield os.path.join(dirpath, fn)


def iter_files_staged():
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, text=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return
    for rel in out.splitlines():
        rel = rel.strip()
        if rel:
            yield os.path.join(REPO_ROOT, rel)


def main() -> int:
    staged = "--staged" in sys.argv
    files = iter_files_staged() if staged else iter_files_full()
    findings: list[Finding] = []
    for path in files:
        if not os.path.isfile(path):
            continue
        if is_test_file(path):
            findings.extend(scan_test_file(path))
        elif _is_config(path):
            findings.extend(scan_config_file(path))

    if not findings:
        return 0

    print("✗ db-safety-gate: destructive DB operation(s) in test/config code:\n", file=sys.stderr)
    for f in findings:
        print(str(f), file=sys.stderr)
    print(
        "\nEach must be FIXED or EXEMPTED:\n"
        "  • unscoped DELETE  → add a WHERE that scopes to the test's own rows\n"
        "  • TRUNCATE / DROP  → guard the helper with testsafe.EnsureThrowawayDB(current_database())\n"
        "                       AND point the *_TEST_*_URL at a throwaway DB (name carries a marker)\n"
        "  • test-URL→prod DB → rename the target DB to carry a test/smoke marker\n"
        "  • genuine false positive (sqlmock, SQL-string assertion, already-guarded helper)\n"
        "      → inline  `db-safety-gate: ok — <reason>`  (finding line or line above)\n"
        "      → or file `db-safety-gate: file-ok — <reason>` near the top\n"
        "See CLAUDE.md › 'Destructive DB ops in tests'. Emergency bypass: git commit --no-verify.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
