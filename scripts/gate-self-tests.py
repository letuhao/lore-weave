#!/usr/bin/env python3
"""Run EVERY gate's `--self-test`. Discovered, never enumerated.

WHY THIS EXISTS
---------------
`D-380` established that a self-test nobody runs is not a self-test, and wired
the three game-tier gates into the pre-commit hook. A cold-start review then
measured the remedy and found the hook reached **three** of the `scripts/*.py`
that advertise `--self-test`, out of *"fourteen"* it counted at the time. The
rest remained in exactly the state `D-380` calls intolerable, and the next one
written would have been default-uncovered — which is NV-3, the shape the comment
below that same hook line explicitly forbids:

    Scope is DIRECTORIES ... an enumerated list is default-uncovered, NV-3.

CI did not close it either: `gate-wiring-gate --run-all` invokes each gate with
**no arguments**, so it exercises normal mode and never a self-test.

So the scope here is a DIRECTORY and a PREDICATE:

    every `scripts/*.py` whose source registers `--self-test`

A gate added tomorrow is covered on its first commit, with nobody to remember.

    python scripts/gate-self-tests.py             # run them all
    python scripts/gate-self-tests.py --list      # what would run
    python scripts/gate-self-tests.py --self-test # this driver's own cases
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SELF = Path(__file__).name

# The floor exists because DISCOVERY CAN SILENTLY FIND NOTHING. A predicate that
# stops matching -- a rename, a refactor of how the flag is registered -- would
# turn this driver into a green no-op, which is the exact failure it exists to
# prevent, one level up. The number is a floor and not an equality on purpose:
# it must not need editing when a gate is added, only when many are removed.
MIN_EXPECTED = 10


def discover(root: Path | None = None) -> list[Path]:
    """Every `scripts/*.py` that advertises `--self-test`, except this driver.

    Excluding self is not tidiness: discovery would otherwise find this file,
    run it with `--self-test`, and recurse until the stack ends.
    """
    root = root or (REPO / "scripts")
    found = []
    for p in sorted(root.glob("*.py")):
        # A DOT-PREFIXED file is not a gate. `gate-bite-harness` mutates a gate
        # by writing `.bite-<name>.py` beside the original -- same directory, so
        # `REPO` still resolves -- and that copy sat in the very directory this
        # scans. Discovery picked it up, ran it, and it discovered the copy in
        # turn: a mutation of THIS file then reported GREEN for a reason that had
        # nothing to do with the rule under test. Dotfiles are editor swap files
        # and scratch copies everywhere else too; none of them are gates.
        if p.name == SELF or p.name.startswith("."):
            continue
        try:
            if "--self-test" in p.read_text(encoding="utf-8", errors="replace"):
                found.append(p)
        except OSError:
            continue
    return found


def run_all(scripts: list[Path], run=None) -> int:
    runner = run or (lambda p: subprocess.run(
        [sys.executable, str(p), "--self-test"], cwd=REPO,
        capture_output=True, text=True))
    failed = []
    for p in scripts:
        t0 = time.time()
        out = runner(p)
        ms = int((time.time() - t0) * 1000)
        ok = out.returncode == 0
        print(f"  {'ok  ' if ok else 'FAIL'} {p.name:<44} {ms:>6}ms")
        if not ok:
            failed.append(p.name)
            for line in (out.stdout + out.stderr).splitlines():
                if line.strip():
                    print(f"        {line}")
    if failed:
        print(f"\ngate-self-tests: {len(failed)} gate(s) RED — {', '.join(failed)}",
              file=sys.stderr)
        return 1
    print(f"\ngate-self-tests: {len(scripts)} gate self-tests green")
    return 0


def self_test() -> int:
    failures = 0

    # Discovery must find the real gates, and must not find itself.
    found = discover()
    names = {p.name for p in found}
    if SELF in names:
        failures += 1
        print(f"  FAIL discovery found {SELF}; running it would recurse forever")
    else:
        print("  ok  discovery excludes this driver")
    if len(found) < MIN_EXPECTED:
        failures += 1
        print(f"  FAIL discovery found {len(found)} gates, floor is {MIN_EXPECTED} — "
              "the predicate has probably stopped matching")
    else:
        print(f"  ok  discovery found {len(found)} gates (floor {MIN_EXPECTED})")

    # ...and `main` must REFUSE a run that discovered too few, rather than
    # reporting "0 gate self-tests green". A predicate that silently stops
    # matching turns this driver into a green no-op, which is the failure it
    # exists to prevent, one level up.
    import contextlib
    import io as _io
    starved_err = _io.StringIO()
    with contextlib.redirect_stdout(_io.StringIO()), contextlib.redirect_stderr(starved_err):
        starved = main(argv=[], discover_fn=lambda: [])
        healthy = main(argv=["--list"], discover_fn=lambda: [REPO / "scripts" / "a-gate.py"])
    # The REASON is asserted, not just the exit code. A version that checked only
    # `!= 0` passed while the mutation under test was live, because the run had
    # gone non-zero for an unrelated reason -- a red gate somewhere in the list.
    # A case satisfied by any failure is a case that proves nothing about its own
    # subject.
    if starved == 0 or "discovery found only" not in starved_err.getvalue():
        failures += 1
        print("  FAIL main() must refuse a starved discovery, and say so: "
              f"rc={starved}, stderr={starved_err.getvalue()!r}")
    else:
        print("  ok  main() refuses a run that discovered too few gates, and says why")
    if healthy != 0:
        failures += 1
        print("  FAIL --list must not apply the floor; it reports, it does not run")
    else:
        print("  ok  --list reports without applying the floor")

    # A gate that advertises `--self-test` but is not in the list is the whole
    # defect. Three known ones, asserted by name, so a predicate that narrows is
    # caught even while the floor still passes.
    for required in ("citation-gate.py", "actor-hub-figures-gate.py",
                     "hashed-substrate-float-gate.py", "deferral-gate.py"):
        if required not in names:
            failures += 1
            print(f"  FAIL {required} advertises --self-test and was not discovered")

    # A file WITHOUT the flag must not be picked up, or every script in the
    # directory would be invoked with an argument it does not understand.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "has-flag.py").write_text('ap.add_argument("--self-test")', encoding="utf-8")
        (tmp / "no-flag.py").write_text("print(1)", encoding="utf-8")
        # A scratch copy of a gate, which carries the flag and must still be
        # skipped — `gate-bite-harness` writes exactly this shape beside the
        # original while it mutates it.
        (tmp / ".bite-has-flag.py").write_text('ap.add_argument("--self-test")', encoding="utf-8")
        got = {p.name for p in discover(tmp)}
        if got != {"has-flag.py"}:
            failures += 1
            print(f"  FAIL the predicate selected {got}, want just has-flag.py")
        else:
            print("  ok  neither a flagless script nor a dot-prefixed copy is invoked")

    # And a RED gate must fail the run, with its output shown. `run_all` is
    # driven for real with an injected runner -- the defect one directory over
    # was a self-test that reimplemented the code it was testing.
    class _Red:
        returncode = 1
        stdout = "FAIL some rule did not bite"
        stderr = ""

    class _Green:
        returncode = 0
        stdout = "every rule bites"
        stderr = ""

    import contextlib
    import io

    def quietly(runner) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return run_all([Path("a-gate.py")], run=runner)

    if quietly(lambda _: _Red()) == 0:
        failures += 1
        print("  FAIL a red gate did not fail the run")
    else:
        print("  ok  a red gate fails the run")
    if quietly(lambda _: _Green()) != 0:
        failures += 1
        print("  FAIL a green gate failed the run")
    else:
        print("  ok  a green gate passes")

    if failures:
        print(f"\ngate-self-tests --self-test: {failures} rule(s) did not behave")
        return 1
    print("\ngate-self-tests --self-test: every rule bites, and none cries wolf")
    return 0


def main(argv: list[str] | None = None, discover_fn=None) -> int:
    """`discover_fn` is injectable so the floor below can be DRIVEN. Its only
    assertion used to live inside `self_test`, where mutating a case cannot red
    anything -- so the production arm was deletable with the suite green."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="print what would run")
    ap.add_argument("--self-test", action="store_true", dest="self_test")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    found = (discover_fn or discover)()
    if args.list:
        for p in found:
            print(p.relative_to(REPO).as_posix())
        return 0
    if len(found) < MIN_EXPECTED:
        print(f"gate-self-tests: discovery found only {len(found)} gates (floor "
              f"{MIN_EXPECTED}); the predicate has probably stopped matching",
              file=sys.stderr)
        return 1
    return run_all(found)


if __name__ == "__main__":
    sys.exit(main())
