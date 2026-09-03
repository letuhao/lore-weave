#!/usr/bin/env python3
"""Read a gate result for a whole batch and sort the tools into what to DO about each.

    python scripts/toolloop/triage_batch.py docs/eval/toolloop/2026-08-14/rebaseline.json

🔴 WHY THIS EXISTS. `gate.py check` prints one line per BAR per tool — for a 41-tool batch that is
several hundred lines, and the question a cycle actually asks is much smaller: which tools can be
concluded now, which are blocked on something nameable, and which failed for a reason that is not
about the tool at all. Scanning that by eye is where a tool gets concluded on a bar someone skimmed.

IT DECIDES NOTHING. It groups gate output and prints the exact `conclude` command for the group that
is ready; every conclusion still goes through `gate.py conclude`, which re-checks the bars itself and
refuses `blocked` without a written reason. This is a reading aid over the gate, never a substitute:
if it disagrees with the gate, the gate is right.

THE THREE GROUPS, and the middle one is the one that matters:
  READY          every bar passed — `conclude --state proven` will be accepted
  BLOCKED-ABLE   the only failures are the two the gate excuses for a blocked tool (LIVE called,
                 SHIP exercised), so it can be concluded `blocked` WITH a reason
  NOT-EVIDENCE   LIVE clean failed — the turn died in transport, so the run is no evidence about the
                 tool in EITHER direction and the gate refuses both verdicts. These need a re-run,
                 not a decision, and counting them as "blocked" would be recording a platform
                 failure as a tool's property.
"""
from __future__ import annotations

import collections
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "toolloop" / "gate.py"

#: the two bars gate.py excuses when concluding a tool `blocked` (its `excused` tuple)
EXCUSED = ("LIVE called", "SHIP exercised")
LINE = re.compile(r"^\s*(ok|FAIL)\s+\[([^\]]+)\]\s+(.*)$")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    batch = sys.argv[1]
    r = subprocess.run([sys.executable, str(GATE), "check", batch],
                       capture_output=True, text=True, cwd=str(ROOT))
    fails: dict[str, list[str]] = collections.defaultdict(list)
    tools: set[str] = set()
    for line in (r.stdout or "").splitlines():
        m = LINE.match(line)
        if not m:
            continue
        verdict, tool, rest = m.group(1), m.group(2), m.group(3)
        tools.add(tool)
        if verdict == "FAIL":
            fails[tool].append(rest)

    ready, blockable, not_evidence = [], [], []
    for t in sorted(tools):
        f = fails.get(t) or []
        if not f:
            ready.append(t)
        elif any("LIVE clean" in x for x in f):
            not_evidence.append((t, f))
        elif all(any(e in x for e in EXCUSED) for x in f):
            blockable.append((t, f))
        else:
            not_evidence.append((t, f))

    print(f"{batch}\n  tools={len(tools)}  ready={len(ready)}  "
          f"blocked-able={len(blockable)}  not-evidence={len(not_evidence)}\n")

    if ready:
        print("READY — every bar passed:")
        for t in ready:
            print(f"  {t}")
        print("\n  python scripts/toolloop/gate.py conclude --state proven \\")
        print(f"      --tool {' \\\n      --tool '.join(ready[:1])} {batch}")
        print("  (one invocation per tool; the gate re-checks the bars itself)\n")

    if blockable:
        print("BLOCKED-ABLE — only excused bars failed; needs a written blocked_reason:")
        for t, f in blockable:
            print(f"  {t}\n      {'; '.join(x[:100] for x in f)}")
        print()

    if not_evidence:
        print("NOT EVIDENCE — re-run, do not conclude:")
        for t, f in not_evidence:
            why = "LIVE clean (transport)" if any("LIVE clean" in x for x in f) else "other bars"
            print(f"  {t:36} {why}")
            for x in f:
                print(f"      {x[:110]}")
        print("\n  A turn that died in transport says nothing about the tool in EITHER direction.")
        print("  Concluding these `blocked` would record a platform failure as a tool's property.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
