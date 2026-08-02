#!/usr/bin/env python3
"""actor-hub-figures — every number the actor-hub handoff claims, MEASURED.

WHY THIS EXISTS
---------------
The stale-figure defect recurred **four times** in one round, each time inside
the commit that recorded the previous recurrence:

  D-343  the SESSION_HANDOFF block shipped in the feature commit carried four
         numbers that same commit superseded.
  D-350  the fix advanced 270 -> 279 while its own VERIFY line said 281.
  D-351  the next fix advanced 279 -> 281 while its own VERIFY line said 283.
  D-353  the row declaring the remedy *"every number is now derived by a script
         that reads the artifacts"* was written **while no such script existed**
         -- the repo's own *"intent is not a mechanism"*, in the sentence
         claiming a mechanism.

This is that script. It reads the artifacts and prints what they say. Nothing
here is typed from memory, and a figure that disagrees with this output is
wrong by construction rather than by argument.

    python scripts/actor-hub-figures.py
    python scripts/actor-hub-figures.py --check    # exit 1 if a doc disagrees
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

CRATES = [
    "actor-hub", "entity-existence", "ruleset-core", "game-rules", "ruleset-loader",
]
CONTRACTS = [
    "docs/specs/2026-08-02-actor-hub/2026-08-02-actor-hub.md",
    "docs/specs/2026-08-02-actor-hub/2026-08-02-engine-substrate.md",
]
RUN_STATE = "docs/plans/2026-08-02-actor-substrate-RUN-STATE.md"
HANDOFF = "docs/sessions/SESSION_HANDOFF.md"
SEAMS = "docs/specs/2026-08-02-actor-hub/2026-08-02-seams-and-triggers.md"


def _passed(args: list[str]) -> int:
    out = subprocess.run(["cargo", "test", *args], cwd=REPO, capture_output=True, text=True)
    return sum(int(m) for m in re.findall(r"test result: ok\. (\d+) passed", out.stdout))


def _max_id(path: str, prefix: str) -> int:
    text = (REPO / path).read_text(encoding="utf-8", errors="replace")
    ids = [int(x) for x in re.findall(rf"\*\*{prefix}-(\d+)\*\*", text)]
    return max(ids) if ids else 0


def _hook_gate_scripts() -> int:
    """Distinct `scripts/*.py|sh` invoked by the pre-commit hook.

    Counts SCRIPTS, not tools: `eslint` and friends are wired by the hook too and
    are not gate scripts, which is why an earlier hand count said 38 for 37.
    """
    text = (REPO / ".githooks/pre-commit").read_text(encoding="utf-8", errors="replace")
    body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    return len(set(re.findall(r"scripts/([A-Za-z0-9_-]+\.(?:py|sh))", body)))


def measure() -> dict:
    return {
        "rust_tests": _passed(["-p" if False else "-p", CRATES[0], *sum([["-p", c] for c in CRATES[1:]], [])]),
        "dp_kernel_lib_tests": _passed(["-p", "dp-kernel", "--lib"]),
        "max_decision_id": _max_id(RUN_STATE, "D"),
        "max_seam_id": _max_id(SEAMS, "S"),
        "contract_lines": {
            c.rsplit("/", 1)[-1]: len((REPO / c).read_text(encoding="utf-8").splitlines())
            for c in CONTRACTS
        },
        "hook_gate_scripts": _hook_gate_scripts(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the handoff or run-state disagrees with a measured figure")
    args = ap.parse_args()

    m = measure()
    print(json.dumps(m, indent=2))

    if not args.check:
        return 0

    problems: list[str] = []
    # SCOPE: the CURRENT-STATE blocks only.
    #
    # The first version of this check scanned both documents whole and reported
    # eight disagreements, every one of them a correct HISTORICAL statement --
    # slice S4's "202 passed" from the design round, "D-1..D-109" from the item
    # round's snapshot. That is the cry-wolf failure this round spent four rounds
    # learning, reproduced immediately in the tool written to stop a different
    # one. A decision record is supposed to contain the numbers that were true
    # when it was written.
    for doc, marker, span in (
        (HANDOFF, "## ▶ GAME TIER", 4000),
        (RUN_STATE, "> # ▶▶ NEXT SESSION STARTS HERE", 4000),
    ):
        text = (REPO / doc).read_text(encoding="utf-8", errors="replace")
        start = text.find(marker)
        text = text[start:start + span] if start >= 0 else ""
        for claimed in re.findall(r"\*\*(\d+) passed, 0 failed\*\*", text):
            if int(claimed) != m["rust_tests"]:
                problems.append(f"{doc}: claims {claimed} passing tests, measured {m['rust_tests']}")
        for claimed in re.findall(r"`D-1`\.\.`D-(\d+)`", text):
            if int(claimed) != m["max_decision_id"]:
                problems.append(
                    f"{doc}: claims decisions up to D-{claimed}, "
                    f"the run-state's maximum is D-{m['max_decision_id']}"
                )

    if problems:
        print("\nactor-hub-figures --check: %d disagreement(s)\n" % len(problems), file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        print(
            "\nA figure that disagrees with this script is wrong by construction. "
            "Re-read the measurement; do not advance the number.",
            file=sys.stderr,
        )
        return 1

    print("\nactor-hub-figures --check: the docs agree with the artifacts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
