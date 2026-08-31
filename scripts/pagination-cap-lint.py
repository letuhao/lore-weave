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
#
# 🔴 **THE BOUND MAY BE A NAMED CONSTANT, AND REQUIRING A DIGIT MADE A REAL CAP INVISIBLE**
# (L6, 2026-08-30). `mcp_tools_read.go` caps in its own function:
#
#     const maxChapterBlocks = 300                                        // :246
#     if limit <= 0 || limit > maxChapterBlocks { limit = maxChapterBlocks }
#
# The previous pattern required `\d+` on both sides AND `if <limit> >` immediately after the
# `if`, so it failed twice over — the bound is a name, and the condition is compound. §22
# priced its batch as "7 blind spots plus 1 real verdict"; that one verdict was this, and the
# batch is 8 blind spots.
#
# ⚠️ **A VARIABLE IS STILL NOT A CAP.** The whole point of the signal is that the bound is
# KNOWABLE at the call site: `limit = someVar` bounds nothing a reader can check, and
# accepting it would turn this lint into one that passes whenever an assignment exists.
# `_go_int_consts` therefore resolves only package-level `const NAME = <int>` (and the
# `const ( … )` block form) — never a `var`, never a non-integer const.
GO_INLINE_CAP = re.compile(
    r"if\s+[^{}]*?\b(\w*[Ll]imit\w*)\s*>\s*(\w+)\b[^{}]*?\{[^}]*?\1\s*=\s*(\w+)\b", re.S)
GO_MIN_CAP = re.compile(r"\bmin\s*\(\s*\w*[Ll]imit\w*\s*,\s*(\w+)\s*\)", re.I)

#: `const NAME = 300` at package scope, and the same inside a `const ( … )` block. Only
#: INTEGER literals: a `const pageSize = someOther` chains to something this cannot see, and
#: a string const is not a bound at all.
GO_CONST_SINGLE = re.compile(r"^\s*const\s+(\w+)(?:\s+\w+)?\s*=\s*(\d+)\s*$", re.M)
GO_CONST_BLOCK = re.compile(r"^const\s*\(\s*$(.*?)^\)\s*$", re.M | re.S)
GO_CONST_BLOCK_ENTRY = re.compile(r"^\s*(\w+)(?:\s+\w+)?\s*=\s*(\d+)\s*(?://.*)?$", re.M)


def _go_int_consts(text: str) -> set[str]:
    """Package-level integer constants — the only names allowed as a cap's bound.

    Deliberately narrow. A `var` can be reassigned, a const chained to another const is not
    resolvable by a regex, and a string const is not a bound; all three read as "unknowable
    at the call site", which is the property this signal is actually asserting.
    """
    names = {m.group(1) for m in GO_CONST_SINGLE.finditer(text)}
    for block in GO_CONST_BLOCK.finditer(text):
        names |= {m.group(1) for m in GO_CONST_BLOCK_ENTRY.finditer(block.group(1))}
    return names


def _bound_is_knowable(token: str, consts: set[str]) -> bool:
    """A literal, or a name this file declares as an integer const. Nothing else."""
    return token.isdigit() or token in consts

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
    consts = _go_int_consts(text)
    return all(_scope_caps(text[s:e], consts) for _n, s, e in scopes)


def _scope_caps(body: str, consts: set[str]) -> bool:
    """True when this function body bounds its limit with something KNOWABLE.

    Both halves of an inline cap are checked — the comparison bound and the value assigned —
    because `if limit > 500 { limit = someVar }` compares against a literal and then bounds
    the query by whatever that variable happens to hold. A regex that looked only at the
    comparison would call that capped.
    """
    for m in GO_INLINE_CAP.finditer(body):
        if (_bound_is_knowable(m.group(2), consts)
                and _bound_is_knowable(m.group(3), consts)):
            return True
    for m in GO_MIN_CAP.finditer(body):
        if _bound_is_knowable(m.group(1), consts):
            return True
    return False


def _in_line_comment(text: str, pos: int) -> bool:
    """True when `pos` sits after a `//` on its own line.

    🔴 A comment is not a query (L6). `search.go` documents its own placeholders —
    `// $3 = escaped ILIKE pattern   $4 = limit` and `// per chapter, so ``LIMIT $4`` bounds
    distinct CHAPTERS` — and the scanner counted all three as unbounded list queries. Three
    of the five findings a stricter signal would have produced were prose ABOUT the cap,
    which is the "hygiene grep matches a comment" defect this repo has hit before: the
    instrument reporting on its own documentation.

    Line-comments only. A `/* … */` block containing a LIMIT is rare enough that guessing at
    it would add more failure modes than it removes, and a false POSITIVE here costs a
    finding rather than hiding one.
    """
    line_start = text.rfind(chr(10), 0, pos) + 1
    comment = text.find("//", line_start)
    return 0 <= comment < pos


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
        if _in_line_comment(full, m.start()):
            continue
        if _go_capped_in_scope(full, funcs, m.start()):
            continue
        n = full.count(chr(10), 0, m.start()) + 1
        out.append((rel, n, _strip(lines[n - 1])))
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
# finding. `frozenset` deduplicated them silently, so 39 literal rows were 36. Now 33,
# each exactly once.
#
# 2026-08-22 · AND `mcp_worlds.go` WAS STILL HERE. The paragraph above says it was
# removed; the row sat three lines under that sentence for another three weeks. It
# surfaced only when merging `main`, whose shrink arm reds on a baseline row matching
# no finding — the mechanism, not the prose, is what found it. A comment recording a
# deletion is not a deletion.
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
    "services/book-service/internal/api/dek_shred_sweeper.go::ORDER BY last_attempt_at ASC NULLS FIRST, requested_at ASC LIMIT $1`, batchSize)",
    "services/book-service/internal/api/favorites.go::ORDER BY f.created_at DESC LIMIT $2 OFFSET $3`, userID, limit, offset)",
    "services/book-service/internal/api/import.go::ORDER BY ts ASC LIMIT $2",
    "services/book-service/internal/api/reparse_sweeper.go::LIMIT $1`, batchSize)",
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
    "services/sharing-service/internal/api/server.go::rows, err := s.pool.Query(r.Context(), `SELECT book_id FROM sharing_policies WHERE visibility='public' ORDER BY updated_at DESC LIMIT $1 OFFSET $2`, limit, offset)",
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

    # ── L6 (refactor/entity-lifecycle): the Go INLINE-CAP resolution ───────────
    #
    # `NL`/`BT` are local: their harness writes Go bodies as plain literals, and a
    # backtick inside a Python string in a file this heavily quoted is how the
    # original cases were written too.
    NL = chr(10)
    BT = chr(96)
    #
    # These probe the half feat/game-logic's suite does not reach at all. Its Go cases
    # ask whether a clamp HELPER is present in the file; these ask whether the bound is
    # KNOWABLE at the call site, which is what `_go_capped_in_scope` decides.
    #
    # Ported into `probe()` rather than kept as a second harness: a gate with two
    # selftests has two things to keep honest, and the merge is where that becomes one.
    GO_CONST_CAP = ("package api" + NL +
                    "const maxChapterBlocks = 300" + NL +
                    "func h(w http.ResponseWriter, r *http.Request) {" + NL +
                    "    if limit <= 0 || limit > maxChapterBlocks {" + NL +
                    "        limit = maxChapterBlocks" + NL +
                    "    }" + NL +
                    "    rows, _ := s.pool.Query(ctx, " + chr(96) + "SELECT id FROM t LIMIT $1" + chr(96) + ", limit)" + NL +
                    "}" + NL)
    probe("a cap against a package-level int const passes", 0,
          {"svc/internal/api/constcap.go": GO_CONST_CAP})

    GO_VAR_CAP = ("package api" + NL +
                  "func h(w http.ResponseWriter, r *http.Request) {" + NL +
                  "    if limit > someVar {" + NL +
                  "        limit = someVar" + NL +
                  "    }" + NL +
                  "    rows, _ := s.pool.Query(ctx, " + chr(96) + "SELECT id FROM t LIMIT $1" + chr(96) + ", limit)" + NL +
                  "}" + NL)
    probe("a VARIABLE bound is NOT a cap", 1,
          {"svc/internal/api/varcap.go": GO_VAR_CAP})

    GO_MIXED_CAP = ("package api" + NL +
                    "func h(w http.ResponseWriter, r *http.Request) {" + NL +
                    "    if limit > 500 {" + NL +
                    "        limit = someVar" + NL +
                    "    }" + NL +
                    "    rows, _ := s.pool.Query(ctx, " + chr(96) + "SELECT id FROM t LIMIT $1" + chr(96) + ", limit)" + NL +
                    "}" + NL)
    probe("compares against a literal but ASSIGNS a variable — still uncapped", 1,
          {"svc/internal/api/mixedcap.go": GO_MIXED_CAP})

    GO_COMMENT_LIMIT = ("package api" + NL +
                        "func h(w http.ResponseWriter, r *http.Request) {" + NL +
                        "    // $1 = book_id   $2 = query   LIMIT $3 bounds the page" + NL +
                        "}" + NL)
    probe("a LIMIT inside a // comment is not a query", 0,
          {"svc/internal/api/commentonly.go": GO_COMMENT_LIMIT})

    GO_CAP_ELSEWHERE = ("package api" + NL +
                        "const listSQL = " + chr(96) + "SELECT id FROM t LIMIT $1" + chr(96) + NL +
                        "func capper(w http.ResponseWriter, r *http.Request) {" + NL +
                        "    if limit > 500 { limit = 500 }" + NL +
                        "}" + NL +
                        "func querier(w http.ResponseWriter, r *http.Request) {" + NL +
                        "    rows, _ := s.pool.Query(ctx, listSQL, limit)" + NL +
                        "}" + NL)
    probe("a cap in a DIFFERENT function than the query does not vouch for it", 1,
          {"svc/internal/api/elsewhere.go": GO_CAP_ELSEWHERE})

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
    unknown = [a for a in argv if a not in ("--regen", "--selftest", "--help", "-h")]
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
