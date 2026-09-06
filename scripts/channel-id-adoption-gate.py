#!/usr/bin/env python3
"""channel-id-adoption-gate — `ChannelId::unverified` may only get rarer.

WHAT IT GUARDS
--------------
`dp::ChannelId::unverified` mints a channel identity from a value nothing
resolved. It is the pre-SDK seam `dp-kernel` has carried since before a channel
tree existed, and slice `5D` moved it to `crates/dp` with the type rather than
deleting it.

Deleting it in one commit would mean routing every call site through a real
tree, which for the unit tests among them means inventing a fake tree — trading
an honest escape hatch for a dishonest verification. §0.6c already sealed the
shape for `3E`'s 880 sites: **a ratchet, never a big bang.**

WHY A GATE AND NOT THE DOC COMMENT THAT WAS ALREADY THERE
----------------------------------------------------------
`dp-kernel`'s own comment said, for months:

    "when `crates/dp` lands this function is deleted and the compiler
     enumerates the migration. `rg 'ChannelId::unverified'` is the worklist."

`crates/dp` landed in slice 1. The function was not deleted, and nothing said
so — because a worklist that lives in a doc comment is a worklist nobody runs.
That is the prose-only deferral shape `scripts/deferral-gate.py` exists for, in
a place it could not see. This file is the mechanism that comment described.

THE TWO FAILURE MODES, BOTH DIRECTIONS
--------------------------------------
* an INCREASE — a new call site appeared. The seam is supposed to be closing.
* an UNRECORDED DECREASE — sites were migrated and the baseline not updated.
  Silently accepting improvement sounds harmless and is not: the baseline stops
  describing the tree, and the next increase is measured against a stale figure
  that hides it.

Both are the shape `contracts/dp/dp-clippy-baseline.json` and
`contracts/dp/reality-id-baseline.json` already prove in this repo.

    python scripts/channel-id-adoption-gate.py
    python scripts/channel-id-adoption-gate.py --selftest
    REGEN_CHANNEL_ID_BASELINE=1 python scripts/channel-id-adoption-gate.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "contracts" / "dp" / "channel-id-baseline.json"

# The call, not the word. `ChannelId::unverified` in a doc comment is prose —
# the same distinction `deferral-gate` had to learn when a JSDoc header and a
# module docstring certified three prose-only deferrals as mechanised.
CALL = re.compile(r"\bChannelId::unverified\s*\(")

# Where a call site could live. `.claude/worktrees/` is EXCLUDED: it holds
# agent worktree copies of the whole repo, and counting them inflated the first
# measurement of this very worklist from 23 to 115.
ROOTS = ("crates", "services")


def strip_line_comments(text: str) -> str:
    """Drop `//`-comments so prose about the seam is not counted as a use.

    Deliberately line-based and deliberately crude: it does not understand
    strings containing `//`, and over-stripping can only UNDERCOUNT a comment,
    never invent a call. A call inside a `/* */` block would still be counted,
    which is the safe direction.
    """
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("//"))


def measure() -> Counter[str]:
    counts: Counter[str] = Counter()
    for root in ROOTS:
        base = REPO / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.rs"):
            if ".claude" in path.parts or "target" in path.parts:
                continue
            try:
                body = strip_line_comments(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            n = len(CALL.findall(body))
            if n:
                counts[str(path.relative_to(REPO)).replace("\\", "/")] = n
    return counts


def load_baseline() -> dict[str, int]:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8")).get("sites", {})


def write_baseline(counts: Counter[str]) -> None:
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(
        json.dumps({"sites": dict(sorted(counts.items()))}, indent=2) + "\n",
        encoding="utf-8",
    )


def compare(counts: Counter[str], baseline: dict[str, int]) -> list[str]:
    problems: list[str] = []
    for path in sorted(set(counts) | set(baseline)):
        now, was = counts.get(path, 0), baseline.get(path, 0)
        if now > was:
            problems.append(
                f"INCREASE: {path} has {now} `ChannelId::unverified` call(s), baseline {was}. "
                f"The seam is supposed to be closing — resolve the channel through "
                f"`SessionContext::move_to_channel` instead."
            )
        elif now < was:
            problems.append(
                f"UNRECORDED IMPROVEMENT: {path} is down to {now} from {was}. Good — now "
                f"record it: REGEN_CHANNEL_ID_BASELINE=1 python scripts/channel-id-adoption-gate.py"
            )
    return problems


def selftest() -> int:
    """Prove each arm can fail, on synthetic counts rather than on the tree."""
    failures: list[str] = []
    base = {"a.rs": 2, "b.rs": 1}

    if not compare(Counter({"a.rs": 3, "b.rs": 1}), base):
        failures.append("increase check did NOT red on 2 -> 3")
    if not compare(Counter({"a.rs": 2}), base):
        failures.append("decrease check did NOT red on a file dropping to 0")
    if not compare(Counter({"a.rs": 2, "b.rs": 1, "c.rs": 1}), base):
        failures.append("increase check did NOT red on a NEW file")
    if compare(Counter(base), base):
        failures.append("exact match reded (false positive)")

    # And the comment-stripper, which is the difference between counting a call
    # and counting a sentence about one.
    if CALL.findall(strip_line_comments("// see ChannelId::unverified(1)\n")):
        failures.append("a call inside a line comment was counted")
    if not CALL.findall(strip_line_comments("let c = ChannelId::unverified(1);\n")):
        failures.append("a real call was NOT counted")

    if failures:
        for f in failures:
            print(f"channel-id-adoption-gate: SELFTEST FAIL — {f}")
        return 1
    print(
        "channel-id-adoption-gate: SELFTEST PASS — 6 case(s); it flags an increase, an "
        "unrecorded decrease and a new file, does NOT flag an exact match, and tells a "
        "call from a comment about one (non-vacuous in both directions)"
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if selftest() != 0:
        return 1

    counts = measure()
    total = sum(counts.values())

    if os.environ.get("REGEN_CHANNEL_ID_BASELINE") == "1":
        write_baseline(counts)
        print(f"channel-id-adoption-gate: baseline rewritten — {total} site(s) across {len(counts)} file(s)")
        return 0

    baseline = load_baseline()
    if not baseline:
        print("channel-id-adoption-gate: MISUSE — no baseline. Create it with "
              "REGEN_CHANNEL_ID_BASELINE=1", file=sys.stderr)
        return 2

    print(f"[channel-id] {total} `ChannelId::unverified` call site(s) across {len(counts)} file(s)")
    for path in sorted(counts):
        print(f"    {path}: {counts[path]}")

    problems = compare(counts, baseline)
    if problems:
        print("\nchannel-id-adoption-gate: FAIL")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("[channel-id-adoption-gate] OK — matches the baseline exactly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
