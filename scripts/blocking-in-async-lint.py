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
`BASELINE` exempts known offenders by a line-number-free fingerprint, so the
lint flags only NEW ones. **Measured 2026-08-12 it is EMPTY, and this tree has
zero offenders** — the gate passes because the rule holds, not because the
baseline absorbs anything. That distinction was worth fixing in this docstring:
the previous wording said the lint "passes clean on the CURRENT tree via a
BASELINE of today's known offenders", which described a mechanism that was
doing nothing. A gate's header claiming a number nothing measures is the same
defect the gate exists to prevent, one level up.

Refresh the baseline after intentionally fixing/adding offenders:
    python scripts/blocking-in-async-lint.py --regen

GT5 · what this gate lacked
---------------------------
It could not say what it SCANNED. `iter_files` opens with
`if not os.path.isdir(SERVICES): return`, so a renamed tree yielded zero files,
zero hits, and the same cheerful `OK` line — byte-identical to compliance
(`BDR-82`). A REACH FLOOR (`GT-F3`) now prints the file count and exits 2 on a
zero.

Unparseable files were invisible in the same way: `scan_python` swallows a
`SyntaxError` and returns no hits, so a file the gate could not read was counted
as a file it had checked. The count is now printed and ratcheted at zero. There
is deliberately no downward arm on that ratchet — it is already at the floor, and
a branch that cannot fire is the defect this board removes (`GTD-7`).

`BASELINE` had no SHRINK ARM (`GT-F5`): a fingerprint matching no hit exempts
nothing today and silently re-exempts its call the day the code returns.

Usage
-----
    python scripts/blocking-in-async-lint.py             # self-test, then scan
    python scripts/blocking-in-async-lint.py --self-test # the proof alone
    python scripts/blocking-in-async-lint.py --regen     # print fingerprints
    python scripts/blocking-in-async-lint.py --help

Exit 0 = clean (or baseline-only). 1 = NEW violation. 2 = usage / self-test
failure / nothing scanned.
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

# A file this scanner cannot parse is a file it did not check, and it was being
# reported as clean. Measured 2026-08-12: 0 of 958.
UNPARSEABLE_BASELINE = 0


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


def scan_python(path: str, rel: str) -> tuple[list[tuple[str, int, str]], bool]:
    """Returns (hits, parsed_ok). A file that does not parse yields no hits —
    which is why the caller must count it rather than treat it as clean."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            src = fh.read()
    except OSError:
        return [], False
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return [], False  # not parseable on this interpreter — never crash CI
    v = _Visitor(rel)
    v.visit(tree)
    return v.hits, True


def iter_files(services_root: str = SERVICES, repo_root: str = REPO_ROOT):
    if not os.path.isdir(services_root):
        return
    for dirpath, dirnames, filenames in os.walk(services_root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, repo_root).replace(os.sep, "/")
            if is_excluded(rel):
                continue
            yield full, rel


def collect(services_root: str = SERVICES, repo_root: str = REPO_ROOT):
    """Returns (hits, n_scanned, n_unparseable)."""
    hits: list[tuple[str, int, str]] = []
    scanned = unparseable = 0
    for full, rel in iter_files(services_root, repo_root):
        scanned += 1
        found, ok = scan_python(full, rel)
        if not ok:
            unparseable += 1
        hits.extend(found)
    return hits, scanned, unparseable


def fingerprint(hit: tuple[str, int, str]) -> str:
    """Line-number-free: `rel::reason` (the reason encodes which primitive)."""
    rel, _lineno, reason = hit
    return f"{rel}::{reason.split(' —')[0]}"


# ── BASELINE — known blocking-in-async offenders. Regenerate w/ --regen.
# Measured 2026-08-12: EMPTY, and the tree has zero offenders. The shrink arm
# below is what keeps that honest if a row is ever added and later fixed.
BASELINE: frozenset[str] = frozenset()


def check(
    services_root: str = SERVICES,
    repo_root: str = REPO_ROOT,
    baseline: frozenset[str] = BASELINE,
    unparseable_max: int = UNPARSEABLE_BASELINE,
) -> int:
    """The REAL checker, parameterised so `--self-test` can drive it over a
    synthetic tree instead of re-implementing its rules."""
    hits, scanned, unparseable = collect(services_root, repo_root)

    # ── REACH FLOOR (GT-F3). Zero files is a moved tree, not compliance.
    if scanned == 0:
        print(f"blocking-in-async-lint: ERROR — scanned 0 python file(s) under "
              f"{services_root}. A walk that reached nothing is byte-identical to a "
              f"clean tree, exit code included (BDR-82).", file=sys.stderr)
        return 2

    problems: list[str] = []

    # ── SHRINK ARM (GT-F5). A baseline fingerprint that matches no hit exempts
    # nothing today, and silently re-exempts its call the day the code returns.
    live = {fingerprint(h) for h in hits}
    dead = sorted(fp for fp in baseline if fp not in live)
    for fp in dead:
        problems.append(
            f"BASELINE row `{fp}` matches no call in this tree — it exempts nothing "
            f"and would re-exempt that call the day it returns. Delete it (--regen "
            f"reprints the live set).")

    # ── A file that does not parse is a file this gate did NOT check, and it was
    # being counted as clean. Ratchet at zero. There is no downward arm because
    # zero is the floor — a branch that cannot fire is the defect this board
    # removes, not a symmetry to preserve (GTD-7).
    if unparseable > unparseable_max:
        problems.append(
            f"{unparseable} python file(s) could not be parsed, so PERF-4 was never "
            f"checked in them (ratchet is {unparseable_max}). Fix the syntax, or the "
            f"gate is silently blind to them.")

    new = [h for h in hits if fingerprint(h) not in baseline]
    baselined = len(hits) - len(new)

    if new or problems:
        if new:
            print("blocking-in-async-lint: FAIL — NEW blocking call in an async def (PERF-4)\n")
            print("  A blocking call on the event loop stalls every concurrent request.")
            print("  Offload CPU work to `await asyncio.to_thread(...)` / an executor,")
            print("  and use async clients (httpx.AsyncClient, asyncio.sleep, asyncpg).\n")
            for rel, lineno, reason in sorted(new):
                print(f"  {rel}:{lineno}: {reason}")
            print("\nIf this is tracked debt, add a DEFERRED row and refresh the")
            print("baseline: python scripts/blocking-in-async-lint.py --regen")
        for p in problems:
            print(f"blocking-in-async-lint: FAIL — {p}")
        return 1

    print(f"blocking-in-async-lint: OK — no blocking call in an async def (PERF-4). "
          f"{scanned} file(s) scanned, {unparseable} unparseable, "
          f"{baselined} baselined offender(s) tracked.")
    return 0


# ── SELF-TEST ────────────────────────────────────────────────────────────────
CLEAN = "import asyncio\n\n\nasync def h():\n    await asyncio.sleep(1)\n"


def self_test() -> int:
    """Every rule against input that violates it AND input that must not trip it,
    driving the REAL `check()` over a synthetic services tree."""
    import contextlib
    import io
    import tempfile

    failures = 0

    def probe(name: str, body: str, want: int, *, rel="svc/app/h.py",
              baseline=frozenset(), unparseable_max=0, empty=False,
              missing=False) -> None:
        nonlocal failures
        with tempfile.TemporaryDirectory() as d:
            services = os.path.join(d, "services")
            # `missing` must NOT create the directory — an earlier draft used the
            # same fixture for both floor probes, so one of them was a duplicate
            # wearing the other's name, which certifies coverage of an input it
            # never read (GTD-17).
            if not missing:
                os.makedirs(services, exist_ok=True)
            if not (empty or missing):
                # a clean file is always present, so the reach floor stays quiet
                # and each probe below tests exactly ONE rule
                clean = os.path.join(services, "svc", "app", "clean.py")
                os.makedirs(os.path.dirname(clean), exist_ok=True)
                with open(clean, "w", encoding="utf-8") as fh:
                    fh.write(CLEAN)
                target = os.path.join(services, *rel.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w", encoding="utf-8") as fh:
                    fh.write(body)
            try:
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    got = check(services, d, baseline, unparseable_max)
            except Exception as e:  # noqa: BLE001 - a crash is what this asserts against
                failures += 1
                print(f"  FAIL {name}: raised {type(e).__name__}: {e} — it must return a code")
                return
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: rc={got} (want {want})")

    print("blocking-in-async-lint --self-test")

    probe("a clean async handler passes", CLEAN, 0)

    # the four primitives
    probe("time.sleep in an async def fails",
          "import time\n\n\nasync def h():\n    time.sleep(1)\n", 1)
    probe("requests.get in an async def fails",
          "import requests\n\n\nasync def h():\n    requests.get('http://x')\n", 1)
    probe("psycopg2.connect in an async def fails",
          "import psycopg2\n\n\nasync def h():\n    psycopg2.connect('dsn')\n", 1)
    probe("urllib.request.urlopen in an async def fails",
          "import urllib.request\n\n\nasync def h():\n    urllib.request.urlopen('http://x')\n", 1)

    # scope — the whole reason this uses `ast` and not grep
    probe("...but time.sleep in a SYNC def does not",
          "import time\n\n\ndef h():\n    time.sleep(1)\n", 0)
    probe("...nor in a nested sync def (the offload target)",
          "import time\n\n\nasync def h():\n    def work():\n        time.sleep(1)\n"
          "    return work\n", 0)
    probe("...nor in a lambda (also an offload target)",
          "import time\n\n\nasync def h():\n    f = lambda: time.sleep(1)\n    return f\n", 0)
    probe("...nor as a bare reference passed to to_thread",
          "import asyncio, time\n\n\nasync def h():\n"
          "    await asyncio.to_thread(time.sleep, 1)\n", 0)
    probe("...but a nested ASYNC def inside a sync def still fails",
          "import time\n\n\ndef outer():\n    async def h():\n        time.sleep(1)\n"
          "    return h\n", 1)

    # exclusions
    probe("an offender under tests/ is excluded", "import time\n\n\nasync def h():\n"
          "    time.sleep(1)\n", 0, rel="svc/tests/thing.py")
    probe("an offender in a test_*.py is excluded", "import time\n\n\nasync def h():\n"
          "    time.sleep(1)\n", 0, rel="svc/app/test_thing.py")

    # baseline + its shrink arm
    probe("a BASELINED offender passes",
          "import time\n\n\nasync def h():\n    time.sleep(1)\n", 0,
          baseline=frozenset({"services/svc/app/h.py::time.sleep"}))
    probe("a BASELINE row matching no call fails (shrink arm)", CLEAN, 1,
          baseline=frozenset({"services/svc/app/vanished.py::time.sleep"}))

    # the unparseable ratchet
    probe("an UNPARSEABLE file fails — it was never checked",
          "async def h(:\n    pass\n", 1)
    probe("...and passes when the ratchet allows it",
          "async def h(:\n    pass\n", 0, unparseable_max=1)

    # the reach floor
    probe("a MISSING services tree is misuse, not a pass", "", 2, missing=True)
    probe("an EMPTY services tree is misuse, not a pass", "", 2, empty=True)

    if failures:
        print(f"blocking-in-async-lint --self-test: {failures} rule(s) did not behave")
        return 2
    print("blocking-in-async-lint --self-test: every rule bites, and none cries wolf")
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
        print(f"blocking-in-async-lint: unknown arg(s): {unknown}", file=sys.stderr)
        print("usage: blocking-in-async-lint.py [--regen] [--self-test] [--help]",
              file=sys.stderr)
        return 2

    if regen:
        hits, _scanned, _bad = collect()
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
