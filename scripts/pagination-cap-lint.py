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

# Go, second clamp form: the cap written INLINE rather than routed through a
# helper. glossary-service and statistics-service have no `clampLimit` to call,
# so every one of their list routes clamps in place — `if limit > 500 { limit =
# 500 }` — and read to this lint as unbounded. Six such sites sat in the BASELINE
# below with the note "clearing these properly means teaching the lint to find
# the clamp"; this is that. The pattern requires the SAME variable on both sides,
# so `if limit > 500 { offset = 500 }` is not a cap.
GO_INLINE_CAP = re.compile(
    r"if\s+(\w*[Ll]imit\w*)\s*>\s*\d+\s*\{[^}]*?\1\s*=\s*\d+", re.S)
GO_MIN_CAP = re.compile(r"\bmin\s*\(\s*\w*[Ll]imit\w*\s*,\s*\d+", re.I)

# Resolving a LIMIT to the function(s) that can reach it. Unlike the helper
# signal above, which passes a whole FILE, the inline signal is scoped to the
# enclosing function: a `clampLimit` call anywhere in a 3000-line server.go
# should not vouch for an unrelated query, and a NEW signal has no back-compat
# reason to inherit that looseness. A SQL string declared at file scope
# (`const fooSQL = `...``) belongs to whichever functions name it.
GO_FUNC = re.compile(r"^func\s+(?:\([^)]*\)\s*)?(\w+)", re.M)
GO_SQL_CONST = re.compile(r"^\s*(?:const\s+|var\s+)?(\w+)\s*=\s*`", re.M)


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


def _go_funcs(text: str) -> list[tuple[str, int, int]]:
    """(name, start, end) per top-level func; end at the next column-0 `}`."""
    out: list[tuple[str, int, int]] = []
    for fm in GO_FUNC.finditer(text):
        end = text.find(chr(10) + "}", fm.start())
        out.append((fm.group(1), fm.start(),
                    end + 2 if end != -1 else len(text)))
    return out


def _go_capped_in_scope(text: str, funcs: list[tuple[str, int, int]],
                        pos: int) -> bool:
    """True when every function that can reach the LIMIT at `pos` caps it.

    A LIMIT inside a function is judged by that function. A LIMIT in a
    file-scope SQL constant is judged by every function naming that constant —
    if ANY of them fails to cap, the site is still a finding, because that is
    the caller that reaches the database unbounded. An unresolvable constant
    (no identifier, or named by no function) is NOT quietly passed."""
    inner = [f for f in funcs if f[1] <= pos < f[2]]
    if inner:
        scopes = [inner[0]]
    else:
        ident = None
        for cm in GO_SQL_CONST.finditer(text[:pos]):
            ident = cm.group(1)
        if not ident:
            return False
        scopes = [f for f in funcs if ident in text[f[1]:f[2]]]
        if not scopes:
            return False
    return all(
        GO_INLINE_CAP.search(text[s:e]) or GO_MIN_CAP.search(text[s:e])
        for _n, s, e in scopes)


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
        return out  # file routes limits through a known clamp helper
    funcs = _go_funcs(full)
    for m in GO_PARAM_LIMIT.finditer(full):
        if _go_capped_in_scope(full, funcs, m.start()):
            continue
        n = full.count(chr(10), 0, m.start()) + 1
        out.append((rel, n, _strip(lines[n - 1])))
    return out


def iter_files():
    if not os.path.isdir(SERVICES):
        return
    for dirpath, dirnames, filenames in os.walk(SERVICES):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if not (fn.endswith(".py") or fn.endswith(".go")):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, REPO_ROOT).replace(os.sep, "/")
            if is_excluded(rel):
                continue
            yield full, rel


def collect() -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    for full, rel in iter_files():
        if rel.endswith(".py"):
            hits.extend(scan_python(full, rel))
        else:
            hits.extend(scan_go(full, rel))
    return hits


def fingerprint(hit: tuple[str, int, str]) -> str:
    """Line-number-free fingerprint: `rel::snippet`. Survives edits elsewhere
    in the file so the baseline doesn't churn on unrelated line shifts."""
    rel, _lineno, snippet = hit
    return f"{rel}::{snippet}"


# ── BASELINE — today's known offenders (PERF-3 debt, tracked not fixed here).
# Regenerate with `--regen`. Each entry is `rel::snippet`. Keep sorted.
BASELINE: frozenset[str] = frozenset({
    # ── PRUNED 2026-08-30 (T48ay) — 10 entries removed, none by fixing a route.
    # The inline-cap detector below now SEES the clamp these entries were parked
    # around, which is what their own note asked for: 'clearing these properly
    # means teaching the lint to find the clamp'. An entry that matches no current
    # hit is worse than none: it asserts debt that does not exist and makes the
    # tracked count unfalsifiable. Pruned by INTERSECTION with the live scan, never
    # by regenerating wholesale, so a genuinely new offender cannot be absorbed.
    # ── Verified 2026-07-31 (D-QC-GATES-BUILT-BUT-NOT-WIRED). This lint had never run
    # in CI; when it was first executed it reported these five, and all five are LINT
    # PRECISION false positives, checked one at a time rather than baselined on sight:
    #   · dek_shred_sweeper / reparse_sweeper — `batchSize` is a parameter of a background
    #     sweeper (`RunDekShredSweeper(ctx, interval, batchSize)`), set by the server. No
    #     client can influence it.
    #   · mcp_worlds — clamped 3 lines above the query: `if limit <= 0 || limit > 100 { limit = 20 }`.
    #   · entities_by_ids_handler — `if limit > 500 { limit = 500 }`.
    #   · entity_handler — same clamp; the `limit+1` is the documented peek-ahead row.
    # The regex sees `LIMIT $N` with a variable and cannot see a clamp 3-40 lines earlier.
    # Baselined WITH the verification rather than left red, so a genuinely unclamped route
    # still fails. Clearing these properly means teaching the lint to find the clamp.
    #   · epub_asset_retention — `limit` is the server-owned 100-item batch passed by
    #     RunEPUBAssetRetentionSweeper; no request path supplies it. This is the same
    #     background-sweeper exception as the two entries below, verified against the
    #     call site rather than weakening the handler scan for every API file.
    "services/book-service/internal/api/epub_asset_retention.go::LIMIT $2",
    "services/book-service/internal/api/dek_shred_sweeper.go::ORDER BY last_attempt_at ASC NULLS FIRST, requested_at ASC LIMIT $1`, batchSize)",
    "services/book-service/internal/api/reparse_sweeper.go::LIMIT $1`, batchSize)",
    # Go handler-layer list queries carrying today's PERF-3 debt. Many use a
    # server-set cap (batchSize/pipelineReadCap/*ListCap) and are safe; a few
    # (sharing listPublicInternal, statistics, usage-billing) are genuinely
    # unclamped client limits — tracked debt, not fixed by this lint.
    # ── 2026-07-29 · three verified NON-defects, traced before baselining ──────
    # The lint recognises a clamp by the NAME of the helper (`clampLimit` /
    # `parseLimitOffset`). These three clamp correctly without using it, so they
    # read as unbounded and are not. Each was traced to the value's source:
    #
    #   dek_shred_sweeper / reparse_sweeper — NOT ROUTES. `batchSize` is a
    #     parameter of `RunDekShredSweeper(ctx, interval, batchSize)`, a
    #     background sweeper started at boot with an operator-set batch. No
    #     client can reach it, which is outside this lint's own stated subject
    #     ("every list/search ENDPOINT").
    #   entity_handler — clamped INLINE and completely:
    #     `limit := queryInt(q.Get("limit"), 200)`, then `<1 → 1`, `>500 → 500`.
    #     glossary-service has no `clampLimit` to route through; introducing one
    #     for a single call site would be a different change than this lint asks
    #     for.
    #
    # The fourth finding from that run was NOT baselined — `mcp_worlds.go` was
    # fixed, because its inline clamp DISAGREED with the helper beside it
    # (over-max → 20 rather than the 100 `clampLimit` returns, so `world_list`
    # and `book_list` answered the same over-request differently).
    "services/book-service/internal/api/dek_shred_sweeper.go::ORDER BY last_attempt_at ASC NULLS FIRST, requested_at ASC LIMIT $1`, batchSize)",
    "services/book-service/internal/api/reparse_sweeper.go::LIMIT $1`, batchSize)",

    "services/auth-service/internal/api/handlers.go::ORDER BY f.created_at DESC LIMIT $2 OFFSET $3`, userID, limit, offset)",
    "services/auth-service/internal/api/mcp_audit.go::LIMIT $3 OFFSET $4`, uid, keyID, limit, offset)",
    "services/book-service/internal/api/favorites.go::ORDER BY f.created_at DESC LIMIT $2 OFFSET $3`, userID, limit, offset)",
    "services/book-service/internal/api/import.go::ORDER BY ts ASC LIMIT $2",
    "services/glossary-service/internal/api/canonical_summary_handler.go::LIMIT $2`, bookID, limit)",
    "services/glossary-service/internal/api/enrichment_handler.go::LIMIT $2`, bookID, limit)",
    "services/glossary-service/internal/api/evidence_handler.go::LIMIT $2`, entityID, limit)",
    "services/glossary-service/internal/api/facts_handler.go::LIMIT $`+strconv.Itoa(len(args)), args...)",
    "services/glossary-service/internal/api/fold_handler.go::LIMIT $2",
    "services/glossary-service/internal/api/glossary_translate_handler.go::entitySQL += ` ORDER BY e.entity_id LIMIT $` + strconv.Itoa(limitArg) +",
    "services/glossary-service/internal/api/knowledge_client.go::fmt.Sprintf(`SELECT ge.entity_id::text `+base+` ORDER BY ge.created_at LIMIT %d`, limit),",
    "services/glossary-service/internal/api/merge_candidates_handler.go::q += ` LIMIT $3`",
    "services/glossary-service/internal/api/pipeline_read_tools.go::ORDER BY revision_num DESC LIMIT $2`, entityID, entityRevisionsListCap)",
    "services/glossary-service/internal/api/plan_ops.go::q += ` LIMIT $2`",
    "services/glossary-service/internal/api/select_for_context_handler.go::LIMIT $3`, selectCols)",
    "services/glossary-service/internal/api/select_for_context_handler.go::LIMIT $4`, selectCols)",
    "services/glossary-service/internal/api/server.go::LIMIT $3`",
    "services/glossary-service/internal/api/server.go::LIMIT $4",
    "services/glossary-service/internal/api/server.go::LIMIT $4`",
    "services/glossary-service/internal/api/wiki_contributions_handler.go::LIMIT $2 OFFSET $3`, targetUser, limit, offset)",
    "services/glossary-service/internal/api/wiki_gold_pairs.go::LIMIT $2`,",
    "services/glossary-service/internal/api/wiki_handler.go::LIMIT $2 OFFSET $3`, articleID, limit, offset)",
    "services/sharing-service/internal/api/server.go::rows, err := s.pool.Query(r.Context(), `SELECT book_id FROM sharing_policies WHERE visibility='public' ORDER BY updated_at DESC LIMIT $1 OFFSET $2`, limit, offset)",
    "services/usage-billing-service/internal/api/server.go::LIMIT $1 OFFSET $2",
})


def selftest() -> int:
    """Drive scan_go over synthetic Go files whose verdict is known.

    A hand-bite is invisible to CI, and this detector has two properties that
    look identical when they are broken: the same-variable backreference, and
    the function scoping. Both are one character wide. The negative cases are
    the point — a detector validated only on code it was derived from is green
    by construction."""
    import tempfile

    NL = chr(10)
    Q = chr(96)   # backtick: Go raw string
    QUOTE = chr(34)

    CAP = "if limit > 500 {" + chr(10) + "        limit = 500" + chr(10) + "    }"
    cases: list[tuple[str, str, bool]] = [
        ("capped inline, one handler", NL.join([
            "package api",
            "func listThings(w http.ResponseWriter, r *http.Request) {",
            "    limit := queryInt(r.URL.Query().Get(" + QUOTE + "limit" + QUOTE + "), 200)",
            "    " + CAP,
            "    rows, _ := s.pool.Query(r.Context(), " + Q + "SELECT id FROM t LIMIT $1" + Q + ", limit)",
            "}"]), False),

        ("capped via min()", NL.join([
            "package api",
            "func listThings(w http.ResponseWriter, r *http.Request) {",
            "    limit = min(limit, 100)",
            "    rows, _ := s.pool.Query(ctx, " + Q + "SELECT id FROM t LIMIT $1" + Q + ", limit)",
            "}"]), False),

        ("file-scope SQL const, referenced by a capping handler", NL.join([
            "package api",
            "const listSQL = " + Q + "SELECT id FROM t LIMIT $1 OFFSET $2" + Q,
            "func listThings(w http.ResponseWriter, r *http.Request) {",
            "    " + CAP,
            "    rows, _ := s.pool.Query(ctx, listSQL, limit, offset)",
            "}"]), False),

        # ── the negatives ────────────────────────────────────────────────────
        ("NO cap at all", NL.join([
            "package api",
            "func listThings(w http.ResponseWriter, r *http.Request) {",
            "    limit := queryInt(r.URL.Query().Get(" + QUOTE + "limit" + QUOTE + "), 200)",
            "    rows, _ := s.pool.Query(ctx, " + Q + "SELECT id FROM t LIMIT $1" + Q + ", limit)",
            "}"]), True),

        # The guard assigns a DIFFERENT variable, so nothing bounds `limit`.
        # Only the backreference in GO_INLINE_CAP separates this from case 1;
        # without it the pattern reads any `= <int>` inside the block as a cap.
        ("guard tests limit but assigns offset", NL.join([
            "package api",
            "func listThings(w http.ResponseWriter, r *http.Request) {",
            "    if limit > 500 {",
            "        offset = 500",
            "    }",
            "    rows, _ := s.pool.Query(ctx, " + Q + "SELECT id FROM t LIMIT $1" + Q + ", limit)",
            "}"]), True),

        # One caller caps, the other does not. A file-level signal passes this;
        # the uncapped caller is the one that reaches the database unbounded.
        ("shared SQL const, only ONE of two callers caps", NL.join([
            "package api",
            "const listSQL = " + Q + "SELECT id FROM t LIMIT $1" + Q,
            "func listSafe(w http.ResponseWriter, r *http.Request) {",
            "    " + CAP,
            "    rows, _ := s.pool.Query(ctx, listSQL, limit)",
            "}",
            "func listUnsafe(w http.ResponseWriter, r *http.Request) {",
            "    rows, _ := s.pool.Query(ctx, listSQL, limit)",
            "}"]), True),

        # An SQL constant no function names cannot be shown to be capped. The
        # resolver returns "not capped" rather than passing it, so a resolution
        # failure costs a finding and never hides one. Seven of book-service
        # search.go's eight sites land here (spec section 22).
        ("file-scope SQL const that NO function references", NL.join([
            "package api",
            "const orphanSQL = " + Q + "SELECT id FROM t LIMIT $1" + Q,
            "func unrelated(w http.ResponseWriter, r *http.Request) {",
            "    " + CAP,
            "}"]), True),

        # The cap lives in a neighbouring handler, not the one that queries.
        ("cap in a DIFFERENT function than the query", NL.join([
            "package api",
            "func other(w http.ResponseWriter, r *http.Request) {",
            "    " + CAP,
            "}",
            "func listThings(w http.ResponseWriter, r *http.Request) {",
            "    rows, _ := s.pool.Query(ctx, " + Q + "SELECT id FROM t LIMIT $1" + Q + ", limit)",
            "}"]), True),
    ]

    failures = 0
    with tempfile.TemporaryDirectory() as td:
        for i, (name, src, want_flag) in enumerate(cases):
            path = os.path.join(td, "f%d.go" % i)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(src + chr(10))
            rel = "services/selftest-service/internal/api/f%d.go" % i
            got_flag = bool(scan_go(path, rel))
            ok = got_flag == want_flag
            failures += 0 if ok else 1
            verb = "flags" if want_flag else "passes"
            print("  %-4s %-52s expected the lint to %s -> %s"
                  % ("ok" if ok else "FAIL", name, verb,
                     "flagged" if got_flag else "passed"))

    if failures:
        print(chr(10) + "pagination-cap-lint --selftest: FAIL "
              "(%d of %d case(s) wrong)" % (failures, len(cases)))
        return 1
    print(chr(10) + "pagination-cap-lint --selftest: OK "
          "(%d cases, %d of them negative)"
          % (len(cases), sum(1 for c in cases if c[2])))
    return 0


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--selftest" in argv:
        return selftest()
    regen = "--regen" in argv
    unknown = [a for a in argv if a not in ("--regen", "--selftest", "--help", "-h")]
    if unknown:
        print(f"pagination-cap-lint: unknown arg(s): {unknown}", file=sys.stderr)
        print("usage: pagination-cap-lint.py [--regen] [--selftest] [--help]", file=sys.stderr)
        return 2

    hits = collect()

    if regen:
        for fp in sorted({fingerprint(h) for h in hits}):
            print(fp)
        return 0

    new = [h for h in hits if fingerprint(h) not in BASELINE]

    baselined = len(hits) - len(new)
    if not new:
        print(f"pagination-cap-lint: OK — every list route has a clamped cap "
              f"(PERF-3). {baselined} baselined offender(s) tracked.")
        return 0

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
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
