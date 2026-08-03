#!/usr/bin/env python3
"""Mutate each gate's production rules and require its `--self-test` to go RED.

WHY THIS EXISTS
---------------
A self-test's own claim — *"every rule bites"* — is a claim like any other, and
the only proof is a mutation that turns it red. `D-376` recorded twelve such
mutations as *"verified by a script that runs them"*. **The script existed only
in a session scratchpad.** A cold-start review looked for it, did not find it,
and pointed out that `D-380`'s own thesis — a check nobody runs is not a check —
applies to the artefact certifying `D-376`.

So it lives here, and it runs a mutation per PRODUCTION RULE, not per file.

IT NEVER TOUCHES THE REAL FILE
------------------------------
An earlier hand-run of this idea edited the gate in place and was killed
mid-run, leaving two `if False:` mutations in the working tree — caught by
running the self-test before committing, which is luck, not a mechanism. So the
harness mutates a COPY placed beside the original (same directory, so `REPO`
still resolves) and deletes it in a `finally`. The original is opened read-only.

    python scripts/gate-bite-harness.py             # every gate with a table
    python scripts/gate-bite-harness.py --gate citation-gate
    python scripts/gate-bite-harness.py --self-test
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"

# gate -> [(label, find, replace)]. `find` must occur EXACTLY once: an anchor
# that has drifted is reported as a failure, not silently skipped, or the table
# rots into a list of no-ops that all pass.
MUTATIONS: dict[str, list[tuple[str, str, str]]] = {
    "actor-hub-figures-gate": [
        ("a stale figure is never reported",
         "                elif int(claimed) != want:", "                elif False:"),
        ("a moved anchor downgraded to a note",
         '            problems.append(\n                f"{doc}: the marker',
         '            notes.append(\n                f"{doc}: the marker'),
        ("the coverage arm disabled",
         "        if pattern not in seen:", "        if False:"),
        ("the unmeasurable branch skipped",
         "                if isinstance(want, dict):", "                if False:"),
        ("the live-range escape rule disabled",
         "    problems += _escaped_live_range(m, scopes=scopes, read=read)",
         "    problems += []"),
        ("the escape rule stops excluding the governed block",
         "            if any(mo.group(0) in b for b in blocks):", "            if False:"),
        ("the 6-BUILD scope row deleted",
         '    (RUN_STATE, "### 6-BUILD", "| # | Slice |"),', ""),
        ("the _index.md scope row deleted",
         '    (INDEX, "# Actor Hub", "\\n## Read this to REUSE"),', ""),
        ("the red-build guard removed",
         '    if "test result: FAILED" in out.stdout or out.returncode != 0:',
         "    if False:"),
        ("the cargo-absent guard removed",
         '    if (which or shutil.which)("cargo") is None:', "    if False:"),
        ("the empty-id guard removed", "    if not ids:", "    if False:"),
        ("the hook scan counts commented invocations",
         '    body = "\\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))',
         "    body = text"),
        ("main() stops failing",
         '    if problems:\n        print(f"\\nactor-hub-figures: {len(problems)} disagreement(s)',
         '    if False:\n        print(f"\\nactor-hub-figures: {len(problems)} disagreement(s)'),
        ("--print starts failing", "    if args.print_only:\n        return 0",
         "    if False:\n        return 0"),
        ("fence/comment/quote blanking removed (cry wolf)",
         "        block = _claimable(block)", "        block = block"),
        ("fences toggled instead of paired (the tail goes blind)",
         "    for a, b in zip(marks[::2], marks[1::2]):\n        fenced.update(range(a, b + 1))",
         "    for a in marks:\n        fenced.update(range(a, len(lines)) if marks.index(a) % 2 == 0 else [])"),
        ("the multi-line comment state dropped",
         '        if stripped.startswith("<!--") and "-->" not in line:',
         '        if False:'),
        ("the inline comment span not blanked",
         '        line = COMMENT_RE.sub(lambda mo: " " * len(mo.group(0)), line)',
         "        line = line"),
        ("the escape scan stops blanking fences (cry wolf on an example)",
         "        text = _claimable(text, quotes=False)", "        text = text"),
        ("the escape scan starts exempting quotations",
         "        text = _claimable(text, quotes=False)", "        text = _claimable(text)"),
        ("the substrate contract row deleted",
         '    (r"and\\s*\\n?>?\\s*\\*\\*(\\d+)\\*\\*\\s*\\n?>?\\s*lines", "contract_substrate_lines", "the substrate contract\'s lines"),',
         ""),
    ],
    "gate-self-tests": [
        ("a red gate no longer fails the run", "    if failed:", "    if False:"),
        ("discovery stops excluding this driver and scratch copies",
         '        if p.name == SELF or p.name.startswith("."):\n            continue',
         "        if False:\n            continue"),
        ("the discovery predicate matches everything",
         '            if "--self-test" in p.read_text(encoding="utf-8", errors="replace"):',
         "            if True:"),
        # Targeted at `main`'s floor, not at the assertion inside `self_test`.
        # Mutating a CASE cannot red the suite it belongs to, so the first
        # version of this row surveyed nothing and reported GREEN — which is how
        # the production floor turned out to have no case at all.
        ("the discovery floor removed from main()",
         '    if len(found) < MIN_EXPECTED:\n        print(f"gate-self-tests: discovery found only',
         '    if False:\n        print(f"gate-self-tests: discovery found only'),
        ("the discovery injection ignored", "    found = (discover_fn or discover)()",
         "    found = discover()"),
    ],
    "citation-gate": [
        ("the pragma stops exempting", "        if _pragma_covers(lines, i):", "        if False:"),
        ("URLs are no longer blanked",
         "        scan_line = URL_RE.sub(lambda m: \" \" * len(m.group(0)), line)",
         "        scan_line = line"),
        ("a no-line-number citation is checked again (the cry-wolf revert)",
         "            # A dead branch is not a record of a decision; this comment is.\n"
         "            if start is None:",
         "            # A dead branch is not a record of a decision; this comment is.\n"
         "            if False:"),
    ],
}


def _mutate_and_run(gate: str, find: str, repl: str, run=None) -> tuple[bool, str]:
    """(went_red, note). The ORIGINAL is opened read-only; a copy is mutated."""
    src = SCRIPTS / f"{gate}.py"
    text = src.read_text(encoding="utf-8")
    if text.count(find) != 1:
        return False, f"anchor occurs {text.count(find)}x — the table has drifted"
    # Beside the original so `REPO = Path(__file__).parent.parent` still resolves.
    copy = SCRIPTS / f".bite-{gate}.py"
    try:
        copy.write_text(text.replace(find, repl, 1), encoding="utf-8")
        runner = run or (lambda p: subprocess.run(
            [sys.executable, str(p), "--self-test"], cwd=REPO,
            capture_output=True, text=True))
        out = runner(copy)
    finally:
        copy.unlink(missing_ok=True)
    if out.returncode != 0:
        return True, ""
    return False, "self-test stayed GREEN"


def run_gate(gate: str, run=None, only: str | None = None) -> int:
    rows = [r for r in MUTATIONS[gate] if only is None or only.lower() in r[0].lower()]
    print(f"\n{gate}" + (f"  ({len(rows)}/{len(MUTATIONS[gate])} matching {only!r})" if only else ""))
    green = 0
    for label, find, repl in rows:
        red, note = _mutate_and_run(gate, find, repl, run=run)
        print(f"  {'RED ' if red else 'GREEN'}  {label}{'  <- ' + note if note else ''}")
        green += 0 if red else 1
    return green


def self_test() -> int:
    """The harness's own rules. It cannot verify itself by mutation — that is
    the regress this file stops at — so its cases are direct."""
    failures = 0

    # Every table entry's anchor must still occur exactly once. A drifted anchor
    # silently mutates nothing, and a table of no-ops passes every time.
    for gate, rows in MUTATIONS.items():
        text = (SCRIPTS / f"{gate}.py").read_text(encoding="utf-8")
        for label, find, _ in rows:
            if text.count(find) != 1:
                failures += 1
                print(f"  FAIL {gate}: anchor for '{label}' occurs {text.count(find)}x")
    if not failures:
        total = sum(len(v) for v in MUTATIONS.values())
        print(f"  ok  all {total} mutation anchors resolve exactly once")

    # A mutation that leaves the self-test GREEN must be reported as GREEN, and
    # one that reddens it as RED. Driven through the real `_mutate_and_run`.
    class _R:
        def __init__(self, rc):
            self.returncode, self.stdout, self.stderr = rc, "", ""

    gate, (_, find, repl) = "citation-gate", MUTATIONS["citation-gate"][0]
    red, _ = _mutate_and_run(gate, find, repl, run=lambda _: _R(1))
    if not red:
        failures += 1
        print("  FAIL a reddened self-test was not reported as RED")
    else:
        print("  ok  a reddened self-test is reported RED")
    red, note = _mutate_and_run(gate, find, repl, run=lambda _: _R(0))
    if red or "GREEN" not in note:
        failures += 1
        print("  FAIL a surviving mutation was not reported as GREEN")
    else:
        print("  ok  a surviving mutation is reported GREEN")

    # ...and the copy must be gone whatever happened, or a killed run leaves a
    # mutated file on disk — which is the incident this harness is shaped by.
    def _boom(_):
        raise RuntimeError("killed mid-run")

    try:
        _mutate_and_run(gate, find, repl, run=_boom)
    except RuntimeError:
        pass
    leftover = list(SCRIPTS.glob(".bite-*.py"))
    if leftover:
        failures += 1
        print(f"  FAIL a crashed run left {[p.name for p in leftover]} on disk")
    else:
        print("  ok  a crashed run leaves no mutated copy behind")

    # The anchor guard must FIRE on an anchor that does not exist -- otherwise
    # the drift check above is the only thing standing, and it lives here too.
    red, note = _mutate_and_run(gate, "@@ NOT IN ANY FILE @@", "x")
    if red or "drifted" not in note:
        failures += 1
        print(f"  FAIL a missing anchor was not reported as drift: {note!r}")
    else:
        print("  ok  a missing anchor is reported as drift, not skipped")

    if failures:
        print(f"\ngate-bite-harness --self-test: {failures} rule(s) did not behave")
        return 1
    print("\ngate-bite-harness --self-test: every rule bites, and none cries wolf")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate", help="one gate name (default: all with a table)")
    ap.add_argument("--only", help="substring filter on the mutation label")
    ap.add_argument("--self-test", action="store_true", dest="self_test")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    gates = [args.gate] if args.gate else sorted(MUTATIONS)
    unknown = [g for g in gates if g not in MUTATIONS]
    if unknown:
        print(f"gate-bite-harness: no mutation table for {unknown}", file=sys.stderr)
        return 2
    survivors = sum(run_gate(g, only=args.only) for g in gates)
    total = sum(len([r for r in MUTATIONS[g]
                     if args.only is None or args.only.lower() in r[0].lower()])
                for g in gates)
    if not total:
        print(f"gate-bite-harness: no mutation matched {args.only!r} — a filter that "
              "selects nothing must not report success", file=sys.stderr)
        return 2
    if survivors:
        print(f"\ngate-bite-harness: {survivors}/{total} mutations SURVIVED — those "
              "rules have no case and can be deleted with the suite green",
              file=sys.stderr)
        return 1
    print(f"\ngate-bite-harness: all {total} mutations reddened their self-test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
