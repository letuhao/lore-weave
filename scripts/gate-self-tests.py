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
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SELF = Path(__file__).name

# **REFERENCED BY CODE, not mentioned in prose.**
#
# The first predicate was `"--self-test" in src`, so a script whose only
# relationship to the flag was a sentence in a comment was invoked, exited 0, and
# counted as a green self-test. Measured on this tree, that was not hypothetical:
# `gate-teeth-gate.py` names the flag in two comments -- including one saying a
# gate should have *"a `def self_test` and a `--self-test` CLI flag"* -- has
# neither, and was being counted green. The inverse is live too: a script that
# mentions the flag and parses arguments strictly exits 2 and blocks the commit,
# which is cry-wolf, the severe direction.
#
# The obvious tightening -- require an argparse registration -- was measured and
# is WRONG: it drops `gatelib.py`, which has a real self-test dispatched through
# `sys.argv`. A predicate keyed on one dispatch idiom is an enumerated list
# wearing a regex.
#
# So: the flag must appear in the file with comments and docstrings REMOVED.
# This repo already has that rule and learned it the hard way -- prose that
# happens to live in a source file is still prose, which is what certified three
# prose-only deferrals as covered until the stripper was fixed.
FLAG = "--self-test"

# ...and the SPELLING is the same defect one level down (found 2026-08-07 while
# wiring gate #48). The predicate above was fixed to read CODE rather than PROSE,
# which was the right fix for the problem it had -- and it still keyed on ONE
# spelling. Measured on this tree: **four** gates dispatch on `--selftest` with
# no hyphen (`amendment-rot-gate`, `design-lint`, `phase0-reconcile-gate`,
# `tier-capability-gate`), so this driver had never invoked one of their cases,
# while printing a count that reads as full coverage. Discovery went 22 -> 26.
#
# Three of the four happen to run their self-test inline in normal mode, so the
# damage was smaller than it looks -- but that is luck, not a mechanism, and it
# is invisible from here either way. The comment above says a predicate keyed on
# one dispatch idiom is "an enumerated list wearing a regex"; two hard-coded
# spellings would be that list, one entry longer. So the match is on the SHAPE.
#
# `run_all` then invokes each script with the spelling THAT SCRIPT advertises.
# Passing `--self-test` to a gate that only knows `--selftest` runs it in NORMAL
# mode and scores whatever the full scan returned as a self-test verdict --
# measured on `tier-capability-gate`, which exits 0 either way. That false green
# is the exact failure this driver exists to prevent.
FLAG_RE = re.compile(r"--self[-_]?test\b")


def advertised_flag(src: str) -> str | None:
    """The self-test flag THIS script dispatches on, or `None`."""
    m = FLAG_RE.search(_code_only(src))
    return m.group(0) if m else None


def _code_only(src: str) -> str:
    """`src` with comments and docstrings blanked. Offsets are not preserved.

    On a syntax error it returns `src` UNCHANGED -- deliberately the permissive
    direction. Wrongly INCLUDING a script costs one wasted invocation; wrongly
    excluding one silently drops a gate from every commit, which is the failure
    this whole file exists to prevent.
    """
    import ast
    import io as _io
    import tokenize

    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src

    lines = src.split("\n")
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        if not (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            continue
        doc = node.body[0].value
        for i in range(doc.lineno - 1, (doc.end_lineno or doc.lineno)):
            if 0 <= i < len(lines):
                lines[i] = ""
    stripped = "\n".join(lines)

    try:
        out, last = [], (1, 0)
        for tok in tokenize.generate_tokens(_io.StringIO(stripped).readline):
            if tok.type == tokenize.COMMENT:
                continue
            out.append(tok.string)
        return " ".join(out)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return stripped

# A hanging self-test must not wedge a commit or burn the CI job to its cap.
CHILD_TIMEOUT_S = 300

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
    # **RECURSIVE**, because the hook's trigger is: `^scripts/.*\.py$` matches
    # `scripts/perf/slo_assert.py`, which has a real `--self-test` -- so staging
    # it fired a driver that then did not look at it. The enumerated-list defect
    # one directory level down.
    for p in sorted(root.rglob("*.py")):
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
            if advertised_flag(p.read_text(encoding="utf-8", errors="replace")):
                found.append(p)
        except OSError:
            continue
    return found


def flag_for(p: Path) -> str:
    """The spelling `p` dispatches on. Falls back to the canonical one."""
    try:
        return advertised_flag(p.read_text(encoding="utf-8", errors="replace")) or FLAG
    except OSError:
        return FLAG


def argv_for(p: Path) -> list[str]:
    """The exact command this driver runs for `p`.

    Extracted so the self-test can assert on **what is actually invoked** rather
    than on `flag_for` in isolation. The first version of that case called
    `flag_for` directly, so reverting `run_all` to a hardcoded `--self-test`
    left it GREEN — `NV-3` ("the scope never reaches it") inside the case
    written to prevent exactly this. Caught by biting it.
    """
    return [sys.executable, str(p), flag_for(p)]


def run_all(scripts: list[Path], run=None) -> int:
    runner = run or (lambda p, argv: subprocess.run(
        argv, cwd=REPO, capture_output=True, text=True, timeout=CHILD_TIMEOUT_S))
    failed = []
    for p in scripts:
        t0 = time.time()
        # **A timeout is a FINDING about that gate, not the end of the run.**
        # The timeout was configured and never caught, so one hanging gate
        # aborted THIS driver -- the one the pre-commit hook runs across 47
        # services -- with a raw traceback, and the gates after it were reported
        # by nothing at all. The mutation harness carries this guard and says so
        # in a comment about itself; the same rule was never written here.
        try:
            out = runner(p, argv_for(p))
        except subprocess.TimeoutExpired:
            ms = int((time.time() - t0) * 1000)
            print(f"  SLOW {p.name:<44} {ms:>6}ms -> no verdict in {CHILD_TIMEOUT_S}s")
            failed.append(p.name)
            continue
        ms = int((time.time() - t0) * 1000)
        ok = out.returncode == 0
        print(f"  {'ok  ' if ok else 'FAIL'} {p.name:<44} {ms:>6}ms")
        if not ok:
            failed.append(p.name)
            # **The reason is PRINTED.** Swallowing it leaves a contributor with
            # a gate name and no way to see what failed; the figures gate has a
            # case for exactly this and this side had none, so suppressing the
            # child's output here survived every mutation.
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
    # defect. Known ones asserted BY NAME, so a predicate that narrows is caught
    # even while the floor still passes.
    #
    # The last four are the `--selftest` spelling. They are named separately
    # because the floor did NOT catch them: this driver ran 22 gates and reported
    # "22 gate self-tests green" while four gates' cases had never been invoked
    # by it, and 22 is comfortably above a floor of 10. **A count that is right
    # about what it did and silent about what it missed is the shape this whole
    # file exists to refuse**, and it had it.
    for required in ("citation-gate.py", "actor-hub-figures-gate.py",
                     "hashed-substrate-float-gate.py", "deferral-gate.py",
                     "amendment-rot-gate.py", "design-lint.py",
                     "phase0-reconcile-gate.py", "tier-capability-gate.py"):
        if required not in names:
            failures += 1
            print(f"  FAIL {required} advertises a self-test flag and was not discovered")

    # ...and each must be invoked with the spelling IT dispatches on. Handing
    # `--self-test` to a gate that only knows `--selftest` runs it in NORMAL mode
    # and scores the full scan as a self-test verdict — measured on
    # `tier-capability-gate`, which exits 0 either way, so the false green is
    # completely silent.
    #
    # **This case drives `run_all` and records the argv it BUILDS.** Asking
    # `flag_for` directly was the first version, and biting it showed the case
    # was vacuous: reverting `run_all` to a hardcoded `--self-test` left it
    # green, because nothing it looked at was on the path being reverted. That
    # is `NV-3` — the scope never reaches the subject — inside the case written
    # to prevent a false green. The subject is what gets EXECUTED, so the case
    # has to go through the thing that executes it.
    import contextlib as _cl
    import io as _io2

    class _Ok:
        returncode, stdout, stderr = 0, "", ""

    seen: list[list[str]] = []
    with _cl.redirect_stdout(_io2.StringIO()), _cl.redirect_stderr(_io2.StringIO()):
        run_all(found, run=lambda _p, argv: seen.append(argv) or _Ok())

    if len(seen) != len(found):
        failures += 1
        print(f"  FAIL run_all invoked {len(seen)} of {len(found)} discovered gates")
    else:
        wrong = [(Path(a[1]).name, a[-1], flag_for(Path(a[1]))) for a in seen
                 if a[-1] != flag_for(Path(a[1]))]
        hyphenless = [a for a in seen if a[-1] == "--selftest"]
        if wrong:
            failures += 1
            print(f"  FAIL run_all passed the wrong flag to {len(wrong)} gate(s): {wrong[:3]}")
        elif not hyphenless:
            failures += 1
            print("  FAIL no discovered gate dispatches on `--selftest`, so this case has no "
                  "subject — it would pass whether or not the flag were routed at all")
        else:
            print(f"  ok  run_all invokes each gate with ITS OWN flag spelling "
                  f"({len(hyphenless)} hyphenless, {len(seen) - len(hyphenless)} canonical)")

    # `--self-test` must ROUTE to the cases. Deleting that branch left this
    # file's own self-test green, because the fallthrough ran every other gate.
    import argparse as _ap

    def _parsed(argv):
        q = _ap.ArgumentParser()
        q.add_argument("--list", action="store_true")
        q.add_argument("--self-test", action="store_true", dest="self_test")
        return q.parse_args(argv)

    for argv, want in ((["--self-test"], "self-test"), (["--list"], "list"), ([], "run")):
        got = _route(_parsed(argv))
        if got != want:
            failures += 1
            print(f"  FAIL {argv} routes to {got!r}, want {want!r}")
    if all(_route(_parsed(a)) == w for a, w in
           ((["--self-test"], "self-test"), (["--list"], "list"), ([], "run"))):
        print("  ok  every flag routes to its own mode")

    # A file WITHOUT the flag must not be picked up, or every script in the
    # directory would be invoked with an argument it does not understand.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "has-flag.py").write_text('ap.add_argument("--self-test")', encoding="utf-8")
        (tmp / "no-flag.py").write_text("print(1)", encoding="utf-8")
        # **MENTIONING the flag is not having one.** A script whose only
        # relationship to `--self-test` is a sentence in its docstring was
        # invoked, exited 0, and counted as a green self-test.
        (tmp / "mentions-only.py").write_text(
            '"""Run me with --self-test one day."""\nprint(1)\n', encoding="utf-8")
        # ...in a COMMENT too, which is how a real gate in this tree was being
        # counted green while having no self-test at all.
        (tmp / "comment-only.py").write_text(
            "# a gate should have a --self-test flag\nprint(1)\n", encoding="utf-8")
        # ...and a REAL self-test dispatched WITHOUT argparse must still count:
        # requiring `add_argument` dropped `gatelib.py`, a miss introduced by the
        # fix for a false green.
        (tmp / "argv-dispatch.py").write_text(
            'import sys\nif "--self-test" in sys.argv:\n    pass\n', encoding="utf-8")
        # ...and discovery is RECURSIVE, matching the hook trigger.
        (tmp / "perf").mkdir()
        (tmp / "perf" / "nested.py").write_text(
            'ap.add_argument("--self-test")', encoding="utf-8")
        # A scratch copy of a gate, which carries the flag and must still be
        # skipped — `gate-bite-harness` writes exactly this shape beside the
        # original while it mutates it.
        (tmp / ".bite-has-flag.py").write_text('ap.add_argument("--self-test")', encoding="utf-8")
        got = {p.name for p in discover(tmp)}
        want = {"has-flag.py", "nested.py", "argv-dispatch.py"}
        if got != want:
            failures += 1
            print(f"  FAIL the predicate selected {got}, want {want}")
        else:
            print("  ok  registration is required, mentioning is not enough, "
                  "subdirectories are covered")

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

    if quietly(lambda _p, _argv: _Red()) == 0:
        failures += 1
        print("  FAIL a red gate did not fail the run")
    else:
        print("  ok  a red gate fails the run")
    if quietly(lambda _p, _argv: _Green()) != 0:
        failures += 1
        print("  FAIL a green gate failed the run")
    else:
        print("  ok  a green gate passes")

    # **A hanging gate is a FINDING, not the end of the run.** The timeout was
    # configured and never caught here, so one gate that never returns aborted
    # THIS driver -- the one the pre-commit hook runs -- with a raw traceback,
    # and the gates after it were reported by nothing. The mutation harness
    # carries the guard and its comment describes this exact failure; the rule
    # was simply never written on this side.
    def _hangs(_p, _argv):
        raise subprocess.TimeoutExpired("child", CHILD_TIMEOUT_S)

    printed = io.StringIO()
    try:
        with contextlib.redirect_stdout(printed), contextlib.redirect_stderr(io.StringIO()):
            rc = run_all([Path("a-gate.py"), Path("b-gate.py")], run=_hangs)
    except subprocess.TimeoutExpired:
        failures += 1
        rc, printed = None, io.StringIO()
        print("  FAIL a hanging gate aborted the whole run")
    if rc == 0:
        failures += 1
        print("  FAIL a hanging gate did not fail the run")
    elif rc is not None:
        seen = printed.getvalue().count("no verdict")
        if seen != 2:
            failures += 1
            print(f"  FAIL {seen} gate(s) reported after a hang, want 2")
        else:
            print("  ok  a hanging gate is a finding and the run continues past it")

    # ...and the failing child's OUTPUT is printed. Swallowing it leaves a
    # contributor with a gate name and no way to see what failed; the figures
    # gate has a case for exactly this and this side had none.
    reason = io.StringIO()
    with contextlib.redirect_stdout(reason), contextlib.redirect_stderr(io.StringIO()):
        run_all([Path("a-gate.py")], run=lambda _p, _argv: _Red())
    if _Red.stdout not in reason.getvalue():
        failures += 1
        print("  FAIL a red gate's reason was not printed")
    else:
        print("  ok  a red gate's reason is printed, not just its name")

    if failures:
        print(f"\ngate-self-tests --self-test: {failures} rule(s) did not behave")
        return 1
    print("\ngate-self-tests --self-test: every rule bites, and none cries wolf")
    return 0


def _route(args) -> str:
    """Which mode `main` will take. Extracted so it can be ASSERTED.

    Deleting `if args.self_test: return self_test()` left this file's own
    self-test GREEN: the fallthrough ran every discovered gate, all of which
    passed, so the run exited 0. The routing could not be tested in place --
    calling `main(["--self-test"])` from inside `self_test` recurses -- so the
    decision moved out to where a case can reach it.
    """
    if args.self_test:
        return "self-test"
    if args.list:
        return "list"
    return "run"


def _self_test_guarded(fn, name: str) -> int:
    """Run a self-test, reporting an ESCAPING EXCEPTION as a CRASH.

    **A self-test that dies has failed, and it must say so in its own
    vocabulary.** Four rules in this repo read RED for eighteen rounds purely
    because deleting them made the child raise: the harness saw a non-zero exit
    and called it a bite, while not one case had disagreed. `run_rust`'s
    compile-failure guard was written for exactly this on the Rust side; the
    Python side had nothing.
    """
    try:
        return fn()
    except BaseException as e:  # noqa: BLE001 - a crash IS the finding here
        # **`CRASH`, not `FAIL`, and the difference is load-bearing.** The first
        # version printed `FAIL`, which is exactly the token the mutation
        # harness counts as a case disagreeing -- so a child that DIED read as a
        # rule that BIT, which is the artifact the failing-case rule was written
        # in the same commit to end. Two decisions, each correct alone, the
        # later one defeating the earlier.
        #
        # The exit code is still non-zero, so a human and `gate-self-tests`
        # both see a red gate; only the harness's "did a case disagree"
        # question gets the honest answer, which is no.
        print(f"  CRASH {name} raised before finishing: {type(e).__name__}: {e}")
        print(f"{chr(10)}{name}: 1 rule(s) did not behave")
        return 1


def main(argv: list[str] | None = None, discover_fn=None) -> int:
    """`discover_fn` is injectable so the floor below can be DRIVEN. Its only
    assertion used to live inside `self_test`, where mutating a case cannot red
    anything -- so the production arm was deletable with the suite green."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="print what would run")
    ap.add_argument("--self-test", action="store_true", dest="self_test")
    args = ap.parse_args(argv)

    mode = _route(args)
    if mode == "self-test":
        return _self_test_guarded(self_test, "gate-self-tests --self-test")

    found = (discover_fn or discover)()
    if mode == "list":
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
