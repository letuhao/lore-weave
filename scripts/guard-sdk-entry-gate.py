#!/usr/bin/env python3
"""S9 — the guard-SDK extraction has an ENTRY CRITERION, and it is now a mechanism.

Why this script exists rather than a fourth SDK
------------------------------------------------
S9's v1 was "extract a shared guard SDK". The red team inverted it, for two measured reasons:

  · It would be the **fourth**. `loreweave_grounding`, `loreweave_canon_check` and
    `loreweave_eval` already exist with three unreconciled verdict shapes; a fourth abstraction
    over three that disagree does not unify anything, it adds a place to disagree.
  · **Three of the four adopters v1 named produce a float score, not a tri-state verdict.**
    An interface extracted from one implementation is that implementation with an import.

So the sealed decision is: land `GuardReport` INSIDE composition · implement the same contract
INDEPENDENTLY in translation and knowledge as part of their own slices · **then** extract what
all three actually agreed on.

And the entry criterion was a sentence in a spec:

    "three services carry a structurally identical GuardReport with no service-specific
     fields, proven by a test that imports all three."

A criterion that lives only in prose fails in both directions. It is forgotten — the extraction
never happens and three services drift apart anyway — or it is acted on from memory before it
holds, which is exactly the premature-abstraction this inversion exists to prevent. This repo
has the rule already (`docs/standards/`: intent is not a mechanism; a claim in a doc is not
enforcement), and a `PROSE_ONLY` deferral registry that exists because nine of nineteen game-tier
deferrals were prose and nothing else.

So the criterion is measured here, on every run:

  · while adoption is BELOW the threshold, this reports the distance and exits 0. Not building
    the SDK is the correct state, and a gate that reds for a decision working as designed
    teaches people to silence it.
  · when adoption REACHES the threshold, it exits 1 — because at that moment the sealed
    decision says extract, and nobody is going to re-read a spec sentence from July to find out.

    python scripts/guard-sdk-entry-gate.py          # gate
    python scripts/guard-sdk-entry-gate.py --list   # per-service adoption detail
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The contract an adopter must carry. Named symbols, not a fuzzy "has a guard" — the whole
#: point of the criterion is that the three are STRUCTURALLY identical.
CONTRACT_SYMBOLS = ("GuardReport", "CheckStatus")

#: Services that could adopt it. A service absent here can never satisfy the criterion, so the
#: list is the denominator and it is derived from the AI-service set, not from what shipped.
CANDIDATE_SERVICES = (
    "composition-service",
    "translation-service",
    "knowledge-service",
    "chat-service",
)

#: The sealed threshold. THREE, from the spec — one implementation is a design, two is a
#: coincidence, three is a pattern with enough evidence to say what they agree on.
REQUIRED_ADOPTERS = 3

_SKIP = ("__pycache__", "/tests/", "/test_", "/build/")


def _adopting_modules(service: str) -> list[str]:
    """Non-test modules in `service` that reference the contract symbols."""
    app = ROOT / "services" / service / "app"
    if not app.is_dir():
        return []
    pat = re.compile(r"\b(?:%s)\b" % "|".join(CONTRACT_SYMBOLS))
    out: list[str] = []
    for p in sorted(app.rglob("*.py")):
        posix = p.as_posix()
        if any(s in posix for s in _SKIP) or p.name.startswith("test_"):
            continue
        try:
            if pat.search(p.read_text(encoding="utf-8", errors="ignore")):
                out.append(p.relative_to(ROOT).as_posix())
        except OSError:
            continue
    return out


def main() -> int:
    adoption = {svc: _adopting_modules(svc) for svc in CANDIDATE_SERVICES}
    adopters = sorted(s for s, mods in adoption.items() if mods)

    if "--list" in sys.argv:
        for svc in CANDIDATE_SERVICES:
            mods = adoption[svc]
            print(f"{svc}: {len(mods)} module(s)")
            for m in mods:
                print(f"    {m}")
        return 0

    if len(adopters) < REQUIRED_ADOPTERS:
        missing = REQUIRED_ADOPTERS - len(adopters)
        print(f"guard-sdk-entry-gate: OK — {len(adopters)}/{REQUIRED_ADOPTERS} services carry "
              f"the GuardReport contract; NOT extracting is the correct state.")
        print(f"  adopters: {', '.join(adopters) or '(none)'}")
        print(f"  {missing} more before the sealed decision says extract. The repo already has "
              f"THREE verdict SDKs (loreweave_grounding, loreweave_canon_check, "
              f"loreweave_eval); a fourth built from one implementation would be that "
              f"implementation with an import.")
        return 0

    print(f"guard-sdk-entry-gate: FAIL — {len(adopters)} services now carry the GuardReport "
          f"contract ({', '.join(adopters)}).")
    print()
    print("  The S9 entry criterion is MET. The sealed decision (spec §S9) is that at this")
    print("  point the shared guard SDK gets extracted from what the three implementations")
    print("  ACTUALLY agreed on — and that the extraction folds in loreweave_canon_check's")
    print("  and loreweave_grounding's verdict types, or the repo ships with four.")
    print()
    print("  This gate exists because that criterion was a sentence in a spec written in")
    print("  July, and nobody re-reads a spec sentence to discover that a condition became")
    print("  true. Do the extraction, then delete this gate.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
