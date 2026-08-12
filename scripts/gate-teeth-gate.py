#!/usr/bin/env python
"""D-QC-GATE-TEETH — a gate wired into CI must be able to FAIL.

Why this exists
---------------
The QC sweep of 2026-07-31 found 63 named gate scripts with 18 wired, fixed that, and then
found the harder version of the same bug one layer down: *wired* is not *enforcing*. Two of
the scripts sitting in the "gate" pile could not return non-zero under any input —
`fe-door-scan.py` has no exit path at all, `timeout-discipline-lint.sh` ends in an
unconditional `exit 0` after printing its findings as advisory WARNs. Wiring those would have
read as +2 gates in the workflow file while enforcing exactly nothing, and a green CI would
have been evidence for a rule nothing checked.

That is the same shape as every other finding this cycle — a guarantee asserted somewhere
with nothing in code behind it — so it gets the same treatment: a rule, and a gate for it.

Two tiers, deliberately
-----------------------
HARD — every gate script CI invokes must contain a reachable non-zero exit. This is cheap,
mechanical, and green today. A new advisory-only "gate" reds here immediately.

RATCHET — a gate should also carry a PROOF that it goes red: a built-in selftest (the repo's
existing convention, e.g. `[emit-0013] SELFTEST PASS — flags a missing-0013 emit script,
passes one with 0013 (non-vacuous)`), or a test file that drives it. Most do not yet, so this
is a ratchet rather than a wall: the count may not grow, and lowering it is recorded. Making
this HARD today would mean ~40 findings and a red build with no path to green, which is how
gates get commented out instead of fixed.

    python scripts/gate-teeth-gate.py          # exit 1 on a toothless gate / ratchet drift
    python scripts/gate-teeth-gate.py --list   # the full inventory with each verdict
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

#: Gates CI runs that carry no red-ability proof yet. Ratcheted — see the module docstring.
#: 2026-07-31: 54 CI-invoked gates, 7 proven (4 selftest + 3 test files) ⇒ 47.
#: MEASURED, not estimated — the first value here was a guess of 43 and the gate rejected it
#: on its own first run, which is the behaviour you want from a ratchet.
#: 2026-08-09: 45 → 44, `scripts/test_db_safety_gate.py`. db-safety-gate had shipped two
#: 2026-08-12: 44 → 43, `glossary-events-ssot-gate.py` gained a --selftest. Its SSOT
#: moved from the producer's string literals to `contracts/events/_registry.yaml`
#: (T30/OD-1), which is a stronger question — so the proof was written with the
#: change rather than owed after it.
#: blind spots (an allowlist that omitted `tests/`, and a config check that required `TEST`
#: in the variable name) and both were found by hand; the proofs are now permanent.
NO_PROOF_BASELINE = 43

#: Scripts CI invokes that are NOT gates and are exempt from the HARD rule, with the reason.
NOT_A_GATE = {
    # Emits a report consumed by a later step / a human; failure is not its job.
    "runbook-index-generator.sh": "generator, not a checker",
}

#: A script whose only failure mode is an external tool's exit code under `set -e`.
#: Accepted as a failure path, but named here so it is a decision and not an accident.
DELEGATES_FAILURE = {
    "lint-contract.sh": "spectral-cli returns non-zero on an error-severity finding",
}

# A non-zero exit, in every form these scripts actually use. The first version of this
# regex looked for a LITERAL `return 1` / `^exit 1` and reported THIS FILE as toothless —
# it exits via `rc = 1 … return rc`, and shell gates commonly end `echo …; exit 1` or
# `exit "$violations"`. A detector that cannot see its own failure path is the same bug it
# was written to catch, so it is pinned by a test.
_PY_FAIL = re.compile(
    r"sys\.exit\(\s*(?!0\s*\))"          # sys.exit(<anything but literal 0>)
    r"|raise\s+SystemExit"
    r"|return\s+[1-9]\b"                  # return 1
    r"|^\s*(?:rc|code|status|exit_code|failures|violations)\s*=\s*[1-9]",
    re.M,
)
_SH_FAIL = re.compile(r"\bexit\s+(?!0\b)[\"'$\w]", re.M)
_SET_E = re.compile(r"^\s*set\s+-\w*e", re.M)
# MERGE 2026-08-02: `gate-wiring-gate.py` arrived from main carrying a real, working proof —
# a `self_test()` function behind a `--self-test` flag, verified red-able — and the previous
# pattern (`SELFTEST`) reported it as UNPROVEN purely because it spells the word with a
# separator. A detector that misses an existing proof is a false accusation, and the pressure
# it creates is to bolt on a second, redundant proof to satisfy a regex.
#
# But the separator must NOT simply be made optional. Measured: a bare `SELF[-_ ]?TEST` also
# certified `context-inspector-checklist-gate.py`, which has no self-test at all — it matched
# the words "for gate self-tests" inside an argparse `help=` string. `_executable_text` strips
# docstrings and comments, not string literals, so a MENTION would have counted as a PROOF.
# That is this file's own warning ("a gate must never be its own witness") re-committed one
# level out. So the separator spellings are accepted only in the two shapes that are proofs
# rather than prose: a `def self_test` and a `--self-test` CLI flag.
_SELFTEST = re.compile(r"SELFTEST|def\s+self[-_]?test\b|--self[-_]?test\b", re.I)
_PY_DOCSTRING = re.compile(r'("""|\'\'\')(?:.|\n)*?\1')
_HASH_COMMENT = re.compile(r"(?m)^\s*#.*$")


def _executable_text(path: Path, src: str) -> str:
    """`src` with docstrings and full-line comments removed.

    A gate must PRINT its selftest, not merely mention one. This file claimed a "built-in
    selftest" on its first run purely because the word appears in its own module docstring —
    the identical mistake `enforcement-claims-gate.py` made when it satisfied its own check by
    naming contracts in its docstring. A claim in prose is exactly what these gates exist to
    reject, so the search runs over what actually executes."""
    if path.suffix == ".py":
        src = _PY_DOCSTRING.sub("", src)
    return _HASH_COMMENT.sub("", src)

#: What makes a script an ENFORCEMENT gate rather than something else CI happens to run.
#: Without this the scan swept in 30 perf rigs (`perf/w1-capacity.sh`, `perf/soak.sh`, …),
#: which are load harnesses, not checkers — counting them as toothless gates would have
#: buried the two REAL findings under noise and made the baseline meaningless.
_IS_GATE = re.compile(r"(?:-|_)(?:lint|gate|validator|check|scan|enforcer|drift|guard)s?"
                      r"(?:-\w+)?\.(?:py|sh)$")


def ci_invoked_scripts() -> dict[str, list[str]]:
    """{script relpath: [workflow names]} for every enforcement gate a workflow runs."""
    out: dict[str, list[str]] = {}
    for wf in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        text = wf.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"scripts/([\w./-]+\.(?:py|sh))", text):
            rel = m.group(1)
            name = Path(rel).name
            # A pytest target under scripts/ is a TEST of a gate, not a gate.
            if name.startswith("test_") or "/tests/" in rel:
                continue
            if not _IS_GATE.search(name):
                continue
            out.setdefault(rel, [])
            if wf.name not in out[rel]:
                out[rel].append(wf.name)
    return out


def has_failure_path(path: Path) -> bool:
    src = path.read_text(encoding="utf-8", errors="ignore")
    if path.name in DELEGATES_FAILURE:
        return True
    if path.suffix == ".py":
        return bool(_PY_FAIL.search(src))
    if _SH_FAIL.search(src):
        return True
    # A shell gate whose real check is an embedded Python heredoc: under `set -e` the
    # heredoc's `sys.exit(1)` aborts the script, so the trailing `exit 0` is unreachable on
    # failure. `runbook-verification-lint.sh` is exactly this and was flagged toothless until
    # the shape was checked instead of assumed — measured: set -e → rc=1, without it → rc=0.
    return bool(_SET_E.search(src) and _PY_FAIL.search(src))


#: Gates whose red-ability is proved by `guard-redability-gate.py` — it injects the real
#: violation into real source and asserts the gate exits non-zero. That is a STRICTLY stronger
#: proof than a selftest, which exercises a synthetic input the author chose: the sweep's first
#: run found two gates that passed their own tests and stayed green when the actual violation
#: was put in front of them.
#:
#: Read off the AST, not the text, and this is not a nicety. The sweep's module docstring NAMES
#: `llm-budget-ssot-gate.py` while explaining what it found there — a text scan would certify a
#: gate on the strength of prose describing it, which is the exact false-proof this file
#: already caught twice (a `help=` string, a module docstring). The constants are read from the
#: `CASES` assignment alone, so only a gate the sweep actually EXECUTES counts.
def _redability_sweep_targets() -> frozenset[str]:
    sweep = ROOT / "scripts" / "guard-redability-gate.py"
    if not sweep.exists():
        return frozenset()
    try:
        tree = ast.parse(sweep.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return frozenset()
    cases = next((n for n in ast.walk(tree)
                  if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "CASES" for t in n.targets)), None)
    if cases is None:
        return frozenset()
    return frozenset(
        c.value for c in ast.walk(cases)
        if isinstance(c, ast.Constant) and isinstance(c.value, str)
        and c.value.startswith("scripts/")
    )


_REDABILITY_PROVEN = _redability_sweep_targets()


def teeth_proof(rel: str, path: Path) -> str | None:
    """How this gate proves it can go red, or None."""
    if rel in _REDABILITY_PROVEN:
        return "guard-redability-gate case (real violation, real source)"
    src = path.read_text(encoding="utf-8", errors="ignore")
    # This file is the ANALYZER: the word "selftest" is its vocabulary, so it matched its own
    # `return "built-in selftest"` string and certified itself. Third instance of that shape in
    # one cycle (enforcement-claims-gate named contracts in its docstring; the S12 gate greened
    # on its own motivating example). A gate must never be its own witness.
    if path.name != Path(__file__).name and _SELFTEST.search(_executable_text(path, src)):
        return "built-in selftest"
    stem = path.stem.replace("-", "_")
    for cand in (
        ROOT / "scripts" / f"test_{stem}.py",
        path.parent / f"test_{path.stem}.py",
        ROOT / "scripts" / "tests" / f"test_{stem}.py",
    ):
        if cand.exists():
            return f"test file {cand.relative_to(ROOT).as_posix()}"
    return None


def main() -> int:
    want_list = "--list" in sys.argv
    invoked = ci_invoked_scripts()

    missing_file: list[str] = []
    toothless: list[str] = []
    unproven: list[str] = []
    rows: list[tuple[str, str, str]] = []

    for rel in sorted(invoked):
        path = ROOT / "scripts" / rel
        if not path.exists():
            missing_file.append(rel)
            continue
        name = path.name
        if name in NOT_A_GATE:
            rows.append((rel, "exempt", NOT_A_GATE[name]))
            continue
        fails = has_failure_path(path)
        proof = teeth_proof(rel, path)
        if not fails:
            toothless.append(rel)
        if proof is None:
            unproven.append(rel)
        rows.append((rel, "OK" if fails else "TOOTHLESS", proof or "— no red-ability proof"))

    if want_list:
        print(f"{len(invoked)} gate script(s) invoked by CI\n")
        for rel, verdict, note in rows:
            print(f"  [{verdict:9}] {rel:46} {note}")
        return 0

    rc = 0
    if missing_file:
        print("FAIL — CI invokes a script that does not exist:")
        for r in missing_file:
            print(f"   {r}   (workflows: {', '.join(invoked[r])})")
        rc = 1

    if toothless:
        print("FAIL — gate wired into CI with NO reachable non-zero exit "
              "(it can never report a violation):")
        for r in toothless:
            print(f"   scripts/{r}   (workflows: {', '.join(invoked[r])})")
        print("\n   Give it an `exit 1` on findings, or move it out of the gate steps and")
        print("   record it in NOT_A_GATE with the reason.")
        rc = 1

    if len(unproven) != NO_PROOF_BASELINE:
        verb = "grew to" if len(unproven) > NO_PROOF_BASELINE else "dropped to"
        print(f"\n{'FAIL' if len(unproven) > NO_PROOF_BASELINE else 'NOTE'} — gates without a "
              f"red-ability proof {verb} {len(unproven)} (baseline {NO_PROOF_BASELINE}).")
        if len(unproven) > NO_PROOF_BASELINE:
            new = [r for r in unproven]
            print("   A gate is not proven by passing; it is proven by going red on a bad input.")
            print("   Add a selftest block or scripts/test_<name>.py for the new gate(s):")
            for r in new[-8:]:
                print(f"     scripts/{r}")
        else:
            print(f"   Progress — lower NO_PROOF_BASELINE to {len(unproven)} in {Path(__file__).name}.")
        rc = 1

    if rc == 0:
        proven = len(invoked) - len(unproven)
        print(f"gate-teeth-gate: PASS — {len(invoked)} CI-invoked gate(s), every one able to "
              f"return non-zero.")
        print(f"  {proven} carry a red-ability proof; {len(unproven)} held at baseline.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
