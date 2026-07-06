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
    # Go handler-layer list queries carrying today's PERF-3 debt. Many use a
    # server-set cap (batchSize/pipelineReadCap/*ListCap) and are safe; a few
    # (sharing listPublicInternal, statistics, usage-billing) are genuinely
    # unclamped client limits — tracked debt, not fixed by this lint.
    "services/auth-service/internal/api/handlers.go::ORDER BY f.created_at DESC LIMIT $2 OFFSET $3`, userID, limit, offset)",
    "services/auth-service/internal/api/mcp_audit.go::LIMIT $3 OFFSET $4`, uid, keyID, limit, offset)",
    "services/book-service/internal/api/favorites.go::ORDER BY f.created_at DESC LIMIT $2 OFFSET $3`, userID, limit, offset)",
    "services/book-service/internal/api/import.go::ORDER BY ts ASC LIMIT $2",
    "services/glossary-service/internal/api/canonical_summary_handler.go::LIMIT $2`, bookID, limit)",
    "services/glossary-service/internal/api/enrichment_handler.go::LIMIT $2`, bookID, limit)",
    "services/glossary-service/internal/api/evidence_handler.go::LIMIT $2`, entityID, limit)",
    "services/glossary-service/internal/api/extraction_handler.go::LIMIT $3",
    "services/glossary-service/internal/api/facts_handler.go::LIMIT $`+strconv.Itoa(len(args)), args...)",
    "services/glossary-service/internal/api/fold_handler.go::LIMIT $2",
    "services/glossary-service/internal/api/glossary_translate_handler.go::entitySQL += ` ORDER BY e.entity_id LIMIT $` + strconv.Itoa(limitArg) +",
    "services/glossary-service/internal/api/knowledge_client.go::fmt.Sprintf(`SELECT ge.entity_id::text `+base+` ORDER BY ge.created_at LIMIT %d`, limit),",
    "services/glossary-service/internal/api/merge_candidates_handler.go::q += ` LIMIT $3`",
    "services/glossary-service/internal/api/pipeline_read_tools.go::LIMIT $2`, bookID, pipelineReadCap)",
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


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    regen = "--regen" in argv
    unknown = [a for a in argv if a not in ("--regen", "--help", "-h")]
    if unknown:
        print(f"pagination-cap-lint: unknown arg(s): {unknown}", file=sys.stderr)
        print("usage: pagination-cap-lint.py [--regen] [--help]", file=sys.stderr)
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
