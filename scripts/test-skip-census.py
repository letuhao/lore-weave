#!/usr/bin/env python3
"""Report which test suites are gated off, and what would switch them on.

WHY THIS EXISTS
---------------
A full run of this repo reports roughly a thousand SKIPPED tests. Almost none of
them are rot — they are integration tests that need a live Postgres, Neo4j, MinIO
or KMS, and they skip cleanly when the corresponding `*_TEST_*` variable is unset.

That is the right behaviour and it is also indistinguishable, to someone new, from
a suite that has quietly died. "1000 skipped" reads as "nobody knows if this works",
and a contributor who cannot tell which tests their change actually exercised will
either ignore the skips or distrust the whole suite. Both are worse than knowing.

So the answer is discovered, not written down: this walks the test tree, finds every
skip and the environment variables the surrounding file reads, and prints the
mapping. A test added tomorrow appears without anyone updating a list — the property
an enumerated inventory can never have.

    python scripts/test-skip-census.py            # grouped by gating variable
    python scripts/test-skip-census.py --files    # per-file detail
    python scripts/test-skip-census.py --unset    # only what is gated off RIGHT NOW
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_result import GateResult  # noqa: E402  (repo-local helper; path set above)

REPO = Path(__file__).resolve().parent.parent

# Directories that hold tests. Discovered by walking, not enumerated per service —
# a new service's tests must be covered the day it appears.
TEST_DIR_NAMES = {"tests", "test", "__tests__"}
SOURCE_SUFFIXES = {".py", ".go"}
SKIP_PATTERNS = (
    re.compile(r"pytest\.skip\(\s*[\"'f]([^\"')]{0,120})"),
    re.compile(r"pytest\.mark\.skipif\("),
    re.compile(r"t\.Skip\(\s*\"([^\"]{0,120})"),
    re.compile(r"t\.Skipf\(\s*\"([^\"]{0,120})"),
)
# Any *_TEST_* / TEST_* variable the file consults, in either language.
ENV_READ = re.compile(
    r"(?:os\.environ(?:\.get)?\(|os\.getenv\(|Getenv\(|LookupEnv\()\s*[\"']"
    r"([A-Z][A-Z0-9_]*)[\"']"
)
# Only variables that plausibly gate infrastructure. TEST_USER / TEST_TOKEN and
# friends are fixture DATA, not switches, and listing them would bury the signal.
INFRA_HINT = re.compile(r"(_URL|_URI|_DSN|_ENDPOINT|_PG_|_ADDR|_HOST|_PORT)")


def iter_test_files():
    skip_dirs = {".git", "node_modules", "venv", ".venv", "__pycache__", "target", "dist"}
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        parts = set(Path(root).parts)
        if not (parts & TEST_DIR_NAMES):
            continue
        for name in files:
            p = Path(root) / name
            if p.suffix in SOURCE_SUFFIXES and ("test" in name or "conftest" in name):
                yield p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", action="store_true", help="per-file detail")
    ap.add_argument("--unset", action="store_true", help="only variables unset right now")
    args = ap.parse_args()

    by_var: dict[str, set[Path]] = defaultdict(set)
    ungated: list[tuple[Path, str]] = []
    scanned = 0

    for path in iter_test_files():
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        if not any(p.search(src) for p in SKIP_PATTERNS):
            continue
        env_vars = {v for v in ENV_READ.findall(src) if INFRA_HINT.search(v)}
        if env_vars:
            for v in env_vars:
                by_var[v].add(path.relative_to(REPO))
        else:
            reason = ""
            for pat in SKIP_PATTERNS:
                m = pat.search(src)
                if m and m.groups():
                    reason = (m.group(1) or "").strip()
                    break
            ungated.append((path.relative_to(REPO), reason))

    if not scanned:
        # An empty walk would make every number below a reassuring zero. Fail loudly.
        print("test-skip-census: FAIL — walked the repo and found no test files at all.")
        return 1

    rows = sorted(by_var.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    if args.unset:
        rows = [(v, f) for v, f in rows if not os.environ.get(v)]

    print(f"Scanned {scanned} test files.\n")
    print("Suites gated on infrastructure — set the variable to run them:\n")
    for var, files in rows:
        state = "SET" if os.environ.get(var) else "unset"
        print(f"  {var:<34} {len(files):>3} file(s)   [{state}]")
        if args.files:
            for f in sorted(files):
                print(f"      {f.as_posix()}")

    if ungated:
        print(f"\nSkips with no infrastructure variable ({len(ungated)}) — these are the ones")
        print("worth reading, since nothing external switches them on:\n")
        for f, reason in sorted(ungated)[:40]:
            print(f"  {f.as_posix()}")
            if reason:
                print(f"      reason: {reason}")
        if len(ungated) > 40:
            print(f"  ... and {len(ungated) - 40} more")

    result = GateResult(gate="rules")
    result.note(
        f"{scanned} test files scanned; {len(rows)} infrastructure variables gate "
        f"{sum(len(f) for _, f in rows)} file(s); {len(ungated)} file(s) skip without one"
    )
    print()
    print(result.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
