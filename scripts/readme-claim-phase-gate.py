#!/usr/bin/env python3
"""Gate: a README claim whose roadmap phase is still In Progress must SAY so.

WHY. The README states capabilities as unqualified present-tense fact in the Features and
"How LoreWeave is different" sections, while its own Roadmap table marks the phases those
capabilities belong to as "In Progress". A reader meets the promise several screens before
the qualification, and most readers never reach the table at all.

That gap is not theoretical. A 2026-09-06 human-sim run drove the product as a novelist for
days, measured the claims against what shipped, and produced a NO-GO on the headline pitch.
Two claims it could not reconcile are exactly the ones whose phases the roadmap already
flags: the co-writer that "can't contradict your canon" (Phase 3) and the "Auto-Draft
Factory" that runs "a whole drafting campaign" (Phase 4 — the engine extracts and
translates; it has no drafting stage).

WHAT THIS ENFORCES, and it is deliberately bidirectional:

  1. Every claim in CLAIMS below carries the phase marker, while its phase is In Progress.
     Strip the marker and the document silently goes back to overclaiming — the failure this
     gate exists to catch, because nothing else in CI reads marketing prose.

  2. A claim keeps its marker ONLY while its phase is In Progress. When a phase graduates to
     Done, this fails and tells you to REMOVE the markers. Without that direction the repo
     would accumulate stale "in progress" labels on shipped features, which is its own kind
     of lie and the reason a one-way check would not be worth having.

WHAT IT DOES NOT DO. It does not judge whether a claim is true, and it must not be read as
doing so — truth is what the linked tests are for (e.g. `test_automatic_extraction_claim.py`
pins the "automatic extraction" claim, which IS true and therefore carries no marker). This
gate only keeps the prose consistent with the roadmap the same document publishes.

Adding a claim here is a product decision, not a mechanical one: if a capability is claimed
and its phase is unfinished, either the phase marker goes on the claim or the claim changes,
and which of those happens is the PO's call.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"

#: The In-Progress marker, as rendered in the README.
MARKER = "🔄"

#: claim substring -> the roadmap phase that owns it.
#:
#: Keyed on a distinctive fragment rather than a whole line so ordinary copy-editing does not
#: break the gate; distinctive enough that it cannot match a different sentence.
CLAIMS: dict[str, str] = {
    "A co-writer that can't contradict your canon": "Phase 3",
    "Advisory prose critic flags potential canon contradictions": "Phase 3",
    "run a whole drafting campaign across chapters": "Phase 4",
}


def _phase_status(text: str, phase: str) -> str | None:
    """The Status cell for `phase` in the roadmap table, or None when the row is gone."""
    for line in text.splitlines():
        if line.lstrip().startswith("|") and f"**{phase}**" in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            return cells[-1] if cells else None
    return None


def main() -> int:
    text = README.read_text(encoding="utf-8")
    problems: list[str] = []

    for claim, phase in CLAIMS.items():
        status = _phase_status(text, phase)
        if status is None:
            problems.append(
                f"{phase} has no row in the roadmap table, but a claim is attributed to it "
                f"({claim!r}). Update CLAIMS in this gate deliberately — a claim pointing at a "
                f"phase that no longer exists is unenforceable."
            )
            continue

        line = next((ln for ln in text.splitlines() if claim in ln), None)
        if line is None:
            problems.append(
                f"claim not found in README: {claim!r}. If it was removed or reworded, update "
                f"CLAIMS here in the same commit — a gate watching a line nobody wrote any more "
                f"reports coverage it does not have."
            )
            continue

        in_progress = "In Progress" in status
        marked = MARKER in line

        if in_progress and not marked:
            problems.append(
                f"{phase} is '{status}' but this claim states it as finished fact:\n"
                f"    {line.strip()}\n"
                f"  Add the {MARKER} phase marker, or change the claim. A reader meets the "
                f"promise here and the qualification several screens later, if at all."
            )
        elif not in_progress and marked:
            problems.append(
                f"{phase} is now '{status}', so this claim's {MARKER} marker is STALE:\n"
                f"    {line.strip()}\n"
                f"  Remove it — labelling a shipped feature as unfinished is its own inaccuracy."
            )

    if problems:
        print("readme-claim-phase-gate: FAIL")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(
        f"readme-claim-phase-gate: OK -- {len(CLAIMS)} claim(s) consistent with the roadmap"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
