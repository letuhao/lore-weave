#!/usr/bin/env python3
"""gate-number-visibility-gate.py — a threshold nobody sees on a green run drifts invisibly.

T56(b), from spec §8.4's rot table: *"every gate prints its number unconditionally (the
`port-adoption-gate` floor bug — generalise it)."*

A ratchet gate carries a number: a ceiling that may only fall, a floor that may only rise, a
baseline held at zero. The number is the whole mechanism — it is what makes a slow regression
visible commit by commit instead of being discovered in an audit. **A gate that prints its
number only when it FAILS has thrown that away**: every green run says nothing, so nobody sees
the value until the day it breaks, and by then the drift is history rather than a diff.

Measured 2026-08-22: 8 gates carry an integer threshold and **2 never printed it** —
`file-ceiling-gate`'s `CEILING = 400` and `plan-row-honesty-gate`'s `MIN_DONE` / `MAX_OWED`,
the latter two tuned from observed data and therefore exactly the kind of number that stops
catching anything if it drifts unwatched.

── HOW IT CHECKS ────────────────────────────────────────────────────────────────────────────
Empirically, not by reading the source. It **runs each gate and looks for the number in the
output**, because that is the property that actually matters: someone reading CI sees it. A
static check for "the constant appears inside a `print(`" would pass on a print that only runs
on the failure path — which is the exact defect.

Both halves are DERIVED: the thresholds by AST (a module-level `int` whose name is threshold
vocabulary), the visibility by execution.

⚠️ **WHAT THIS GATE CANNOT SEE, measured rather than assumed.** A ratchet normally sits AT its
threshold — that is what "exactly at the ceiling" means — so the measured COUNT and the
THRESHOLD are the same digits. When a gate prints the count and not the threshold, this check
cannot tell the difference. Bite 2 proved it: deleting `/{MAX_PINNED_SESSIONS}` from
`port-adoption-gate`'s line still leaves a standalone `9`, and this gate stays green.

So the property enforced is the weaker, honest one: **the number reaches the output at all.**
That is exactly the `file-ceiling-gate` shape it was written from — count 114, ceiling 400,
nothing in common — and it is not the stronger "the threshold is labelled as such". Tightening
would mean imposing one phrasing on eight gates that each say it differently, which trades a
real check for a lint. Stated here so nobody reads the gate's name as the stronger claim.

Usage:
  python scripts/gate-number-visibility-gate.py             # run the threshold-carrying gates
  python scripts/gate-number-visibility-gate.py --selftest  # prove it can go red
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")

#: Names that mean "this is a ratchet". Deliberately a vocabulary rather than a list of
#: constants: a new gate naming its number `MAX_FOO` is covered the day it is written, which
#: is the property T55a's derivation and T56a's both turn on.
THRESHOLD_NAME = re.compile(r"^(MAX_|MIN_)|FLOOR|CEILING|_CAP$|BASELINE")

#: Gates that need an argument to run at all. The value is the argv to give them — NOT an
#: exemption: they are still executed and still checked.
GATE_ARGS: dict[str, list[str]] = {
    "plan-row-honesty-gate.py": ["docs/plans/2026-08-09-knowledge-architecture-refactor.md"],
}

#: Thresholds that are deliberately NOT printed, with the reason. Same two-arm shape as
#: `adapter-selectability-gate`: "deliberately silent" and "nobody noticed" must not look
#: alike. Empty at the time of writing, and that is the point — every threshold in the repo
#: is currently visible on a green run.
SILENT_BY_DESIGN: dict[str, str] = {}

_TIMEOUT_S = 180


def thresholds(path: str) -> dict[str, int]:
    """Module-level integer constants whose NAME says they are a ratchet."""
    try:
        tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
    except (OSError, SyntaxError):
        return {}
    out: dict[str, int] = {}
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            continue
        name = node.targets[0].id
        if not THRESHOLD_NAME.search(name):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int) \
                and not isinstance(node.value.value, bool):
            out[name] = node.value.value
    return out


def gate_scripts() -> list[str]:
    if not os.path.isdir(SCRIPTS):
        return []
    return [f for f in sorted(os.listdir(SCRIPTS))
            if f.endswith(".py") and "gate" in f and f != os.path.basename(__file__)]


def run_gate(fname: str) -> str:
    """The gate's combined output. A crash is output too — it still either shows the number
    or does not, and a gate that cannot run is a separate problem this one must not mask."""
    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, fname)] + GATE_ARGS.get(fname, []),
            capture_output=True, text=True, timeout=_TIMEOUT_S, cwd=REPO_ROOT,
        )
    except subprocess.TimeoutExpired:
        return ""
    return (proc.stdout or "") + (proc.stderr or "")


def invisible(output: str, values: dict[str, int]) -> list[str]:
    """Thresholds whose VALUE does not appear in `output` as a standalone number.

    ⚠️ Substring matching is not good enough, and the selftest caught it: `str(400) in
    "scanned 1400 files"` is True, so a gate would pass because an unrelated count happened
    to contain its threshold's digits. That is a criterion that passes for the wrong reason —
    the thing this whole row is about. Digit boundaries, not `in`.
    """
    missing = []
    for name, value in values.items():
        if not re.search(r"(?<![0-9])" + re.escape(str(value)) + r"(?![0-9])", output):
            missing.append(f"{name} = {value}")
    return missing


def selftest() -> int:
    ok = True
    print("gate-number-visibility-gate - selftest (offline)")

    def expect(label: str, got, want) -> None:
        nonlocal ok
        good = got == want
        ok = ok and good
        print(f"  {'PASS' if good else 'FAIL'}  {label}: expected {want!r}, got {got!r}")

    src = (
        "MAX_THINGS = 7\n"
        "MIN_ADOPTERS = 2\n"
        "SOME_CEILING = 9\n"
        "UNRELATED = 5\n"
        "NAME = 'MAX_THINGS'\n"
        "ENABLED = True\n"
    )
    tmp = os.path.join(SCRIPTS, "_visibility_probe_gate.py")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(src)
    try:
        got = thresholds(tmp)
    finally:
        os.remove(tmp)
    expect("threshold vocabulary is matched", sorted(got), ["MAX_THINGS", "MIN_ADOPTERS", "SOME_CEILING"])
    expect("an unrelated integer is not a threshold", "UNRELATED" in got, False)
    expect("a bool is not a threshold", "ENABLED" in got, False)
    expect("a string constant is not a threshold", "NAME" in got, False)

    expect("a printed value is visible",
           invisible("gate: OK — 7 things (ceiling 7)", {"MAX_THINGS": 7}), [])
    expect("an UNPRINTED value is reported",
           invisible("gate: OK — all clear", {"MAX_THINGS": 7}), ["MAX_THINGS = 7"])
    expect("printing only on the FAILURE path is what this catches",
           invisible("gate: OK — nothing to report", {"CEILING": 400}), ["CEILING = 400"])
    expect("a value BURIED in a larger number does not count as printed",
           invisible("scanned 1400 files", {"CEILING": 400}), ["CEILING = 400"])
    expect("...but the same value standing alone does",
           invisible("scanned 1400 files (ceiling 400)", {"CEILING": 400}), [])
    expect("a threshold of 0 is matched exactly, not found inside 10",
           invisible("held at 10", {"MAX_BYPASS": 0}), ["MAX_BYPASS = 0"])

    # The LIMITATION, pinned so it cannot be quietly assumed away. A ratchet at its ceiling
    # prints a count equal to its threshold, and this check cannot tell them apart.
    expect("a COUNT equal to the threshold satisfies the check — the known blind spot",
           invisible("engine-pinned sessions 9", {"MAX_PINNED_SESSIONS": 9}), [])

    # The live tree must have something to check — a meta-gate that finds no gates is blind.
    live = {f: thresholds(os.path.join(SCRIPTS, f)) for f in gate_scripts()}
    carrying = {f: t for f, t in live.items() if t}
    expect("the real tree yields threshold-carrying gates", bool(carrying), True)
    expect("every SILENT_BY_DESIGN entry carries a non-empty reason",
           all(v and v.strip() for v in SILENT_BY_DESIGN.values()), True)

    print(f"{chr(10)}  {'all checks passed' if ok else 'SELFTEST FAILED'}")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    findings: list[str] = []
    checked = 0
    for fname in gate_scripts():
        values = thresholds(os.path.join(SCRIPTS, fname))
        if not values:
            continue
        checked += 1
        output = run_gate(fname)
        for miss in invisible(output, values):
            name = miss.split(" = ")[0]
            reason = SILENT_BY_DESIGN.get(f"{fname}:{name}")
            if reason and reason.strip():
                continue
            findings.append(f"{fname}: {miss} never reaches the output")

    if not findings:
        print(f"[gate-number-visibility-gate] OK — {checked} gate(s) carry a threshold; every "
              f"one prints it on a green run ({len(SILENT_BY_DESIGN)} declared silent)")
        return 0

    print("[gate-number-visibility-gate] FAIL — a ratchet nobody can see:\n")
    for f in findings:
        print(f"    {f}")
    print(
        "\n  The number IS the mechanism: it is what makes a slow regression visible commit "
        "by\n  commit instead of turning up in an audit. Printed only on failure, it says "
        "nothing\n  on every green run and drift becomes history rather than a diff.\n\n"
        "  Print it on the PASS path, or declare it in SILENT_BY_DESIGN with the reason.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
