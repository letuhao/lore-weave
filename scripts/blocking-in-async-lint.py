#!/usr/bin/env python3
"""blocking-in-async-lint.py — enforce PERF-4 (no blocking in async).

Standard: docs/standards/performance.md › Rules › **PERF-4 · No blocking in
async.** No blocking call (sync DB driver, `requests`, `time.sleep`, CPU loop)
inside an `async def` handler; CPU-bound work goes to
`asyncio.to_thread`/executor (the kg_unify fix is the reference). A blocking
call on the event loop stalls EVERY concurrent request in that worker.

What it flags
-------------
A Call to a known-blocking primitive whose *nearest enclosing function* is an
`async def`:
  • `time.sleep(...)`                — blocks the loop; use `await asyncio.sleep`
  • `requests.<method>(...)`         — sync HTTP; use httpx.AsyncClient
  • `psycopg2` connect/execute       — sync DB driver; use asyncpg
  • `urllib.request.urlopen(...)`    — sync HTTP

Uses the stdlib `ast` module (cross-platform, no deps) so it is precise about
scope: a blocking call inside a nested *sync* `def` or a `lambda` (e.g. the
target of `asyncio.to_thread` / `run_in_executor`) is NOT flagged — that is
exactly the correct offload pattern. Passing a bare function reference
(`asyncio.to_thread(time.sleep, 1)`) is also fine: it is not a Call to
`time.sleep`.

"Obvious CPU loops" from the standard are intentionally NOT auto-detected —
there is no low-false-positive static signal for them; they stay a review
concern.

Baseline / allowlist
--------------------
Mirrors `scripts/ai-provider-gate.py`: passes clean (exit 0) on the CURRENT
tree via a BASELINE of today's known offenders (fingerprinted line-number-free)
and flags only NEW ones. Test/script/eval files are excluded.

Refresh the baseline after intentionally fixing/adding offenders:
    python scripts/blocking-in-async-lint.py --regen

Usage
-----
    python scripts/blocking-in-async-lint.py           # full scan (CI / manual)
    python scripts/blocking-in-async-lint.py --regen   # print current fingerprints
    python scripts/blocking-in-async-lint.py --help

Exit 0 = clean (or baseline-only). Exit 1 = NEW violation. Exit 2 = usage.
"""
from __future__ import annotations

import ast
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICES = os.path.join(REPO_ROOT, "services")

EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", ".next", ".git", "vendor", "coverage",
}

# Blocking primitives. Each entry: a matcher on a Call's dotted func name.
BLOCKING_EXACT = {
    "time.sleep": "time.sleep — blocks the event loop; use `await asyncio.sleep(...)`",
    "urllib.request.urlopen": "urllib.request.urlopen — sync HTTP; use httpx.AsyncClient",
}
# Prefix matches: any attribute chain starting with these roots.
BLOCKING_PREFIX = {
    "requests.": "requests.* — sync HTTP on the loop; use httpx.AsyncClient",
    "psycopg2.": "psycopg2.* — sync DB driver on the loop; use asyncpg",
}


def is_excluded(rel: str) -> bool:
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
    )


def _dotted(node: ast.AST) -> str | None:
    """Best-effort dotted name for a Call's func (`a.b.c`); None if dynamic."""
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def _reason(dotted: str) -> str | None:
    if dotted in BLOCKING_EXACT:
        return BLOCKING_EXACT[dotted]
    for pref, reason in BLOCKING_PREFIX.items():
        if dotted.startswith(pref):
            return reason
    return None


class _Visitor(ast.NodeVisitor):
    """Walk the tree tracking whether the *nearest* enclosing function is
    async. A blocking Call is a violation only when async_depth's top is True."""

    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.stack: list[bool] = []  # True == nearest enclosing fn is async
        self.hits: list[tuple[str, int, str]] = []

    def _visit_fn(self, node, is_async: bool) -> None:
        self.stack.append(is_async)
        self.generic_visit(node)
        self.stack.pop()

    def visit_AsyncFunctionDef(self, node):  # noqa: N802
        self._visit_fn(node, True)

    def visit_FunctionDef(self, node):  # noqa: N802
        self._visit_fn(node, False)

    def visit_Lambda(self, node):  # noqa: N802
        # a lambda body is a fresh (sync) scope — offloaded work runs here
        self._visit_fn(node, False)

    def visit_Call(self, node):  # noqa: N802
        if self.stack and self.stack[-1]:
            dotted = _dotted(node.func)
            if dotted:
                reason = _reason(dotted)
                if reason:
                    self.hits.append((self.rel, node.lineno, reason))
        self.generic_visit(node)


def scan_python(path: str, rel: str) -> list[tuple[str, int, str]]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            src = fh.read()
    except OSError:
        return []
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return []  # not parseable on this interpreter — skip, don't crash CI
    v = _Visitor(rel)
    v.visit(tree)
    return v.hits


def iter_files():
    if not os.path.isdir(SERVICES):
        return
    for dirpath, dirnames, filenames in os.walk(SERVICES):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, REPO_ROOT).replace(os.sep, "/")
            if is_excluded(rel):
                continue
            yield full, rel


def collect() -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    for full, rel in iter_files():
        hits.extend(scan_python(full, rel))
    return hits


def fingerprint(hit: tuple[str, int, str]) -> str:
    """Line-number-free: `rel::reason` (the reason encodes which primitive)."""
    rel, _lineno, reason = hit
    return f"{rel}::{reason.split(' —')[0]}"


# ── BASELINE — today's known blocking-in-async offenders. Regenerate w/ --regen.
BASELINE: frozenset[str] = frozenset({
    # placeholder — populated by --regen against the current tree
})


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    regen = "--regen" in argv
    unknown = [a for a in argv if a not in ("--regen", "--help", "-h")]
    if unknown:
        print(f"blocking-in-async-lint: unknown arg(s): {unknown}", file=sys.stderr)
        print("usage: blocking-in-async-lint.py [--regen] [--help]", file=sys.stderr)
        return 2

    hits = collect()

    if regen:
        for fp in sorted({fingerprint(h) for h in hits}):
            print(fp)
        return 0

    new = [h for h in hits if fingerprint(h) not in BASELINE]
    baselined = len(hits) - len(new)

    if not new:
        print(f"blocking-in-async-lint: OK — no blocking call in an async def "
              f"(PERF-4). {baselined} baselined offender(s) tracked.")
        return 0

    print("blocking-in-async-lint: FAIL — NEW blocking call in an async def (PERF-4)\n")
    print("  A blocking call on the event loop stalls every concurrent request.")
    print("  Offload CPU work to `await asyncio.to_thread(...)` / an executor,")
    print("  and use async clients (httpx.AsyncClient, asyncio.sleep, asyncpg).\n")
    for rel, lineno, reason in sorted(new):
        print(f"  {rel}:{lineno}: {reason}")
    print("\nIf this is tracked debt, add a DEFERRED row and refresh the")
    print("baseline: python scripts/blocking-in-async-lint.py --regen")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
