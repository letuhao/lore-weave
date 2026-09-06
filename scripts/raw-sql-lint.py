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

Usage:
  python scripts/raw-sql-lint.py              # self-test, then full scan
  python scripts/raw-sql-lint.py --self-test  # the proof alone
  python scripts/raw-sql-lint.py --staged     # only git-staged files (pre-commit)
  python scripts/raw-sql-lint.py --help

Exit 0 = clean (or baseline-only). 1 = a NEW value-interpolation violation, a
dead exemption, or a scope row that reaches nothing. 2 = self-test failure /
nothing scanned.

GT5 · what this gate lacked
---------------------------
No REACH FLOOR (`GT-F3`): every `SEARCH_DIRS` entry that does not exist is
skipped silently, so a renamed tree produced zero files, zero hits and the same
`OK` line — byte-identical to a clean scan (`BDR-82`).

`crates` was one of those entries and it reached **zero files**: `SCAN_EXTS` is
`.py`/`.go` and `crates/` is Rust. Decorative scope. Removed, and the Rust SQL
surface it implied is recorded as an open row rather than papered over — see
`GT-RAWSQL-RUST-UNSCANNED`. A per-directory arm now reds on any scope row that
contributes nothing, so this cannot come back quietly.

`BASELINE` had no SHRINK ARM (`GT-F5`), and **2 of its 6 rows were dead** — both
named `services/knowledge-service/scripts/_smoke_a2s1b2*.py`, files that no
longer exist. A row whose subject is gone exempts nothing today and silently
re-exempts the day the name returns, which for THIS gate means waving through a
real injection. Trimmed to 4, both deaths now red.
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

#: Scope. Every entry must contribute at least one scanned file — see the
#: per-directory arm in `check()`. `crates` was removed: it is Rust, and
#: `SCAN_EXTS` cannot see it.
SEARCH_DIRS = ("services", "sdks")
SCAN_EXTS = (".py", ".go")
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", ".next", ".git", "vendor", "coverage",
    "storybook-static", "target",
}

# Path prefixes (forward-slash, relative to repo root) where the rule does not
# apply. Keep tight; comment every entry. Empty today — and the shrink arm in
# `check()` is what keeps a future entry from outliving its reason.
ALLOWLIST_PREFIXES: tuple[str, ...] = (
    # (none yet — the audit found all live SQL parameterized)
)

# ── BASELINE ──────────────────────────────────────────────────────────────
# Known-current offenders, as "relpath::snippet-substring". The lint passes when
# every flagged site is in the baseline; a NEW site (not listed) fails the run.
#
# D-QC-GATES-BUILT-BUT-NOT-WIRED (2026-07-31): this lint had never run in CI. Its first
# execution reported six sites; each was read before being listed, and all were the
# exception the module docstring already sanctions ("only allowlisted identifiers may be
# interpolated"):
#
#   · package_rekey.py ×4 — a marker-gated MIGRATION. What it interpolates is TABLE and
#     COLUMN identifiers, which SQL cannot bind as placeholders at all, drawn from
#     module-level constant lists (_USER_ID_RENAMES, _OWNER_USER_ID_RENAMES,
#     _BOOK_ID_TABLES, _ORPHAN_TABLES, _BATCH_TABLES, _SMALL_PROJECT_TABLES) — closed sets
#     in the file, never user input. `{marker}` is the module's own `pkg_rekey_v1` constant.
#     The builders are private with no caller outside the module, and they emit `DO $$ … $$`
#     blocks, which in Postgres CANNOT take bind parameters at all — so `$1` is not an
#     available alternative even where the position is a value rather than an identifier.
#
#     THE EXEMPTION IS GUARDED, not asserted: the reasoning rests entirely on those names
#     staying literal, and a baseline row that outlived that fact would silently bless a
#     real injection (non-vacuity NV-4 — an adjacent decision defeating the check).
#     `services/composition-service/tests/unit/test_package_rekey_constants.py` parses the
#     module with `ast` and reds if any of them stops being a module-level tuple of string
#     literals. Verified present and still asserting 2026-08-12.
#
#   · two knowledge `_smoke_*` dev scripts — REMOVED 2026-08-12. Both files are gone from
#     the tree, so both rows had become dead exemptions: nothing to excuse today, and a
#     standing waiver for those paths the day anything reappeared under them. Found by the
#     shrink arm this gate previously lacked.
#
# Listed WITH the verification rather than left red. A genuinely user-derived value
# interpolated into SQL still fails, which is the whole point.
BASELINE: frozenset[str] = frozenset({
    "services/composition-service/app/db/package_rekey.py::DELETE FROM package_migration WHERE marker = '{marker}';",
    "services/composition-service/app/db/package_rekey.py::WHERE table_name = '{table}' AND column_name = 'created_by'",
    "services/composition-service/app/db/package_rekey.py::WHERE table_name = '{t}' AND column_name = 'book_id'",
    "services/composition-service/app/db/package_rekey.py::WHERE table_name = '{table}' AND column_name = '{old}'",

    # ── T48n (2026-08-30): the AGE sites, each READ before being listed ────────────────
    #
    # §14 filed the whole sweep's raw-sql-lint red as "other work — none names a file this
    # plan touched." **That attribution was wrong**: five of these six files are this plan's
    # own. Re-attributed and discharged here rather than inherited, which is what T48's
    # "nothing silently dropped" is supposed to mean.
    #
    # Every one interpolates an IDENTIFIER, which SQL cannot bind as a placeholder at all —
    # the exception this module's docstring already sanctions. Read individually:
    #
    #   · age_graph_store.py ×4, age_session.py, age_anchor_scores.py —
    #     `cypher('<graph>', $tag$…$tag$)`. AGE takes the graph name as a LITERAL in the
    #     function call; it is not bindable. The value comes from `graph_name_for()`, which
    #     returns `g_shared` or `g_` + the project UUID's hex and RAISES on anything failing
    #     `_VALID_GRAPH_NAME` — so the slot cannot carry user text: an illegal name is an
    #     exception, never a query. The Cypher body is dollar-quoted with a tag
    #     `_dollar_tag()` chooses to avoid any sequence occurring inside the body.
    #   · age_bootstrap.py — `create_graph('<name>')`, the same validated name, and DDL
    #     takes no binds.
    #   · vector_backend_bench.py — `pg_total_relation_size('<table>')` over the benchmark's
    #     OWN module-level table list. No request reaches it.
    "services/knowledge-service/app/adapters/age_anchor_scores.py::f\"SELECT * FROM cypher('{graph}', $anchor${cypher}$anchor$) \"",
    "services/knowledge-service/app/adapters/age_graph_store.py::sql = f\"SELECT * FROM cypher('{self._graph}', ${tag}${cypher}${tag}$) as ({columns})\"",
    "services/knowledge-service/app/adapters/age_graph_store.py::return f\"SELECT * FROM cypher('{self._graph}', ${tag}${cy}${tag}$) as ({cols})\"",
    "services/knowledge-service/app/benchmark/vector_backend_bench.py::f\"SELECT pg_total_relation_size('{cell.table}')\"",
    "services/knowledge-service/app/db/age_bootstrap.py::await conn.execute(f\"SELECT ag_catalog.create_graph('{name}')\")",
    "services/knowledge-service/app/db/age_session.py::f\"SELECT * FROM cypher('{self._graph}', $q${cypher}$q$, $1) \"",
})

# ── detection ─────────────────────────────────────────────────────────────

# A SQL DML keyword present on the line — the "this is really SQL" gate.
# CASE-SENSITIVE UPPERCASE by design: this repo writes SQL keywords in
# uppercase, and a case-insensitive match collides massively with ordinary
# lowercase identifiers (`.values()`, `where.append`, `params={"limit":…}`,
# `model_copy(update={…})`). Requiring uppercase keeps false positives near
# zero. Tradeoff: a value-injection written with lowercase SQL keywords would
# be missed — acceptable, and now pinned by a self-test case so the tradeoff is
# a decision on the record rather than something a later edit changes silently.
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


def is_allowlisted(rel: str, prefixes: tuple[str, ...] = ALLOWLIST_PREFIXES) -> bool:
    return (bool(prefixes) and rel.startswith(prefixes)) or is_test_file(rel)


def baseline_key(rel: str, line: str) -> str:
    return f"{rel}::{line.strip()}"


def matching_baseline(rel: str, line: str, baseline=BASELINE) -> str | None:
    key = baseline_key(rel, line)
    for b in baseline:
        if key.startswith(b) or b in key:
            return b
    return None


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
                    rel = os.path.relpath(full, repo_root).replace(os.sep, "/")
                    yield full, rel


def iter_staged(repo_root: str = REPO_ROOT, search_dirs=SEARCH_DIRS):
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=repo_root, capture_output=True, text=True, check=True,
            timeout=GIT_TIMEOUT_S,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return
    for rel in res.stdout.splitlines():
        rel = rel.strip().replace(os.sep, "/")
        if not rel.endswith(SCAN_EXTS):
            continue
        if not rel.startswith(tuple(d + "/" for d in search_dirs)):
            continue
        if any(part in EXCLUDE_DIRS for part in rel.split("/")):
            continue
        full = os.path.join(repo_root, rel)
        if os.path.isfile(full):
            yield full, rel


def check(
    repo_root: str = REPO_ROOT,
    search_dirs=SEARCH_DIRS,
    baseline=BASELINE,
    prefixes: tuple[str, ...] = ALLOWLIST_PREFIXES,
    staged: bool = False,
) -> int:
    """The REAL checker, parameterised so `--self-test` can drive it over a
    synthetic tree instead of re-implementing its rules."""
    files = list(iter_staged(repo_root, search_dirs) if staged
                 else iter_full_scan(repo_root, search_dirs))

    per_dir: dict[str, int] = {d: 0 for d in search_dirs}
    for _full, rel in files:
        top = rel.split("/", 1)[0]
        if top in per_dir:
            per_dir[top] += 1

    mode = "staged" if staged else "full"

    # ── REACH FLOOR (GT-F3). Only meaningful on a full scan: a staged run over a
    # commit that touches no scanned file legitimately sees zero.
    if not staged and not files:
        print(f"raw-sql-lint: ERROR — scanned 0 file(s) across {list(search_dirs)}. "
              f"A walk that reached nothing is byte-identical to a clean tree, exit "
              f"code included (BDR-82).", file=sys.stderr)
        return 2

    problems: list[str] = []

    # ── SCOPE ARM. A SEARCH_DIRS entry that contributes no file is either
    # renamed or wrong-language, and either way it advertises coverage it does
    # not provide — `crates` sat in this list scanning nothing at all.
    if not staged:
        for d, n in sorted(per_dir.items()):
            if n == 0:
                problems.append(
                    f"SEARCH_DIRS entry {d!r} contributed 0 scanned file(s). It is "
                    f"renamed, empty, or holds no {'/'.join(SCAN_EXTS)} — remove it or "
                    f"fix it, but do not let it claim coverage.")

    new_violations: list[tuple[str, int, str, list[str]]] = []
    baselined = 0
    used_baseline: set[str] = set()
    for full, rel in files:
        if is_allowlisted(rel, prefixes):
            continue
        for n, line, hits in scan_file(full, rel):
            hit_row = matching_baseline(rel, line, baseline)
            if hit_row is not None:
                baselined += 1
                used_baseline.add(hit_row)
                continue
            new_violations.append((rel, n, line, hits))

    # ── SHRINK ARM (GT-F5) on BASELINE. A row matching no site exempts nothing
    # today and re-exempts its path the day anything reappears there — for THIS
    # gate that means waving through a real injection.
    if not staged:
        for row in sorted(set(baseline) - used_baseline):
            problems.append(
                f"BASELINE row matches no site in this tree: {row[:120]} — delete it, "
                f"or it becomes a standing waiver for that path.")

        # ── SHRINK ARM on ALLOWLIST_PREFIXES, same two deaths.
        for pref in prefixes:
            if not any(rel.startswith(pref) for _f, rel in files):
                problems.append(
                    f"ALLOWLIST_PREFIXES entry {pref!r} matches no scanned file — it "
                    f"exempts nothing and would exempt everything under that path the "
                    f"day it exists.")

    if not new_violations and not problems:
        extra = f" ({baselined} baselined)" if baselined else ""
        scope = ", ".join(f"{d}={n}" for d, n in sorted(per_dir.items()))
        print(f"raw-sql-lint ({mode}): OK — no unparameterized SQL value "
              f"interpolation{extra}. {len(files)} file(s) scanned [{scope}].")
        return 0

    if new_violations:
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
    for p in problems:
        print(f"raw-sql-lint: FAIL — {p}")
    return 1


# ── SELF-TEST ────────────────────────────────────────────────────────────────
CLEAN_PY = 'q = "SELECT id FROM books WHERE owner_user_id = $1"\n'
CLEAN_GO = 'const q = `SELECT id FROM books WHERE owner_user_id = $1`\n'


def self_test() -> int:
    """Every rule against input that violates it AND input that must not trip it,
    driving the REAL `check()` over a synthetic tree."""
    import contextlib
    import io
    import tempfile

    failures = 0

    def probe(name: str, want: int, files: dict[str, str], *,
              search_dirs=("services", "sdks"), baseline=frozenset(),
              prefixes: tuple[str, ...] = (), seed=True) -> None:
        nonlocal failures
        with tempfile.TemporaryDirectory() as d:
            if seed:
                # every probe tree carries one clean file in EACH search dir, so
                # the reach floor and the per-directory arm stay quiet and the
                # probe tests exactly one rule
                files = {"services/svc/clean.py": CLEAN_PY,
                         "sdks/py/clean.py": CLEAN_PY, **files}
            for rel, body in files.items():
                full = os.path.join(d, *rel.split("/"))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(body)
            try:
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    got = check(d, search_dirs, baseline, prefixes)
            except Exception as e:  # noqa: BLE001 - a crash is what this asserts against
                failures += 1
                print(f"  FAIL {name}: raised {type(e).__name__}: {e} — it must return a code")
                return
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: rc={got} (want {want})")

    print("raw-sql-lint --self-test")

    probe("a parameterized tree passes", 0, {})

    # the three detectors
    probe("a quoted f-string brace in python fails", 1, {
        "services/svc/bad.py": "q = f\"SELECT * FROM t WHERE name = '{name}'\"\n"})
    probe("a quoted %-verb fails", 1, {
        "services/svc/bad.py": "q = \"SELECT * FROM t WHERE name = '%s'\" % name\n"})
    probe("a quoted %-verb in Go fails too", 1, {
        "services/svc/bad.go": "q := fmt.Sprintf(\"SELECT * FROM t WHERE name = '%s'\", name)\n"})
    probe("concatenation into a quoted SQL literal fails", 1, {
        "services/svc/bad.go": "q := \"SELECT * FROM t WHERE name = '\" + name + \"'\"\n"})

    # …and the shapes that must NOT cry wolf
    probe("...but a bare $1 placeholder does not", 0, {
        "services/svc/ok.py": CLEAN_PY})
    probe("...nor a bare %s bind placeholder", 0, {
        "services/svc/ok.py": 'q = "SELECT id FROM t WHERE owner = %s"\n'})
    probe("...nor identifier interpolation in a table position", 0, {
        "services/svc/ok.py": 'q = f"SELECT id FROM {table} WHERE owner = $1"\n'})
    probe("...nor a LIKE pattern with literal percents", 0, {
        "services/svc/ok.py": "q = \"SELECT id FROM t WHERE name LIKE '%foo%'\"\n"})
    probe("...nor a Go Postgres array literal '{a,b}'", 0, {
        "services/svc/ok.go": "q := \"SELECT id FROM t WHERE tags = '{a,b}'::text[]\"\n"})
    probe("...nor a line with no SQL keyword at all", 0, {
        "services/svc/ok.py": "msg = f\"greeting = '{name}'\"\n"})
    # A DECISION on the record, not an accident: uppercase-only keyword matching
    # is the false-positive tradeoff the module docstring names. A case pins it.
    probe("...nor lowercase SQL keywords (the documented tradeoff)", 0, {
        "services/svc/ok.py": "q = f\"select * from t where name = '{name}'\"\n"})

    # exclusions
    probe("an offender in a test file is excluded", 0, {
        "services/svc/tests/t.py": "q = f\"SELECT * FROM t WHERE n = '{n}'\"\n"})
    probe("an offender under an ALLOWLIST prefix is excluded", 0, {
        "services/legacy/bad.py": "q = f\"SELECT * FROM t WHERE n = '{n}'\"\n"},
        prefixes=("services/legacy",))
    probe("a BASELINED offender passes", 0, {
        "services/svc/bad.py": "q = f\"SELECT * FROM t WHERE n = '{n}'\"\n"},
        baseline=frozenset({"services/svc/bad.py::q = f\"SELECT * FROM t WHERE n = '{n}'\""}))

    # the shrink arms — a row dies when its subject disappears
    probe("a BASELINE row matching no site fails", 1, {},
          baseline=frozenset({"services/svc/vanished.py::SELECT"}))
    probe("an ALLOWLIST prefix matching no file fails", 1, {},
          prefixes=("services/ghost",))

    # scope + reach
    probe("a SEARCH_DIRS entry that scans nothing fails", 1, {},
          search_dirs=("services", "sdks", "crates"))
    probe("no files anywhere is misuse, not a pass", 2, {}, seed=False)

    # ── the MECHANISM for GT-RAWSQL-RUST-UNSCANNED ───────────────────────────
    # An ASSERTED TRIGGER, not a comment. The open row says Rust is unscanned:
    # 63 `.rs` files under `crates/` and `services/` contain SQL keywords and
    # `SCAN_EXTS` cannot see any of them. A `# TODO(GT-RAWSQL-...)` beside the
    # tuple would be prose that happens to live in a source file, which this
    # repo has ruled is NOT a mechanism -- it certified three prose-only
    # deferrals before the stripper was fixed.
    #
    # So the case reds when the SUBJECT ARRIVES. Add `.rs` and this fails,
    # pointing at the row that must now be deleted. A deferral that cannot
    # notice its own discharge is how one gets cited as an open blocker in four
    # places after it was fixed.
    if ".rs" in SCAN_EXTS:
        failures += 1
        print("  FAIL GT-RAWSQL-RUST-UNSCANNED is DISCHARGED: SCAN_EXTS now covers .rs.\n"
              "       Delete this case and the row in the gate-teeth run-state, and give the\n"
              "       Rust leg its own detector cases -- the two live signals do not transfer\n"
              "       (a `{x}` inside a Rust SQL literal is ambiguous between a format!\n"
              "       interpolation and a Postgres array literal).")
    else:
        print("  ok   GT-RAWSQL-RUST-UNSCANNED still open: SCAN_EXTS is "
              f"{SCAN_EXTS} — the row has a trigger, not a promise")

    if failures:
        print(f"raw-sql-lint --self-test: {failures} rule(s) did not behave")
        return 2
    print("raw-sql-lint --self-test: every rule bites, and none cries wolf")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0
    if "--self-test" in args or "--selftest" in args:
        return self_test()
    rc = self_test()
    if rc:
        return rc
    print()
    return check(staged="--staged" in args)


if __name__ == "__main__":
    sys.exit(main())
