#!/usr/bin/env python3
"""db-safety-gate.py — block destructive DB operations in TEST code.

THE INCIDENT THIS EXISTS TO PREVENT (2026-07): a migration test's cleanup ran an
UNSCOPED `DELETE FROM books` (no WHERE), and its `BOOK_TEST_DATABASE_URL` was pointed
at the REAL `loreweave_book` dev database. Running the test HARD-DELETED every user's
books — no trash, no owner scope, unrecoverable. Nothing stopped it.

This gate is the mechanical layer of a three-part defense (CLAUDE.md › "Destructive DB
ops in tests"): the CLAUDE.md rule (agents read it) + this commit gate + the runtime
`testsafe.EnsureThrowawayDB` guard in the test helpers.

Flags, in TEST files only (*_test.go, test_*.py / *_test.py / conftest.py, and any
*.sh whose name carries a harness marker: test | smoke | drill):
  - an UNSCOPED `DELETE FROM <table>`  (no WHERE on the statement line)
  - any `TRUNCATE`
  - `DROP TABLE | DATABASE | SCHEMA`
and, in CI/compose/env config, a `*_TEST_*_URL` pointing at a BARE production DB name
(`loreweave_<svc>` with no test/smoke/audit/... marker) — the exact CI misconfig that
armed the incident.

Two further checks, both added 2026-08-09 after each caught something the others missed:
  - in `.github/workflows/` ONLY, ANY Postgres DSN assigned to an env var must name a
    database carrying a throwaway marker, whatever the variable is called. The
    `*_TEST_*_URL` rule above needs `TEST` in the name AND a `loreweave_` database;
    `LW_INTEGRATION_META_DB: …/metaworker_meta` satisfied neither, and that DSN was
    handed straight to a helper that applies `DROP TABLE IF EXISTS events`. Restricted
    to workflows because a compose file or service `.env` legitimately names a real
    database, and a CI job never does.
  - every vendored `testsafe/testsafe.go` must be byte-identical. Go's per-module layout
    forces the runtime guard to be copied rather than imported (five copies as of
    2026-08-09), and a fix that reaches four of them leaves the fifth silently accepting
    a production DSN.

Scanning is a DENYLIST over the whole repo (EXCLUDE_DIRS), not an allowlist of trees.
The allowlist it replaced omitted `tests/` — where the cross-service live smokes live —
so this gate reported PASS over the most destructive test code in the repo.

Each finding must be FIXED (scope the statement with a WHERE; point the URL at a
throwaway DB whose name carries a marker; guard the helper with
`testsafe.EnsureThrowawayDB(current_database())`) OR consciously EXEMPTED with a pragma:
  - inline    `db-safety-gate: ok — <reason>`   on the finding line or the line above
  - file-wide `db-safety-gate: file-ok — <reason>` ANYWHERE in the file (for a pure
              sqlmock / SQL-string-assertion test file that never touches a real DB,
              or a harness whose target DB name is a non-overridable literal)
False positives are expected and fine — exempt them with a one-line reason.

Usage:
  python scripts/db-safety-gate.py            # full scan (CI / manual)
  python scripts/db-safety-gate.py --staged   # only git-staged files (pre-commit)
Exit 0 = clean (or all findings exempted). Exit 1 = an un-exempted finding.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Scanning is a DENYLIST — see iter_files_full() for why the allowlist that used to
# live here (SEARCH_DIRS) let the whole `tests/` tree through unscanned. Anything added
# to this set is an explicit, reviewable decision not to look; anything new in the repo
# is scanned by default.
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", ".next", ".git", "vendor", "coverage",
}

PRAGMA = "db-safety-gate:"            # inline / file-level exemption marker
FILE_PRAGMA = "db-safety-gate: file-ok"

# Filename markers that identify a shell script as a TEST HARNESS. Distinct from
# RE_THROWAWAY below on purpose — see the note in is_test_file().
RE_TEST_SCRIPT = re.compile(r"(?i)(test|smoke|drill)")

# ── what counts as a TEST file (only there is unscoped destruction a landmine) ──
def is_test_file(path: str) -> bool:
    p = path.replace("\\", "/")
    base = p.rsplit("/", 1)[-1]
    if p.endswith("_test.go"):
        return True
    if base == "conftest.py" or (base.startswith("test_") and base.endswith(".py")) or base.endswith("_test.py"):
        return True
    # A shell script qualifies on any marker that names it as a HARNESS.
    #
    # This said `"test" in base` until a `*-smoke.sh` that DROPs and CREATEs a
    # database walked straight past the gate — and it was not alone: widening it
    # brought SIX previously-unscanned scripts into scope on the first run, every
    # one of them dropping a database. `smoke` was already an accepted marker
    # twenty lines below (RE_THROWAWAY), so one half of the gate knew the word
    # counted and the other did not (docs/standards/non-vacuity.md, NV-4).
    #
    # It is deliberately NOT RE_THROWAWAY, though, and the first attempt to reuse
    # it was wrong: the two vocabularies answer different questions. In a DATABASE
    # NAME, `audit` means "this database is disposable". In a FILE NAME it means
    # "this operates on audit data" — and reusing the set pulled in
    # event-audit-retention-cron.sh, a PRODUCTION cron whose partition drops are
    # its whole job. Same word, opposite meaning, one directory apart.
    if base.endswith(".sh") and RE_TEST_SCRIPT.search(base):
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
# A Postgres DSN assigned to an env var in a CI workflow: capture the var name and the
# database name. Matches any `*_DB`/`*_DSN`/`*_DATABASE_URL`/`*_URL`, not only ones
# carrying `TEST` — see scan_config_file() for the name that slipped through.
RE_CI_DSN = re.compile(
    r"""\b([A-Z][A-Z0-9_]*(?:_DB|_DSN|_DATABASE_URL|_URL))\s*:\s*["']?postgres(?:ql)?://"""
    r"""[^/\s"']*/([A-Za-z0-9_]+)"""
)
CONFIG_EXT = (".yml", ".yaml", ".env", ".toml")

# ── test code: a SCHEMA-RESETTING fixture reading a PRODUCTION DSN (K29) ───────
# The check above only inspects CI/compose config — it never sees what a test
# fixture reads at runtime. lore-enrichment's DB conftest did:
#     os.environ.get("TEST_LORE_ENRICHMENT_DB_URL") or os.environ.get("LORE_ENRICHMENT_DB_URL")
# and then ran run_down_migrations() (DROP TABLE ×12). A root-conftest
# `os.environ.setdefault(...)` placeholder does NOT protect: setdefault is a no-op
# when the var is already exported, which it is in any compose/dev shell. Reproduced
# against a decoy: 39 tests PASSED green while every table was dropped and the seeded
# row destroyed. So: reading a NON-TEST `*_DB_URL`/`*_DATABASE_URL`/`*_DSN` in a test
# fixture that can reset the schema is a finding, guarded-dir or not — the dedicated
# TEST_ var is the only admissible source. (Assignment — `os.environ["X_DB_URL"] =
# <throwaway>` — is fine: that SETS a test DSN rather than inheriting a live one.)
RE_PROD_DSN_ENV = re.compile(
    r"""(?:environ(?:\.get)?|getenv)\s*[\(\[]\s*["']((?!\w*TEST)[A-Z][A-Z0-9_]*"""
    r"""(?:_DB_URL|_DATABASE_URL|_DSN))["']"""
)
RE_ENV_ASSIGN = re.compile(r"""environ\s*\[\s*["'][A-Z0-9_]+["']\s*\]\s*=""")
# Scoped deliberately NARROW so the gate never cries wolf. It fires only where the
# combination is data-loss shaped: a production DSN reaching a fixture that RESETS
# THE SCHEMA (a conftest supplying a DSN to a whole tree, or any file invoking a
# down-migration/drop helper). Plain `*_db.py` tests that read a prod DSN and clean
# up with SCOPED deletes are NOT this class — the scoped delete is the sanctioned
# pattern, and flagging them here would train people to bypass the gate.
RE_SCHEMA_RESET = re.compile(
    r"\b(run_down_migrations|down_migrations|drop_all|reset_schema|drop_schema|DOWN_DDL)\b"
)


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


def _pragma_near(lines: list[str], idx: int) -> bool:
    """A reason on this line, or anywhere in the comment block attached to it.

    **This was a FIXED ONE-LINE-ABOVE WINDOW, and that is the third time this
    repo shipped that exact bug** — `closed-set-gate` and `zero-digest-gate` both
    had it, and in `zero-digest-gate` the one live finding's real justification
    sat eleven lines up, so the pragma did NOTHING and the bite-test that
    "proved" it worked reported the finding both with and without it. A vacuous
    check that looks green, which is the failure the whole non-vacuity discipline
    exists to catch.

    A destructive statement worth exempting needs a REASON, and a reason worth
    reading is more than one line. Forcing it onto the single line above pushes
    authors toward a terse pragma or toward `--no-verify`. So walk the contiguous
    comment block upward rather than guessing a distance.
    """
    if PRAGMA in lines[idx]:
        return True
    k = idx - 1
    while k >= 0:
        stripped = lines[k].strip()
        is_comment = stripped.startswith(("#", "//", "///", "//!", "*", "/*"))
        if is_comment or stripped == "":
            if PRAGMA in lines[k]:
                return True
            # A blank line ends the block unless the run of comments continues
            # above it (an intentionally spaced comment paragraph).
            if stripped == "" and not (
                k > 0 and lines[k - 1].strip().startswith(("#", "//", "*"))
            ):
                break
            k -= 1
            continue
        break
    return False


def scan_test_file(path: str) -> list[Finding]:
    lines = _lines(path)
    # Anywhere in the file, NOT a fixed leading window.
    #
    # This was `lines[:60]`, and it bit on its second use: restore-drill.sh's
    # exemption sits at line 69, beside the `DRILL_DB="drill_${DRILL_TS}"` line
    # it explains, because that is where a reader needs to see it. The author
    # writes the reason next to the reason; the window then discards it and
    # reports the file as un-exempted, which reads as "you did not write one".
    #
    # This is the fourth non-vacuity shape by name — the escape hatch cannot
    # reach its reason (docs/standards/non-vacuity.md, NV-5), already recorded
    # against three sibling gates. A file-level pragma is a deliberate marker
    # carrying a written justification; there is no threat model in which
    # hiding it below an arbitrary line number is the abuse to defend against.
    if any(FILE_PRAGMA in ln for ln in lines):
        return []
    out: list[Finding] = []
    # The production-DSN read is checked FIRST and is NOT exempted by guarded-dir:
    # a runtime guard refuses a bad DSN, but the fallback itself should not exist —
    # defence in depth for a data-loss class that already shipped once (K29). Only
    # applies where a wipe is actually reachable: a conftest (its DSN feeds a whole
    # tree) or a file that invokes a schema-reset helper.
    resets_schema = any(RE_SCHEMA_RESET.search(ln) for ln in lines)
    if resets_schema or os.path.basename(path) == "conftest.py":
        for i, ln in enumerate(lines):
            if RE_NON_EXEC.search(ln) or PRAGMA in ln or RE_ENV_ASSIGN.search(ln):
                continue
            if RE_PROD_DSN_ENV.search(ln):
                out.append(Finding(path, i + 1, "production-DSN-read-in-test", ln))
    if _dir_is_guarded(path):
        return out
    for i, ln in enumerate(lines):
        if RE_NON_EXEC.search(ln):
            continue
        exempt = _pragma_near(lines, i)
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
    in_workflow = "/.github/workflows/" in path.replace("\\", "/")
    for i, ln in enumerate(_lines(path)):
        if PRAGMA in ln:
            continue
        if RE_TEST_URL.search(ln):
            m = RE_DBNAME.search(ln)
            if m and not RE_THROWAWAY.search(m.group(1)):
                out.append(Finding(path, i + 1, "test-URL→production-DB", ln))
                continue
        # A CI job's DSN must name a THROWAWAY database, whatever the variable is
        # called. The check above needs `TEST` in the variable name AND a
        # `loreweave_`-prefixed database; `LW_INTEGRATION_META_DB: …/metaworker_meta`
        # satisfied neither, so it was invisible twice over — while
        # `metaworker_live_smoke` handed that DSN straight to `mustApply`. The moment
        # the runtime guard moved into `mustApply` (2026-08-09) that CI job would have
        # gone red, and the gate would have had nothing to say about why.
        #
        # Workflows only: a compose file or a service `.env` legitimately names a real
        # database, because that is the service's actual database. A GitHub Actions job
        # has no production data to point at and nothing to gain from pretending
        # otherwise, so here the throwaway marker is simply required.
        if in_workflow:
            m = RE_CI_DSN.search(ln)
            if m and not RE_THROWAWAY.search(m.group(2)):
                out.append(Finding(path, i + 1, "CI-DSN→unmarked-DB", ln))
    return out


def iter_files_full():
    """Walk the WHOLE repo minus EXCLUDE_DIRS — deliberately not an allowlist.

    THE BLIND SPOT THIS CLOSES. This used to iterate SEARCH_DIRS = (services, scripts,
    infra, sdks, contracts, crates) plus .github. `tests/` was not in it, and `tests/`
    is where the cross-service live smokes live — four harnesses that apply
    `contracts/migrations/per_reality/*.up.sql`, one of which opens with
    `DROP TABLE IF EXISTS events`, against whatever `LW_INTEGRATION_DB` points at. The
    gate whose entire purpose is destructive-SQL-in-test-code could not see the most
    destructive test code in the repo, and reported PASS the whole time.

    Nobody excluded `tests/`. It was never included — which is the point. An enumerated
    allowlist is default-UNCOVERED (NV-3): a new top-level tree is invisible until
    someone remembers to add it, and nothing anywhere fails to remind them. A denylist
    is default-COVERED: a new tree is scanned on the day it appears, and the only way
    out is an explicit entry in EXCLUDE_DIRS that a reviewer can see.

    That is the same polarity bug as the hand-written migration lists this gate now
    catches, and the same one `hot-path-gate.py` had. Third time in this repo.
    """
    skip_top = {".git"}
    #: Agent scratch CHECKOUTS of this repo. Every file under here is a copy of a
    #: file the walk already visited, so scanning them reports this tree's own code
    #: back N times under paths nobody can commit — measured on the merged tree, that
    #: was 100% of this gate's findings. Excluded by PATH, not by adding `worktrees`
    #: to EXCLUDE_DIRS: that name is generic enough that a real `worktrees/` of this
    #: repo's own source would go dark, which is the silent-reach failure the
    #: whole-repo walk exists to prevent. `dep-pinning-lint.sh` hit the identical
    #: thing (600 of its 675 `go.mod` were scratch copies) and its header says so.
    worktrees = os.path.join(REPO_ROOT, ".claude", "worktrees")
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        if dirpath == worktrees:
            dirnames[:] = []
            continue
        dirnames[:] = [
            x for x in dirnames
            if x not in EXCLUDE_DIRS and not (dirpath == REPO_ROOT and x in skip_top)
        ]
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


def check_testsafe_copies() -> list[str]:
    """Every `testsafe/testsafe.go` in the repo must be byte-identical.

    Go's per-service go.mod layout means the runtime guard cannot be imported across
    module boundaries without a `replace` line, so it is VENDORED — as of 2026-08-09
    there are five copies (book-service, glossary-service, usage-billing-service,
    integrity-checker, admin-cli). Five copies of a safety check is five chances for a
    fix to land in one and not the others, and the failure would be silent: four
    services keep refusing a production DSN while the fifth quietly accepts it.

    `throwawayMarker` is the specific hazard. Adding a marker to one copy widens what
    that service will happily wipe, and nothing else in the repo would notice. So
    compare bytes and name every divergent copy. Consolidating into one shared module
    would make this check unnecessary; until then it is what keeps the copies honest.
    """
    hits: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIRS and x != ".git"]
        if os.path.basename(dirpath) != "testsafe" or "testsafe.go" not in filenames:
            continue
        fp = os.path.join(dirpath, "testsafe.go")
        try:
            with open(fp, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
        except OSError as e:
            return [f"could not read {os.path.relpath(fp, REPO_ROOT)}: {e} — "
                    "this is a READ failure, not a finding"]
        hits.append((os.path.relpath(fp, REPO_ROOT).replace("\\", "/"), digest))

    # Anti-vacuity: zero copies means the walk is wrong, not that the repo is clean.
    # A comparison over an empty set passes trivially, which is exactly the failure
    # mode this gate's own `|| true` bug had.
    if not hits:
        return ["found NO testsafe/testsafe.go anywhere — the guard package is how "
                "destructive DB tests refuse a production DSN, so an empty scan means "
                "this check is broken, not that there is nothing to check"]

    by_digest: dict[str, list[str]] = {}
    for path, digest in sorted(hits):
        by_digest.setdefault(digest, []).append(path)
    if len(by_digest) == 1:
        return []

    out = [f"the {len(hits)} vendored copies of testsafe.go have DIVERGED "
           f"({len(by_digest)} distinct versions):"]
    for digest, paths in sorted(by_digest.items(), key=lambda kv: -len(kv[1])):
        out.append(f"  [{digest[:12]}] {len(paths)} copy(ies):")
        out.extend(f"      {p}" for p in paths)
    out.append("  → diff them and re-sync. A guard that differs per service is not a guard.")
    return out


def self_test() -> int:
    """Prove this gate can go RED — on synthetic input, and on its own reach.

    `GATE-TEETH`: a gate is not proven by passing, it is proven by going red on
    a bad input. Two families here, and the second is the one that would
    otherwise never be looked at:

    * **the detectors**, each with its false-positive twin. An arm that only
      shows the finding fires proves nothing about a gate whose real cost is
      crying wolf — the `WHERE`-scoped delete must come back CLEAN from the
      same line that reds without it.
    * **the reach**. The walk covers the whole repo minus `EXCLUDE_DIRS`, so the
      only way a tree can go dark now is an exclusion that swallows it — and
      nothing about a silent walk looks different from a clean tree, so it is
      checked directly rather than inferred from a green run. It used to walk a
      hardcoded `SEARCH_DIRS`, where a renamed directory simply stopped being
      visited (`os.path.isdir` False, `continue`, clean forever): `NV-3`,
      *default-uncovered*, the shape that already shipped here twice (`"test" in
      base` missing every `*-smoke.sh`, and `lines[:60]` discarding a pragma at
      line 69). This arm named that hole; main closed it, and the arm now guards
      the closure instead of the hole.
    """
    import tempfile

    fails: list[str] = []

    def scan(name: str, body: str, kind: str = "test") -> list[str]:
        """Kinds found in a synthetic file. Paths stay OUT of the repo tree so
        the fixtures cannot be picked up by a real scan, and `_dir_is_guarded`
        short-circuits on them (they are not under `REPO_ROOT`)."""
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, name)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(body)
            fn = scan_test_file if kind == "test" else scan_config_file
            return [x.kind for x in fn(p)]

    # Counted rather than written down: the summary line below states how many
    # arms of each kind ran, and a literal there would drift from the arms the
    # moment one is added — a gate reporting a coverage number it no longer has.
    arms = {"red": 0, "clean": 0}

    def want(label: str, got: list[str], expect: list[str]) -> None:
        arms["red" if expect else "clean"] += 1
        if sorted(got) != sorted(expect):
            fails.append(f"{label}: got {got}, want {expect}")

    # ── the detectors, each with its false-positive twin ──────────────────────
    want("unscoped DELETE in a Go test",
         scan("x_test.go", '\tdb.Exec("DELETE FROM books")\n'),
         ["unscoped-DELETE-in-test"])
    want("the SAME delete, scoped by a WHERE",
         scan("x_test.go", '\tdb.Exec("DELETE FROM books WHERE owner_user_id = $1", u)\n'),
         [])
    want("TRUNCATE", scan("x_test.go", '\tdb.Exec("TRUNCATE books")\n'), ["TRUNCATE-in-test"])
    want("DROP TABLE", scan("x_test.go", '\tdb.Exec("DROP TABLE books")\n'), ["DROP-in-test"])
    want("the English word 'truncate' in a message",
         scan("x_test.go", '\tt.Log("must not truncate the name")\n'), [])

    # The pragma, and the block-walk that a fixed one-line window broke three
    # times in this repo. The reason sits FOUR lines up, where a reader wants it.
    want("inline pragma on the finding line",
         scan("x_test.go", '\tdb.Exec("TRUNCATE books")  // db-safety-gate: ok — sqlmock only\n'),
         [])
    want("pragma in the comment BLOCK above, not the line above",
         scan("x_test.go",
              "\t// This fixture owns its database outright: the DSN is a\n"
              "\t// throwaway created in TestMain and dropped after.\n"
              "\t// db-safety-gate: ok — throwaway DB created by this test\n"
              "\t// (see TestMain).\n"
              '\tdb.Exec("TRUNCATE books")\n'),
         [])
    want("file-level pragma",
         scan("x_test.go",
              "// db-safety-gate: file-ok — every statement here is a string assertion\n"
              '\tdb.Exec("DROP TABLE books")\n'),
         [])

    # SCOPE: the same statement in a file that is not a test is not this gate's
    # subject. An arm that passes for the wrong reason — because the detector
    # fires everywhere — would make the `is_test_file` split meaningless.
    if is_test_file("/tmp/handler.go"):
        fails.append("a non-test .go file was classified as a test file")
    for name, expect in (
        ("x_test.go", True), ("conftest.py", True), ("test_x.py", True),
        ("x_test.py", True), ("db-smoke.sh", True), ("restore-drill.sh", True),
        ("handler.go", False), ("main.py", False), ("deploy.sh", False),
    ):
        if is_test_file("/some/dir/" + name) is not expect:
            fails.append(f"is_test_file({name!r}) is not {expect}")

    # ── config: a *_TEST_*_URL aimed at a bare production database ────────────
    want("test URL pointing at the real DB",
         scan("ci.yml", "  BOOK_TEST_DATABASE_URL: postgres://u@h:5432/loreweave_book\n", "config"),
         ["test-URL→production-DB"])
    want("the same URL with a throwaway marker",
         scan("ci.yml", "  BOOK_TEST_DATABASE_URL: postgres://u@h:5432/loreweave_book_test\n", "config"),
         [])

    # ── main's CI-DSN rule (2026-08-09), which arrived with no arm on either side.
    # A workflow DSN must name a throwaway database whatever the variable is called;
    # the twin proves the rule does not fire outside `.github/workflows/`, where a
    # compose file legitimately names a service's real database.
    want("a workflow DSN naming a production database",
         scan(os.path.join(".github", "workflows", "ci.yml"),
              "  LW_INTEGRATION_META_DB: postgres://u@h:5432/metaworker_meta\n", "config"),
         ["CI-DSN→unmarked-DB"])
    want("the SAME DSN with a throwaway marker",
         scan(os.path.join(".github", "workflows", "ci.yml"),
              "  LW_INTEGRATION_META_DB: postgres://u@h:5432/metaworker_smoke\n", "config"),
         [])
    want("the same production DSN in a compose file is NOT this rule's business",
         scan("docker-compose.yml",
              "  LW_INTEGRATION_META_DB: postgres://u@h:5432/metaworker_meta\n", "config"),
         [])

    # ── the reach: can this gate still SEE the tree it claims to guard? ───────
    #
    # RETARGETED at the merge with main (2026-08-21). This arm used to check that
    # every entry of a hardcoded `SEARCH_DIRS` existed, because a renamed directory
    # silently stopped being walked — `NV-3`, default-uncovered. Main REMOVED that
    # tuple: `iter_files_full` now walks the whole repo minus `EXCLUDE_DIRS`, which
    # is the actual fix, so the phantom-directory question no longer has a subject.
    #
    # The question that survives the change is the mirror of it: an EXCLUDE entry
    # is now the only way a tree can go dark, so an exclusion that swallows real
    # source is the new version of the same defect.
    for d in ("services", "scripts", "infra", "sdks", "contracts", "crates", "tests"):
        if d in EXCLUDE_DIRS:
            fails.append(
                f"`{d}` is in EXCLUDE_DIRS — the walk skips it silently, which retires "
                f"this gate over that whole tree with no line of output changing.")
    if not os.path.isdir(os.path.join(REPO_ROOT, ".github")):
        fails.append("`.github` is not walked; the CI-config arm scans nothing")

    seen_test = seen_config = 0
    for path in iter_files_full():
        if not os.path.isfile(path):
            continue
        if is_test_file(path):
            seen_test += 1
        elif _is_config(path):
            seen_config += 1
    # Floors, not a ratchet. The question is "is it pointed at anything", and an
    # exact count would red on every added test — noise that trains people to
    # bump the number without reading it. Measured 2026-08-10: 1817 / 229.
    if seen_test < 500:
        fails.append(
            f"the walk found only {seen_test} test file(s) (floor 500, measured 2381 after "
            f"`.claude/worktrees/` was excluded — it had inflated this to 16549). This "
            f"gate is pointed at nothing like the tree it guards.")
    if seen_config < 50:
        fails.append(
            f"the walk found only {seen_config} config file(s) (floor 50, measured 229).")

    for f in fails:
        print(f"FAIL: {f}", file=sys.stderr)
    if fails:
        return 1
    print(f"db-safety-gate: self-test OK — {arms['red']} arm(s) go RED on a destructive shape, "
          f"{arms['clean']} stay clean on the scoped/exempt/non-test twin; walk reaches "
          f"{seen_test} test + {seen_config} config file(s).")
    return 0

def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    staged = "--staged" in sys.argv
    copy_drift = check_testsafe_copies()
    files = iter_files_staged() if staged else iter_files_full()
    findings: list[Finding] = []
    for path in files:
        if not os.path.isfile(path):
            continue
        if is_test_file(path):
            findings.extend(scan_test_file(path))
        elif _is_config(path):
            findings.extend(scan_config_file(path))

    if copy_drift:
        print("✗ db-safety-gate: the runtime guard is not the same everywhere:\n", file=sys.stderr)
        for ln in copy_drift:
            print(ln, file=sys.stderr)
        print("", file=sys.stderr)

    if not findings:
        return 1 if copy_drift else 0

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
