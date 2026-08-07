#!/usr/bin/env python3
"""The falsification gate — every guard must have an edit that makes it RED, or say why not.

🔴 **WHY THIS EXISTS, AND WHAT IT REPLACES.**

Six independent verification rounds on CP-1 converged on one shape and it is not the shape anyone
expected: **the fixes land, and the guards written for them have holes.** R26 is the clean case —
every one of its ten findings was a guard rather than a defect, and the two most serious were a
control that could not fail (`tainted = set(LIVE)` is unconditional, so the assertion asserting it
was a tautology) and a column that reddened for a different clause than the one it was testing.
Sibling pairs fixed at both ends across the run: **3 of 12**.

The standing rule *"a fix without a red-able test is not a closed finding"* has been in force the
whole time. It did not hold, because it is a thing a person is supposed to remember at the moment
they are most convinced they have just fixed something.

**What did hold is the reversion prover.** Apply the exact inverse of a fix; require the guard that
names it to go red. In R26 it caught **four fixes shipped with no guard at all** — `check_contract`'s
two pins, the allocator, the digest and the import gate — before either verifier saw the tree. It has
never flattered the builder, in any round.

So this promotes it from a throwaway script to an instrument with a checked-in register, on exactly
the shape the census already proved here:

* **the denominator comes from the SSOT** — every `test_*` in the two suites, enumerated by AST, not
  a list someone maintains. R26's own headline was an anti-vacuity assertion calibrated below the
  thing it guarded (`>= 15` over a corpus that had silently collapsed to 19 of 334);
* **the partition must be EXACT** — every guard is either falsified, deliberately unfalsifiable with
  a reason, or in the unproven backlog. A guard in none of the three is a finding, and that is the
  clause that would have caught the four;
* **the backlog is a checked-in file**, so adding a row is a decision and removing one is a closed
  finding. A new guard arriving with no falsifier fails immediately rather than in six rounds.

**What it does NOT do.** It does not say a guard is *right*, only that something can make it wrong.
A guard that reds for a bystander still reads RED here unless its falsifier names it — which is why
the runner requires the failing test to be the named one, and why R26's vacuous-column finding is a
verdict's job and not this file's.

Usage:
    python scripts/agentruntime-falsification.py            # the partition, exit 1 on drift
    python scripts/agentruntime-falsification.py --run      # apply every falsifier and verify
    python scripts/agentruntime-falsification.py --write    # regenerate the unproven backlog
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
_CS_REL = pathlib.Path("services") / "chat-service"
SUITES = ("tests/test_cp1_membrane.py", "tests/test_cp0_instrument.py")
UNPROVEN = ROOT / "contracts" / "agentruntime-falsification-unproven.txt"

sys.path.insert(0, str(ROOT / "scripts"))
from agentruntime_falsifiers import FALSIFIERS, UNFALSIFIED  # noqa: E402


def _guards() -> dict[str, str]:
    """`{test name: suite}` for every guard in the two suites — the denominator, from the SSOT.

    🔴 Enumerated rather than listed, because a hand-maintained denominator is the failure this run
    has paid for five times: every ratio the builder published was a lower bound, including from two
    instruments built to stop that.
    """
    out: dict[str, str] = {}
    for suite in SUITES:
        tree = ast.parse((ROOT / _CS_REL / suite).read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node.name.startswith("test_"):
                out[node.name] = suite
    return out


def _mirror() -> pathlib.Path:
    """A throwaway copy of the tracked WORKING tree. The live one is never written.

    The same design the census settled on after four kills left a `raise -> pass` in a tracked module
    in 4 of 4 attempts. Freed on every exit path, including the one where this function itself fails
    after `mkdtemp` — an allocator that can fail owns what it allocated until it returns.
    """
    out = pathlib.Path(tempfile.mkdtemp(prefix="lw-falsify-"))
    try:
        listing = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                                 capture_output=True, check=True).stdout
        for rel in listing.split(b"\0"):
            if not rel:
                continue
            src = ROOT / rel.decode("utf-8")
            if not src.is_file():
                continue
            dst = out / rel.decode("utf-8")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)
        raise
    return out


def _apply(mirror: pathlib.Path, edits) -> None:
    """Apply one falsifier's edits, or say precisely which anchor went stale.

    Line endings are normalised before matching: this tree is CRLF in the builder's checkout and LF
    in a fresh worktree, and a multi-line anchor written with `\\n` silently matches NOTHING on the
    other one. Two verifiers measured a different answer from the builder on the same file.
    """
    for rel, old, new in edits:
        p = mirror / rel
        src = p.read_bytes().decode("utf-8").replace("\r\n", "\n")
        n = src.count(old)
        if n != 1:
            raise SystemExit(
                f"ANCHOR STALE in {rel}: {n} occurrences (want 1) of {old[:70]!r}. A falsifier that "
                f"does not apply is not a falsifier; fix the row or delete it.")
        p.write_bytes(src.replace(old, new, 1).encode("utf-8"))


def _run_one(mirror: pathlib.Path, suite: str, test: str):
    return subprocess.run(
        [sys.executable, "-m", "pytest", suite, "-q", "--no-header", "-k", test],
        cwd=mirror / _CS_REL, capture_output=True, text=True)


def run_falsifiers(verbose: bool = False) -> tuple[list[str], list[str]]:
    """Apply each falsifier and require the guard it NAMES to be the failing test."""
    guards = _guards()
    proven, failed = [], []
    base = _mirror()
    originals = {}
    # 🔴 **THIS INSTRUMENT'S OWN CONTROLS LEAVE DEBRIS, BY DESIGN, AND THAT IS NOT A REASON TO
    # LEAVE IT.** The falsifier for `test_THE_ALLOCATOR_FREES_WHAT_IT_ALLOCATED_WHEN_IT_FAILS`
    # disables `_discard`, so the guard it drives leaks two mirrors on purpose. Somebody counting
    # `%TEMP%` afterwards then reads that as *"the allocator fix does not hold"* — which is exactly
    # what happened once already today, against the fix being verified.
    #
    # 🔴 **AND THE THROWAWAY PROVER THIS FILE WAS PROMOTED FROM ALREADY HAD THIS FIX.** Carrying the
    # instrument and not its repair is the pair-fixed-at-one-end failure, committed inside the
    # instrument built to make that failure expensive. Thirteenth in this run.
    temp_root = pathlib.Path(tempfile.gettempdir())
    try:
        for test, edits in sorted(FALSIFIERS.items()):
            before_dirs = {p for p in temp_root.glob("lw-census-*")}
            suite = guards.get(test)
            if suite is None:
                failed.append(f"{test}: no such guard in either suite (the row is stale)")
                continue
            for rel, _o, _n in edits:
                originals.setdefault(rel, (base / rel).read_bytes())
            try:
                _apply(base, edits)
                r = _run_one(base, suite, test)
                red = r.returncode != 0
                named = test in r.stdout
                if red and named:
                    proven.append(test)
                    if verbose:
                        print(f"  RED     {test}", flush=True)
                else:
                    why = ("GREEN - the guard requires nothing" if not red
                           else "RED, but a DIFFERENT test - the falsifier measured a bystander")
                    failed.append(f"{test}: {why}")
                    if verbose:
                        print(f"  {'GREEN  ' if not red else 'BYSTAND'} {test}", flush=True)
            finally:
                for rel, raw in originals.items():
                    (base / rel).write_bytes(raw)
                originals.clear()
                for p in {q for q in temp_root.glob("lw-census-*")} - before_dirs:
                    shutil.rmtree(p, ignore_errors=True)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return proven, failed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="apply every falsifier and verify it reds")
    ap.add_argument("--write", action="store_true", help="regenerate the unproven backlog")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    guards = _guards()
    unproven_now = sorted(set(guards) - set(FALSIFIERS) - set(UNFALSIFIED))

    if args.write:
        UNPROVEN.parent.mkdir(parents=True, exist_ok=True)
        UNPROVEN.write_text(
            "# Guards with NO falsifier yet - the backlog, not a decision.\n"
            "#\n"
            "# A row here says: nobody has written the edit that would make this guard RED, so\n"
            "# nothing establishes it can fail. Six rounds of verification found that the guards,\n"
            "# not the fixes, are where this run's defects now live - and in R26 the reversion\n"
            "# prover caught FOUR fixes shipped with no guard at all before either verifier saw\n"
            "# the tree. Adding a row is a decision; removing one is a closed finding.\n"
            "#\n"
            "# A guard that CANNOT be falsified by an edit belongs in `UNFALSIFIED` in\n"
            "# scripts/agentruntime_falsifiers.py, with the reason. That is a different claim.\n"
            "#\n"
            "# Generated by scripts/agentruntime-falsification.py --write.\n"
            + "".join(f"{g}\n" for g in unproven_now), "utf-8")
        print(f"wrote {len(unproven_now)} unproven guard(s) to {UNPROVEN.relative_to(ROOT)}")
        return 0

    if not UNPROVEN.exists():
        print(f"MISSING {UNPROVEN.relative_to(ROOT)} - run with --write and review the diff")
        return 1
    recorded = sorted(l.strip() for l in UNPROVEN.read_text("utf-8").splitlines()
                      if l.strip() and not l.startswith("#"))

    # 🔴 THE PARTITION MUST BE EXACT. A guard in none of the three sets is the clause that would
    # have caught R26's four unguarded fixes on the day they were written.
    undeclared = [g for g in unproven_now if g not in recorded]
    now_proven = [g for g in recorded if g not in unproven_now]
    stale = [g for g in set(FALSIFIERS) | set(UNFALSIFIED) if g not in guards]

    for g in undeclared:
        print(f"NO FALSIFIER   {g}  <- write one, or record it deliberately")
    for g in now_proven:
        print(f"NOW PROVEN     {g}  <- good news: drop it from the backlog in the same change")
    for g in stale:
        print(f"STALE ROW      {g}  <- names no guard in either suite")

    rc = 1 if (undeclared or now_proven or stale) else 0
    print(f"agentruntime-falsification: {len(guards)} guards, {len(FALSIFIERS)} falsified, "
          f"{len(UNFALSIFIED)} deliberately unfalsifiable, {len(recorded)} unproven")

    if args.run:
        proven, failed = run_falsifiers(verbose=args.verbose)
        for f in failed:
            print(f"NOT FALSIFIABLE  {f}")
        print(f"  -> {len(proven)}/{len(proven) + len(failed)} falsifiers red the guard they name")
        if failed:
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
