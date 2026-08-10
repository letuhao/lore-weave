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
# 🔴 **A NEW SUITE MUST BE ADDED HERE IN THE CHANGE THAT CREATES IT.** The denominator is
# enumerated from these files, so a suite absent from this tuple is 100% falsified by arithmetic —
# the self-derived-total failure this instrument was built to end, arriving through its own front
# door. `test_THE_SUITE_LIST_IS_EVERY_CP_SUITE_ON_DISK` in `test_cp1_membrane.py` is what makes it
# a gate rather than a request.
SUITES = (
    "tests/test_cp1_membrane.py",
    "tests/test_cp0_instrument.py",
    # 🔴 **FOUND BY THE GATE THAT ENFORCES THIS TUPLE, ON ITS FIRST RUN.** This suite has existed
    # since CP-0 and was never in the list, so its 13 guards were 100% declared by arithmetic while
    # the partition printed clean. The unproven count rising 246 -> 259 is therefore a CORRECTED
    # DENOMINATOR, not new debt: the guards were always unproven, and the instrument was measuring
    # a corpus it had chosen. Fifth time in this run a published denominator turned out to be a
    # lower bound, and the second time an instrument built to stop that produced one.
    "tests/test_cp0_merge_db.py",
    "tests/test_cp2_assembly.py",
    # CP-4's producer. Added in the same change as the suite, which is what the gate below exists
    # to force — the CP-0 suite above sat unregistered for a whole checkpoint and its 13 guards
    # were counted as declared by arithmetic while the partition printed clean.
    "tests/test_cp4_derive.py",
    "tests/test_cp3_plan.py",
    # 3.1's storage half. DB-gated: it skips without Postgres, and the skip says so rather
    # than passing quietly — "one live plan per session" is a partial unique INDEX and
    # "append-only" is a PRIMARY KEY, so a mock would assert my model of the database
    # instead of the database.
    "tests/test_cp3_plan_db.py",
    # CP-5.1/5.2's tool contract + rung 2. Added in the same change as the suite, per the note
    # above — and this suite is where §7's *every member needs a subject* is enforced, so leaving
    # it unregistered would have made the checkpoint's own gate 100% declared by arithmetic.
    "tests/test_cp5_toolcontract.py",
    # CP-5.3's resolver. Registered in the same change as the suite, per the note above.
    "tests/test_cp5_refresolve.py",
    # CP-5.5's typed call outcome. Registered in the same change as the suite.
    "tests/test_cp5_calloutcome.py",
    # CP-5.4's argument supplier. Registered in the same change as the suite.
    "tests/test_cp5_supplier.py",
    # CP-5.7's repeat semantics. Registered in the same change as the suite.
    "tests/test_cp5_repeat.py",
    # CP-5.10's name source. Registered in the same change as the suite.
    "tests/test_cp5_namesource.py",
    # CP-5.8's precondition. Registered in the same change as the suite.
    "tests/test_cp5_precondition.py",
    # CP-5.6's emits-at-plan-build. Registered in the same change as the suite.
    "tests/test_cp5_emits.py",
)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import agentruntime_gatecache as _gatecache  # noqa: E402

VERDICT = ROOT / "contracts" / "agentruntime-falsification-verdict.json"
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
    # The same subset the census mirrors, from the same module: 1,333 of 13,599 tracked files. This
    # runner copied the WHOLE repository for a suite that runs in one directory, and two copies of
    # "what can a measurement see" would drift the first time one was widened.
    prefixes = tuple(str(pref).replace("\\", "/") + "/" for pref in _gatecache.MIRROR_PREFIXES)
    try:
        listing = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                                 capture_output=True, check=True).stdout
        for rel in listing.split(b"\0"):
            if not rel:
                continue
            name = rel.decode("utf-8")
            if not name.startswith(prefixes):
                continue
            src = ROOT / name
            if not src.is_file():
                continue
            dst = out / name
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


def stale_anchors() -> list[str]:
    """Every falsifier whose anchor no longer matches the tree — checked WITHOUT running anything.

    🔴 **THIS EXISTS BECAUSE A STALE ANCHOR USED TO COST FIFTEEN MINUTES TO DISCOVER.** `_apply`
    refuses a falsifier that does not apply, which is the right behaviour — but it refuses it in
    the middle of `--run`, after however many suites have already executed, and CP-2 produced two
    of them in one session: an edit to `_suites` invalidated CP-2.1's census row, and CP-2.2's
    rewrite of the `withheld` expression invalidated another written twenty minutes earlier.

    **A falsifier is data about the tree, and data about the tree goes stale when the tree moves.**
    Checking it is a string comparison; paying for it with a suite run was a choice nobody made on
    purpose. This runs in the default mode, beside the partition, so the answer arrives in the same
    second as the edit that broke it.
    """
    out: list[str] = []
    for test, edits in sorted(FALSIFIERS.items()):
        for rel, old, _new in edits:
            path = ROOT / rel
            if not path.is_file():
                out.append(f"{test}: {rel} does not exist")
                continue
            n = path.read_bytes().decode("utf-8").replace("\r\n", "\n").count(old)
            if n != 1:
                out.append(f"{test}: {rel} has {n} occurrences (want 1) of {old[:60]!r}")
    return out


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
    ap.add_argument("--check", action="store_true",
                    help="is the recorded --run verdict about THIS tree? (exit 1 if stale/absent)")
    ap.add_argument("--force", action="store_true",
                    help="re-run every falsifier even when the recorded verdict is current")
    args = ap.parse_args(argv)

    if args.check:
        return _gatecache.check(VERDICT, "agentruntime-falsification")

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
            "# THE 13 ROWS FROM tests/test_cp0_merge_db.py ARE A THIRD THING, AND THEY ARE HERE\n"
            "# RATHER THAN IN `UNFALSIFIED` DELIBERATELY. They are DB-gated: without a real\n"
            "# Postgres they SKIP, and a skip is not a failure - so a falsifier row for one would\n"
            "# read GREEN and be filed as `the guard requires nothing`, which is a lie about a\n"
            "# guard that works. They are falsifiable, in an environment this runner does not\n"
            "# have. Saying that here is cheaper than a register that quietly means two things.\n"
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

    anchors = stale_anchors()
    for a in anchors:
        print(f"STALE ANCHOR   {a}")

    rc = 1 if (undeclared or now_proven or stale or anchors) else 0
    print(f"agentruntime-falsification: {len(guards)} guards, {len(FALSIFIERS)} falsified, "
          f"{len(UNFALSIFIED)} deliberately unfalsifiable, {len(recorded)} unproven, "
          f"{len(anchors)} stale anchor(s)")

    if args.run:
        # 🔴 Accelerator, not authority: CI passes `--force`, so a recorded verdict is never
        # the last word. 143 mutations at roughly five seconds each is twelve minutes, and four of
        # them ran in one session -- three on trees whose mirrored content had not moved.
        started_on = _gatecache.tree_digest()
        cached = None if args.force else _gatecache.load(VERDICT)
        if cached is not None:
            print(f"falsification: --run verdict is current for this tree "
                  f"({cached['tree_digest'][:12]}) - {cached['proven']}/{cached['total']} red; "
                  f"--force to re-run")
            return 1 if cached["failed"] else rc
        proven, failed = run_falsifiers(verbose=args.verbose)
        _gatecache.store(VERDICT, {"proven": len(proven), "total": len(proven) + len(failed),
                                   "failed": failed}, digest=started_on)
        for f in failed:
            print(f"NOT FALSIFIABLE  {f}")
        print(f"  -> {len(proven)}/{len(proven) + len(failed)} falsifiers red the guard they name")
        if failed:
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
