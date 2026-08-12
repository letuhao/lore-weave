#!/usr/bin/env python3
"""pagination-cap-lint.py — enforce PERF-3 (bounded results by construction).

Standard: docs/standards/performance.md › Rules › **PERF-3 · Bounded results
by construction.** Every list/search endpoint paginates with an *enforced max
cap*; an unbounded `SELECT` without a clamped `LIMIT` on a user-facing path is
a defect. (This is what the reactive `parseLimitOffset` clamp + `limit le=100`
fixes were patching one-by-one.)

What it flags
-------------
1. **FastAPI list routes** — a `limit` query parameter declared with
   `Query(...)` whose argument list has NO `le=` upper bound. FastAPI's `le=`
   is the enforced cap; without it the client can request an unbounded page.
   Multiline `Query(\n  ...\n)` blocks are handled (balanced-paren capture).

2. **Go list handlers** — a `.go` file that builds a *parameterized* list SQL
   (`LIMIT $N` / `LIMIT %d` / `LIMIT %s`) but references NO clamp helper
   (`clampLimit` / `parseLimitOffset`). The two helpers are this repo's
   established 1..100 / 1..MAX clamps; a list query that routes through
   neither is the smell that produced the chapter-list-limit100 bug.
   (A fixed `LIMIT 100` literal is bounded by construction and NOT flagged.)

Baseline / allowlist
--------------------
Mirrors `scripts/ai-provider-gate.py`: the lint passes clean (exit 0) on the
CURRENT tree by carrying a BASELINE of today's known offenders (fingerprinted
line-number-free so the baseline survives edits elsewhere in the file). It
flags only NEW violations. Test/script/eval files are excluded (not
user-facing runtime routes).

Refresh the baseline after intentionally fixing/adding offenders:
    python scripts/pagination-cap-lint.py --regen   # prints current fingerprints

Usage
-----
    python scripts/pagination-cap-lint.py            # full scan (CI / manual)
    python scripts/pagination-cap-lint.py --regen    # print current fingerprints
    python scripts/pagination-cap-lint.py --help

Exit 0 = clean (or baseline-only). Exit 1 = NEW violation. Exit 2 = usage.
"""
from __future__ import annotations

import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICES = os.path.join(REPO_ROOT, "services")

EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", ".next", ".git", "vendor", "coverage",
}

# ── detection patterns ────────────────────────────────────────────────

# FastAPI: a `limit` param defaulting to Query(...). We then balance-capture
# the full Query(...) call (possibly multiline) and require an `le=` bound.
FASTAPI_LIMIT = re.compile(r"\blimit\s*:\s*[^=\n]*=\s*Query\s*\(")
LE_BOUND = re.compile(r"\ble\s*=")

# Go: parameterized list LIMIT (positional `$N` or format `%d`/`%s`). A fixed
# integer literal (`LIMIT 100`) is bounded by construction and NOT matched.
GO_PARAM_LIMIT = re.compile(r"LIMIT\s+(?:\$\d+|\$`|%d|%s)", re.IGNORECASE)
GO_CLAMP_SIGNALS = ("clampLimit", "parseLimitOffset")


def is_excluded(rel: str) -> bool:
    """Test / script / eval / fixture files — not user-facing runtime routes."""
    base = os.path.basename(rel)
    return (
        "/tests/" in rel
        or "/test/" in rel
        or "/scripts/" in rel
        or "/eval/" in rel
        or "/benchmark/" in rel
        or "/__mocks__/" in rel
        or "/fixtures/" in rel
        or "/poc" in rel
        or base.startswith(("test_", "live_", "smoke_", "poc_", "conftest"))
        or base.endswith("_test.go")
    )


def _strip(line: str) -> str:
    return line.strip()


def _balance_from(text: str, open_paren_idx: int) -> str:
    """Return the substring from `open_paren_idx` (an index pointing AT the
    '(') through its matching ')'. Naive paren counting — good enough for the
    call sites here (no unbalanced parens inside string literals in practice)."""
    depth = 0
    for i in range(open_paren_idx, len(text)):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren_idx:i + 1]
    return text[open_paren_idx:]  # unterminated — return the tail


def scan_python(path: str, rel: str) -> list[tuple[str, int, str]]:
    """Return (rel, lineno, snippet) FastAPI limit-without-le violations."""
    out: list[tuple[str, int, str]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    except OSError:
        return out
    for m in FASTAPI_LIMIT.finditer(text):
        # m.end()-1 points at the '(' of Query(
        call = _balance_from(text, m.end() - 1)
        if LE_BOUND.search(call):
            continue
        lineno = text.count("\n", 0, m.start()) + 1
        snippet = _strip(text[m.start():text.find("\n", m.start())
                              if text.find("\n", m.start()) != -1 else len(text)])
        out.append((rel, lineno, snippet))
    return out


def scan_go(path: str, rel: str) -> list[tuple[str, int, str]]:
    """Return (rel, lineno, snippet) parameterized-LIMIT-without-clamp
    violations. File-level clamp-helper presence is the pass signal.

    Scope: the HTTP handler layer only (`internal/api/`). Internal batch
    queries in sweepers/outbox-relays/migrations use a fixed server-set
    batch size (not a client page), so they are out of PERF-3's scope."""
    out: list[tuple[str, int, str]] = []
    if "/internal/api/" not in rel:
        return out
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except OSError:
        return out
    full = "".join(lines)
    if any(sig in full for sig in GO_CLAMP_SIGNALS):
        return out  # file routes limits through a known clamp helper → OK
    for n, line in enumerate(lines, 1):
        if GO_PARAM_LIMIT.search(line):
            out.append((rel, n, _strip(line)))
    return out


def iter_files(services_root: str = SERVICES, repo_root: str = REPO_ROOT):
    if not os.path.isdir(services_root):
        return
    for dirpath, dirnames, filenames in os.walk(services_root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if not (fn.endswith(".py") or fn.endswith(".go")):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, repo_root).replace(os.sep, "/")
            if is_excluded(rel):
                continue
            yield full, rel


def collect(services_root: str = SERVICES, repo_root: str = REPO_ROOT):
    """Returns (hits, reach) where reach counts what each LEG actually looked at.

    A count of files is not enough here: this gate has two legs with different
    subjects, and either can go quiet on its own. The FastAPI leg needs `limit=
    Query(...)` declarations to exist; the Go leg needs `.go` files under
    `internal/api/`. Measured 2026-08-12: 51 FastAPI declarations, 223 handler
    files of which 47 carry a parameterized LIMIT."""
    hits: list[tuple[str, int, str]] = []
    reach = {"py_files": 0, "go_api_files": 0, "fastapi_limit_decls": 0}
    for full, rel in iter_files(services_root, repo_root):
        if rel.endswith(".py"):
            reach["py_files"] += 1
            try:
                with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                    reach["fastapi_limit_decls"] += len(FASTAPI_LIMIT.findall(fh.read()))
            except OSError:
                pass
            hits.extend(scan_python(full, rel))
        else:
            if "/internal/api/" in rel:
                reach["go_api_files"] += 1
            hits.extend(scan_go(full, rel))
    return hits, reach


def fingerprint(hit: tuple[str, int, str]) -> str:
    """Line-number-free fingerprint: `rel::snippet`. Survives edits elsewhere
    in the file so the baseline doesn't churn on unrelated line shifts."""
    rel, _lineno, snippet = hit
    return f"{rel}::{snippet}"


# ── BASELINE — known PERF-3 offenders. Regenerate with `--regen`. Each entry is
# `rel::snippet`, line-number-free so it survives edits elsewhere in the file.
#
# Verified 2026-07-29/31 (D-QC-GATES-BUILT-BUT-NOT-WIRED). This lint had never run in
# CI; its first executions reported these and each was read before being listed. The
# recurring shape is LINT PRECISION, not debt: the regex sees `LIMIT $N` with a
# variable and cannot see a clamp three to forty lines earlier.
#
#   · dek_shred_sweeper / reparse_sweeper — NOT ROUTES. `batchSize` is a parameter of
#     `RunDekShredSweeper(ctx, interval, batchSize)`, a background sweeper started at
#     boot with an operator-set batch. No client can reach it, which is outside this
#     lint's own stated subject ("every list/search ENDPOINT").
#   · entities_by_ids_handler — `if limit > 500 { limit = 500 }`.
#   · entity_handler — clamped INLINE and completely: `queryInt(q.Get("limit"), 200)`,
#     then `<1 → 1`, `>500 → 500`. glossary-service has no `clampLimit` to route
#     through; introducing one for a single call site is a different change.
#   · the rest — Go handler-layer list queries. Many use a server-set cap
#     (batchSize/pipelineReadCap/*ListCap) and are safe; a few (sharing
#     listPublicInternal, statistics, usage-billing) are genuinely unclamped client
#     limits — tracked debt, not fixed by this lint.
#
# GT5 · TWO ROWS WERE DEAD and a shrink arm now says so. `mcp_worlds.go` was
# **fixed** in the 2026-07-29 pass — its inline clamp disagreed with the helper beside
# it — and the comment block below the rows said so in as many words ("the fourth
# finding was NOT baselined — mcp_worlds.go was fixed"), while the row itself stayed in
# the set. The file documented the removal of a row it still carried, for two weeks,
# and nothing could notice. `pipeline_read_tools.go::LIMIT $2`, bookID,
# pipelineReadCap)` had likewise stopped matching. Both removed.
#
# Three rows were also written TWICE (dek_shred_sweeper, reparse_sweeper,
# entity_handler), under two comment blocks giving different accounts of the same
# finding. `frozenset` deduplicated them silently, so 39 literal rows were 36. Now 34,
# each exactly once.
BASELINE: frozenset[str] = frozenset({
    "services/auth-service/internal/api/handlers.go::ORDER BY f.created_at DESC LIMIT $2 OFFSET $3`, userID, limit, offset)",
    "services/auth-service/internal/api/mcp_audit.go::LIMIT $3 OFFSET $4`, uid, keyID, limit, offset)",
    "services/book-service/internal/api/dek_shred_sweeper.go::ORDER BY last_attempt_at ASC NULLS FIRST, requested_at ASC LIMIT $1`, batchSize)",
    "services/book-service/internal/api/favorites.go::ORDER BY f.created_at DESC LIMIT $2 OFFSET $3`, userID, limit, offset)",
    "services/book-service/internal/api/import.go::ORDER BY ts ASC LIMIT $2",
    "services/book-service/internal/api/reparse_sweeper.go::LIMIT $1`, batchSize)",
    "services/glossary-service/internal/api/canonical_summary_handler.go::LIMIT $2`, bookID, limit)",
    "services/glossary-service/internal/api/enrichment_handler.go::LIMIT $2`, bookID, limit)",
    "services/glossary-service/internal/api/entities_by_ids_handler.go::LIMIT $2 OFFSET $3`, bookID, limit+1, offset)",
    "services/glossary-service/internal/api/entity_handler.go::LIMIT $3`, bookID, afterArg, limit+1)",
    "services/glossary-service/internal/api/evidence_handler.go::LIMIT $2`, entityID, limit)",
    "services/glossary-service/internal/api/extraction_handler.go::LIMIT $3",
    "services/glossary-service/internal/api/facts_handler.go::LIMIT $`+strconv.Itoa(len(args)), args...)",
    "services/glossary-service/internal/api/fold_handler.go::LIMIT $2",
    "services/glossary-service/internal/api/glossary_translate_handler.go::entitySQL += ` ORDER BY e.entity_id LIMIT $` + strconv.Itoa(limitArg) +",
    "services/glossary-service/internal/api/knowledge_client.go::fmt.Sprintf(`SELECT ge.entity_id::text `+base+` ORDER BY ge.created_at LIMIT %d`, limit),",
    "services/glossary-service/internal/api/merge_candidates_handler.go::q += ` LIMIT $3`",
    "services/glossary-service/internal/api/pipeline_read_tools.go::ORDER BY revision_num DESC LIMIT $2`, entityID, entityRevisionsListCap)",
    "services/glossary-service/internal/api/plan_ops.go::q += ` LIMIT $2`",
    "services/glossary-service/internal/api/recycle_bin_handler.go::LIMIT $2 OFFSET $3`,",
    "services/glossary-service/internal/api/select_for_context_handler.go::LIMIT $3`, selectCols)",
    "services/glossary-service/internal/api/select_for_context_handler.go::LIMIT $4`, selectCols)",
    "services/glossary-service/internal/api/server.go::LIMIT $3`",
    "services/glossary-service/internal/api/server.go::LIMIT $4",
    "services/glossary-service/internal/api/server.go::LIMIT $4`",
    "services/glossary-service/internal/api/user_genre_handler.go::LIMIT $2 OFFSET $3`, orderClause), userID, limit, offset)",
    "services/glossary-service/internal/api/user_genre_handler.go::LIMIT $2 OFFSET $3`, userID, limit, offset)",
    "services/glossary-service/internal/api/user_kind_handler.go::LIMIT $2 OFFSET $3`, userID, limit, offset)",
    "services/glossary-service/internal/api/wiki_contributions_handler.go::LIMIT $2 OFFSET $3`, targetUser, limit, offset)",
    "services/glossary-service/internal/api/wiki_gold_pairs.go::LIMIT $2`,",
    "services/glossary-service/internal/api/wiki_handler.go::LIMIT $2 OFFSET $3`, articleID, limit, offset)",
    "services/sharing-service/internal/api/server.go::rows, err := s.pool.Query(r.Context(), `SELECT book_id FROM sharing_policies WHERE visibility='public' ORDER BY updated_at DESC LIMIT $1 OFFSET $2`, limit, offset)",
    "services/statistics-service/internal/api/server.go::ORDER BY %s DESC LIMIT $1 OFFSET $2",
    "services/usage-billing-service/internal/api/server.go::LIMIT $1 OFFSET $2",
})


def check(services_root: str = SERVICES, repo_root: str = REPO_ROOT,
          baseline=BASELINE) -> int:
    """The REAL checker, parameterised so `--self-test` can drive it over a
    synthetic tree instead of re-implementing its rules."""
    hits, reach = collect(services_root, repo_root)

    # ── REACH FLOORS (GT-F3), one per LEG. Two legs with different subjects;
    # either can go silent alone, and a silent leg is byte-identical to a
    # compliant one, exit code included (BDR-82).
    # There is deliberately NO `py_files == 0` clause. It would be strictly
    # shadowed by the declaration floor below — zero python files implies zero
    # `limit=Query` declarations — and a rule that cannot produce a finding
    # another does not is deletable with the suite green (`GTD-7`). The bite
    # found it: the arm disabling this floor still went red, on the sibling.
    if reach["go_api_files"] == 0:
        print(f"pagination-cap-lint: ERROR — the Go leg looked at NOTHING: "
              f"0 handler file(s) under internal/api/ (python side saw "
              f"{reach['py_files']} file(s)). A moved tree, not a clean one.",
              file=sys.stderr)
        return 2
    if reach["fastapi_limit_decls"] == 0:
        print("pagination-cap-lint: ERROR — 0 `limit=Query(...)` declarations found. "
              "The FastAPI leg has no subject, so its silence proves nothing; if the "
              "convention genuinely changed, retire the leg rather than let it pass.",
              file=sys.stderr)
        return 2

    problems: list[str] = []

    # ── SHRINK ARM (GT-F5). A baseline row matching no hit exempts nothing today
    # and re-exempts its route the day the line comes back. `mcp_worlds.go` sat
    # here for two weeks after being FIXED, with a comment three lines below
    # saying it had been removed.
    live = {fingerprint(h) for h in hits}
    for row in sorted(set(baseline) - live):
        problems.append(
            f"BASELINE row matches no route in this tree: {row[:110]} — it was fixed "
            f"or moved. Delete it (--regen reprints the live set).")

    new = [h for h in hits if fingerprint(h) not in baseline]
    baselined = len(hits) - len(new)

    if not new and not problems:
        print(f"pagination-cap-lint: OK — every list route has a clamped cap (PERF-3). "
              f"{baselined} baselined offender(s) tracked; scanned "
              f"{reach['py_files']} python file(s) ({reach['fastapi_limit_decls']} "
              f"limit=Query decl(s)) and {reach['go_api_files']} Go handler file(s).")
        return 0

    if new:
        print("pagination-cap-lint: FAIL — NEW unbounded list route(s) (PERF-3)\n")
        print("  Every list/search endpoint MUST cap its page size:")
        print("    • FastAPI: give the `limit` Query param an `le=<MAX>` bound.")
        print("    • Go: route the limit through clampLimit()/parseLimitOffset().")
        print("  A fixed `LIMIT 100` literal is fine; an unclamped client-supplied")
        print("  limit is the defect.\n")
        for rel, lineno, snippet in sorted(new):
            print(f"  {rel}:{lineno}: {snippet}")
        print("\nIf this is tracked debt, add a DEFERRED row and refresh the")
        print("baseline: python scripts/pagination-cap-lint.py --regen")
    for p in problems:
        print(f"pagination-cap-lint: FAIL — {p}")
    return 1


# ── SELF-TEST ────────────────────────────────────────────────────────────────
# Every seeded tree carries one clean file per LEG, so the three reach floors
# stay quiet and each probe below tests exactly one rule.
CLEAN_PY = ('from fastapi import Query\n\n\n'
            'def list_things(limit: int = Query(20, le=100)):\n    return []\n')
CLEAN_GO = 'package api\n\nfunc h() { _ = "SELECT id FROM t LIMIT 100" }\n'


def self_test() -> int:
    import contextlib
    import io
    import tempfile

    failures = 0

    def probe(name: str, want: int, files: dict[str, str], *,
              baseline=frozenset(), seed=True) -> None:
        nonlocal failures
        with tempfile.TemporaryDirectory() as d:
            services = os.path.join(d, "services")
            os.makedirs(services, exist_ok=True)
            if seed:
                files = {"svc/app/routes.py": CLEAN_PY,
                         "svc/internal/api/clean.go": CLEAN_GO, **files}
            for rel, body in files.items():
                full = os.path.join(services, *rel.split("/"))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(body)
            try:
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    got = check(services, d, baseline)
            except Exception as e:  # noqa: BLE001 - a crash is what this asserts against
                failures += 1
                print(f"  FAIL {name}: raised {type(e).__name__}: {e} — it must return a code")
                return
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: rc={got} (want {want})")

    print("pagination-cap-lint --self-test")

    probe("a capped tree passes", 0, {})

    # leg 1 — FastAPI
    probe("a limit Query without le= fails", 1, {
        "svc/app/bad.py": "def f(limit: int = Query(20)):\n    return []\n"})
    probe("...but one WITH le= does not", 0, {
        "svc/app/ok.py": "def f(limit: int = Query(20, le=100)):\n    return []\n"})
    probe("a MULTILINE Query without le= fails", 1, {
        "svc/app/bad.py": "def f(\n    limit: int = Query(\n        20,\n"
                          "        ge=1,\n    ),\n):\n    return []\n"})
    probe("...but a multiline Query with le= on a later line does not", 0, {
        "svc/app/ok.py": "def f(\n    limit: int = Query(\n        20,\n"
                         "        le=100,\n    ),\n):\n    return []\n"})

    # leg 2 — Go
    probe("a parameterized LIMIT with no clamp helper fails", 1, {
        "svc/internal/api/bad.go": 'package api\nfunc h() { q := "SELECT id FROM t LIMIT $1" }\n'})
    probe("...but the same file with clampLimit does not", 0, {
        "svc/internal/api/ok.go": 'package api\nfunc h() { l := clampLimit(n)\n'
                                  ' q := "SELECT id FROM t LIMIT $1" }\n'})
    probe("...nor with parseLimitOffset", 0, {
        "svc/internal/api/ok.go": 'package api\nfunc h() { l, o := parseLimitOffset(r)\n'
                                  ' q := "SELECT id FROM t LIMIT $1 OFFSET $2" }\n'})
    probe("...nor a fixed LIMIT 100 literal", 0, {
        "svc/internal/api/ok.go": 'package api\nfunc h() { q := "SELECT id FROM t LIMIT 100" }\n'})
    probe("...nor the same query OUTSIDE internal/api/", 0, {
        "svc/internal/worker/sweep.go": 'package worker\nfunc h() { q := "SELECT id FROM t LIMIT $1" }\n'})

    # exclusions
    probe("an offender under tests/ is excluded", 0, {
        "svc/tests/bad.py": "def f(limit: int = Query(20)):\n    return []\n"})
    probe("an offender in a _test.go is excluded", 0, {
        "svc/internal/api/bad_test.go": 'package api\nfunc h() { q := "SELECT id FROM t LIMIT $1" }\n'})

    # baseline + shrink arm
    probe("a BASELINED offender passes", 0, {
        "svc/app/bad.py": "def f(limit: int = Query(20)):\n    return []\n"},
        baseline=frozenset({"services/svc/app/bad.py::limit: int = Query(20)):"}))
    probe("a BASELINE row matching no route fails", 1, {},
          baseline=frozenset({"services/svc/app/vanished.py::limit: int = Query(20)"}))

    # reach floors, one per leg
    probe("no python files at all is misuse (the declaration floor catches it)", 2, {
        "svc/internal/api/clean.go": CLEAN_GO}, seed=False)
    probe("no Go handler files at all is misuse, not a pass", 2, {
        "svc/app/routes.py": CLEAN_PY}, seed=False)
    probe("zero limit=Query declarations is misuse, not a pass", 2, {
        "svc/app/routes.py": "def f():\n    return []\n",
        "svc/internal/api/clean.go": CLEAN_GO}, seed=False)

    if failures:
        print(f"pagination-cap-lint --self-test: {failures} rule(s) did not behave")
        return 2
    print("pagination-cap-lint --self-test: every rule bites, and none cries wolf")
    return 0


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--self-test" in argv or "--selftest" in argv:
        return self_test()
    regen = "--regen" in argv
    unknown = [a for a in argv if a not in ("--regen", "--help", "-h")]
    if unknown:
        print(f"pagination-cap-lint: unknown arg(s): {unknown}", file=sys.stderr)
        print("usage: pagination-cap-lint.py [--regen] [--self-test] [--help]",
              file=sys.stderr)
        return 2

    if regen:
        hits, _reach = collect()
        for fp in sorted({fingerprint(h) for h in hits}):
            print(fp)
        return 0

    rc = self_test()
    if rc:
        return rc
    print()
    return check()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
