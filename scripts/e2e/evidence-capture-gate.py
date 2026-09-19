#!/usr/bin/env python3
"""An evidence run that captured nothing must not read as an evidence run.

    python scripts/e2e/evidence-capture-gate.py                  # after a PLAYWRIGHT_EVIDENCE=1 run
    python scripts/e2e/evidence-capture-gate.py --results <dir>
    python scripts/e2e/evidence-capture-gate.py --self-test

WHY THIS EXISTS
---------------
`PLAYWRIGHT_EVIDENCE=1` turns video, screenshot and trace to `on` so a PASSING run leaves
something a person can watch. Every part of that is silent when it fails:

  * the variable is a string compare -- `PLAYWRIGHT_EVIDENCE=true` or `=yes` sets nothing,
  * `PLAYWRIGHT_VIDEO=off` still wins and is easy to leave exported in a shell,
  * a browser without a video encoder drops `video.webm` and keeps going,
  * and `--reporter=list` says `N passed` just as cheerfully either way.

So the failure mode is a green run, a confident report, and an empty directory -- which is the
exact shape of `govulncheck` scanning zero modules for months while its check looked like every
other passing check. **A scan that covered nothing must never be spellable as a pass**, and that
applies to evidence as much as to vulnerabilities.

WHAT IT CHECKS
--------------
Playwright writes one directory per test under `outputDir` (`tests/e2e/test-results`). This counts
the test directories that exist and the watchable artefacts inside them, and fails when there are
tests but no artefacts -- or when a test directory has none of its own.

`.last-run.json` is Playwright's own bookkeeping and is NOT evidence; it is present after every
run, including one that captured nothing, which is why it is excluded by name rather than by
extension.

Exit 0 = every test that ran left something watchable; 1 = it did not; 2 = misuse / self-test.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS = REPO / "frontend" / "tests" / "e2e" / "test-results"

#: Watchable by a person, or replayable into something watchable (the trace viewer).
EVIDENCE_SUFFIXES = {".webm", ".png", ".jpg", ".jpeg", ".zip"}

#: Playwright bookkeeping. Present after EVERY run, including one that captured nothing -- so
#: counting it as evidence would make this gate pass on exactly the case it exists to catch.
NOT_EVIDENCE = {".last-run.json"}


def scan(results: Path) -> tuple[list[Path], dict[str, int]]:
    """(test directories, {dir name: watchable artefact count}). Pure — takes a path, no globals."""
    if not results.is_dir():
        return [], {}
    dirs = sorted(d for d in results.iterdir() if d.is_dir())
    counts: dict[str, int] = {}
    for d in dirs:
        n = 0
        for f in d.rglob("*"):
            if f.is_file() and f.name not in NOT_EVIDENCE and f.suffix.lower() in EVIDENCE_SUFFIXES:
                n += 1
        counts[d.name] = n
    return dirs, counts


def self_test() -> int:
    """Both arms, on synthetic trees — a gate that cannot go red is not a gate."""
    import tempfile
    fails: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # A run that captured NOTHING: the bookkeeping file only, which is the real shape.
        empty = root / "empty"
        (empty / "a-test").mkdir(parents=True)
        (empty / ".last-run.json").write_text("{}", encoding="utf-8")
        dirs, counts = scan(empty)
        if not dirs:
            fails.append("did not see the test directory at all")
        elif sum(counts.values()) != 0:
            fails.append(f"counted {sum(counts.values())} artefact(s) in a run that captured none "
                         "-- .last-run.json is being read as evidence")

        # A real run.
        good = root / "good"
        (good / "a-test").mkdir(parents=True)
        (good / "a-test" / "video.webm").write_bytes(b"x")
        (good / "a-test" / "trace.zip").write_bytes(b"x")
        _, counts2 = scan(good)
        if counts2.get("a-test") != 2:
            fails.append(f"counted {counts2.get('a-test')} artefact(s) where 2 were written")

        # A directory with NO results at all must be distinguishable from a clean pass.
        dirs3, _ = scan(root / "does-not-exist")
        if dirs3:
            fails.append("invented test directories for a path that does not exist")

    if fails:
        print("evidence-capture-gate SELF-TEST FAILED:")
        for f in fails:
            print(f"  - {f}")
        return 2
    print("evidence-capture-gate: self-test OK — counts real artefacts, refuses to read "
          "`.last-run.json` as evidence, and reports an absent directory as absent")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(DEFAULT_RESULTS))
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()

    results = Path(a.results)
    dirs, counts = scan(results)

    if not dirs:
        print(f"evidence-capture-gate: FAIL — no per-test directory under {results}.")
        print("  -> either no test ran, or the run wrote nowhere. Neither is an evidence run,")
        print("     and an empty directory must not be reported as a clean one.")
        return 1

    total = sum(counts.values())
    barren = [n for n, c in counts.items() if c == 0]

    print(f"evidence-capture-gate: {len(dirs)} test dir(s), {total} watchable artefact(s).")

    if total == 0:
        print("\nFAIL — tests ran and captured NOTHING.")
        print("  -> PLAYWRIGHT_EVIDENCE must be exactly '1' (a string compare: 'true'/'yes' set")
        print("     nothing), and PLAYWRIGHT_VIDEO=off still wins if it is exported.")
        return 1

    if barren:
        print(f"\nFAIL — {len(barren)} test director(ies) captured nothing:\n")
        for n in sorted(barren)[:10]:
            print(f"  {n}")
        print("\n  -> a run is only evidence for the tests it actually recorded. Name the ones it")
        print("     did not, or fix the capture; do not average them away.")
        return 1

    print(f"Every one of the {len(dirs)} test dir(s) left something watchable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
