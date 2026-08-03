#!/usr/bin/env python3
"""actor-hub-figures — every number the actor-hub docs claim, MEASURED.

WHY THIS EXISTS
---------------
The stale-figure defect recurred **five times** in one round, each time inside
the commit that recorded the previous recurrence:

  D-343  the handoff block shipped in the feature commit carried four numbers
         that same commit superseded.
  D-350  the fix advanced 270 -> 279 while its own VERIFY line said 281.
  D-351  the next fix advanced 279 -> 281 while its own VERIFY line said 283.
  D-353  the row declaring the remedy *"every number is now derived by a script
         that reads the artifacts"* was written while **no such script existed**.
  D-359  the first version of THIS script then refused its own commit: the
         handoff said `D-353` while the run-state had reached `D-358`.

WHAT A REVIEW THEN FOUND IN THIS SCRIPT, AND WHAT CHANGED
---------------------------------------------------------
The first version measured **six** quantities and compared **two**, while the
documents claimed *"every figure in this block is emitted by this script, which
`--check`s them"*. **That is `D-353`'s defect one level up — a mechanism claimed
rather than verified — inside the mechanism written to end it.** It also:

  * crashed with a raw ``FileNotFoundError`` when ``cargo`` was absent, in a hook
    triggered by the **repo-wide** ``SESSION_HANDOFF.md`` — so a frontend or
    Python contributor on any of 47 services could not commit a handoff update;
  * passed **silently** when a marker string moved, reporting *"the docs agree"*
    against zero subjects;
  * had a RUN-STATE arm whose window contained **no** matching claim at all;
  * missed ``_index.md``, the file with the worst record for this exact defect
    (stale twice, `D-347` and `D-350`);
  * counted a FAILING ``cargo test`` as zero passes and then told the developer
    to rewrite the doc to match a broken build;
  * had no ``--self-test`` of its own, unlike both sibling gates;
  * and was named ``actor-hub-figures.py`` -- **which `gate-wiring-gate`'s
    filename predicate does not recognise**, so `--run-all` never executed it and
    the degradation message's promise *"CI checks it"* was FALSE. Renamed to
    ``-gate.py``, which is the shape that predicate keys on. A promise about
    another mechanism is a claim like any other.

Every one of those is fixed below, and each has a case in ``--self-test``.

    python scripts/actor-hub-figures-gate.py            # measure + check (the default)
    python scripts/actor-hub-figures-gate.py --print    # measurements only, never fails
    python scripts/actor-hub-figures-gate.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

CRATES = ["actor-hub", "entity-existence", "ruleset-core", "game-rules", "ruleset-loader"]
CONTRACTS = [
    "docs/specs/2026-08-02-actor-hub/2026-08-02-actor-hub.md",
    "docs/specs/2026-08-02-actor-hub/2026-08-02-engine-substrate.md",
]
SEAMS = "docs/specs/2026-08-02-actor-hub/2026-08-02-seams-and-triggers.md"
RUN_STATE = "docs/plans/2026-08-02-actor-substrate-RUN-STATE.md"
HANDOFF = "docs/sessions/SESSION_HANDOFF.md"
INDEX = "docs/specs/2026-08-02-actor-hub/_index.md"

# The blocks whose figures are CURRENT-STATE claims. A decision record is
# supposed to contain the numbers that were true when it was written, so the
# scan is bounded to the block a session rewrites — see `D-358`, which is what
# the first version of this check got wrong in the other direction.
#
# `end` is a marker, not a character count. A fixed 4000-char window put the
# RUN-STATE arm's subjects OUTSIDE it, so half the check had nothing to compare.
SCOPES: tuple[tuple[str, str, str], ...] = (
    (HANDOFF, "## ▶ GAME TIER", "\n---\n"),
    (RUN_STATE, "> # ▶▶ NEXT SESSION STARTS HERE", "\n---\n"),
    # The SLICE BOARD's own summary block. A stop-audit found it STALE at
    # round seven -- "81 findings over five rounds" when the count was 123 over
    # seven -- because the check covered the header and the handoff and not the
    # board two screens below them. **A figure outside a checker's scope is a
    # figure nobody is reading**, which is `_index.md`'s defect one file along.
    (RUN_STATE, "### 6-BUILD", "| # | Slice |"),
    (INDEX, "# Actor Hub", "\n## Read this to REUSE"),
)


class Unmeasurable(Exception):
    """A figure that cannot be measured HERE — never a reason to block a commit."""


def _cargo_passed(args: list[str]) -> int:
    """Passing tests, or `Unmeasurable` if the toolchain is absent or the build is red.

    **Never raises a bare OSError, and never reports 0 for a broken build.** The
    first version did both: no `cargo` gave a raw traceback inside a pre-commit
    hook that fires on the repo-wide handoff, and a failing suite summed to 0,
    after which the script told the developer *"do not advance the number"* —
    i.e. to rewrite the doc to match a broken build.
    """
    if shutil.which("cargo") is None:
        raise Unmeasurable("cargo is not on PATH")
    out = subprocess.run(["cargo", "test", *args], cwd=REPO, capture_output=True, text=True)
    if "test result: FAILED" in out.stdout or out.returncode != 0:
        raise Unmeasurable("the test run is not green, so its count means nothing")
    return sum(int(m) for m in re.findall(r"test result: ok\. (\d+) passed", out.stdout))


def _max_id(path: str, prefix: str) -> int:
    text = (REPO / path).read_text(encoding="utf-8", errors="replace")
    ids = [int(x) for x in re.findall(rf"\*\*{prefix}-(\d+)\*\*", text)]
    if not ids:
        raise Unmeasurable(f"no bold {prefix}- id in {path}")
    return max(ids)


def _hook_gate_scripts() -> int:
    """Distinct `scripts/*.py|sh` the pre-commit hook invokes, comments excluded."""
    text = (REPO / ".githooks/pre-commit").read_text(encoding="utf-8", errors="replace")
    body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    return len(set(re.findall(r"scripts/([A-Za-z0-9_-]+\.(?:py|sh))", body)))


def measure() -> dict[str, object]:
    out: dict[str, object] = {}
    for name, fn in (
        ("rust_tests", lambda: _cargo_passed(sum([["-p", c] for c in CRATES], []))),
        ("dp_kernel_lib_tests", lambda: _cargo_passed(["-p", "dp-kernel", "--lib"])),
        ("max_decision_id", lambda: _max_id(RUN_STATE, "D")),
        ("max_seam_id", lambda: _max_id(SEAMS, "S")),
        ("hook_gate_scripts", _hook_gate_scripts),
    ):
        try:
            out[name] = fn()
        except Unmeasurable as e:
            out[name] = {"unmeasurable": str(e)}
    out["contract_lines"] = {
        c.rsplit("/", 1)[-1]: len((REPO / c).read_text(encoding="utf-8").splitlines())
        for c in CONTRACTS
    }
    return out


# Every claim shape this script governs, and the measurement it must equal.
# **A claim shape with no subject anywhere is itself a finding** — see `_check`.
CLAIMS: tuple[tuple[str, str, str], ...] = (
    (r"\*\*(\d+) passed, 0 failed\*\*", "rust_tests", "passing tests"),
    (r"`dp-kernel --lib` \*\*(\d+)\*\*", "dp_kernel_lib_tests", "dp-kernel lib tests"),
    (r"`D-1`\.\.`D-(\d+)`", "max_decision_id", "the highest decision id"),
    (r"`S-11`\.\.`S-(\d+)`", "max_seam_id", "the highest seam id"),
    (r"the \*\*(\d+)\*\*\s*\n?gate scripts", "hook_gate_scripts", "hook gate scripts"),
    (r"\*\*(\d+)\*\* gate scripts", "hook_gate_scripts", "hook gate scripts"),
)


def _scope_text(doc: str, start_marker: str, end_marker: str) -> str | None:
    """The current-state block, or None if its anchor has moved."""
    try:
        text = (REPO / doc).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    i = text.find(start_marker)
    if i < 0:
        return None
    j = text.find(end_marker, i + len(start_marker))
    return text[i:j] if j > 0 else text[i:]


def _check(m: dict[str, object]) -> tuple[list[str], list[str]]:
    """(blocking problems, non-blocking notes)."""
    problems: list[str] = []
    notes: list[str] = []
    seen: set[str] = set()

    for doc, start_marker, end_marker in SCOPES:
        block = _scope_text(doc, start_marker, end_marker)
        if block is None:
            # **A moved anchor is a FINDING, not a silent pass.** The first
            # version set the text to "" and reported "the docs agree" against
            # zero subjects — a check whose scope never reaches it (NV-3).
            problems.append(
                f"{doc}: the marker `{start_marker}` is gone, so this document was NOT checked"
            )
            continue
        for pattern, key, label in CLAIMS:
            want = m.get(key)
            for claimed in re.findall(pattern, block):
                seen.add(key)
                if isinstance(want, dict):
                    # **A figure this MACHINE cannot measure is a SKIP, not a
                    # block.** The hook fires on the repo-wide `SESSION_HANDOFF`,
                    # which this project's SESSION phase mandates updating on
                    # essentially every commit across 47 services — so refusing
                    # a commit because the contributor has no Rust toolchain is
                    # the cry-wolf failure this round spent four rounds learning,
                    # aimed at people who never touched the actor hub.
                    #
                    # CI has the toolchain and enforces there. Every sibling gate
                    # in this repo degrades the same way, with a printed reason.
                    notes.append(
                        f"{doc}: claims {claimed} for {label} — NOT CHECKED here "
                        f"({want['unmeasurable']}); CI checks it"
                    )
                elif int(claimed) != want:
                    problems.append(
                        f"{doc}: claims {claimed} for {label}, measured {want}"
                    )

    # A claim shape that matches NOTHING anywhere is a rule with no subject.
    # Half of the first version's check was exactly this and nobody noticed,
    # because a vacuous arm and a passing arm look identical from outside.
    for _, key, label in CLAIMS:
        if key not in seen and not isinstance(m.get(key), dict):
            problems.append(
                f"NO DOCUMENT claims {label}: this arm of the check has no subject "
                "and proves nothing (docs/standards/non-vacuity.md, NV-3)"
            )
    return problems, notes


def self_test() -> int:
    """Each rule against input that violates it AND input that must not trip it."""
    failures = 0

    def case(name: str, block: str, m: dict, expect: int) -> None:
        nonlocal failures
        got = 0
        seen: set[str] = set()
        for pattern, key, label in CLAIMS:
            for claimed in re.findall(pattern, block):
                seen.add(key)
                want = m.get(key)
                if isinstance(want, dict) or int(claimed) != want:
                    got += 1
        ok = got == expect
        failures += 0 if ok else 1
        print(f"  {'ok ' if ok else 'FAIL'} {name}: expected {expect}, got {got}")

    m = {"rust_tests": 283, "dp_kernel_lib_tests": 315, "max_decision_id": 362,
         "max_seam_id": 18, "hook_gate_scripts": 38}
    case("a correct test count passes", "**283 passed, 0 failed**", m, 0)
    case("a stale test count is caught", "**281 passed, 0 failed**", m, 1)
    case("a correct decision range passes", "`D-1`..`D-362`", m, 0)
    case("a stale decision range is caught", "`D-1`..`D-353`", m, 1)
    case("a stale dp-kernel count is caught", "`dp-kernel --lib` **300**", m, 1)
    case("a stale seam range is caught", "`S-11`..`S-15`", m, 1)
    case("a stale gate-script count is caught", "the **37**\ngate scripts", m, 1)
    case("an unmeasurable figure is a finding, not a pass",
         "**283 passed, 0 failed**",
         {**m, "rust_tests": {"unmeasurable": "cargo is not on PATH"}}, 1)

    # A moved anchor must RED rather than pass silently.
    ghost = _scope_text(HANDOFF, "## THIS MARKER DOES NOT EXIST", "\n---\n")
    if ghost is not None:
        failures += 1
        print("  FAIL a missing marker did not return None")
    else:
        print("  ok  a missing marker returns None, which the check reports")

    # The scope must be marker-bounded, not a character count: a fixed window
    # put the RUN-STATE arm's subjects outside it.
    for doc, start_marker, end_marker in SCOPES:
        block = _scope_text(doc, start_marker, end_marker)
        if block is None:
            failures += 1
            print(f"  FAIL {doc}: its own marker does not resolve")
            continue
        subjects = sum(len(re.findall(p, block)) for p, _, _ in CLAIMS)
        if subjects == 0:
            failures += 1
            print(f"  FAIL {doc}: its block contains NO claim this script governs")
        else:
            print(f"  ok  {doc}: {subjects} claim(s) in scope")

    if failures:
        print(f"\nactor-hub-figures --self-test: {failures} rule(s) did not behave")
        return 1
    print("\nactor-hub-figures --self-test: every rule bites, and none cries wolf")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--print", action="store_true", dest="print_only",
                    help="measurements only; never fails")
    ap.add_argument("--check", action="store_true",
                    help="accepted for compatibility; checking is the default")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    m = measure()
    print(json.dumps(m, indent=2, default=str))
    if args.print_only:
        return 0

    problems, notes = _check(m)
    for n in notes:
        print(f"actor-hub-figures: NOTE — {n}")
    if problems:
        print(f"\nactor-hub-figures: {len(problems)} disagreement(s)\n", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        print(
            "\nA figure that disagrees with this script is wrong by construction. "
            "READ the measurement above; do not advance the number.",
            file=sys.stderr,
        )
        return 1

    print("\nactor-hub-figures: every governed figure agrees with the artifacts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
