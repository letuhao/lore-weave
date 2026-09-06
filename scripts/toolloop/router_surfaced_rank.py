"""DQ-T90 option (d): do the tools a turn ALREADY SURFACED rank the skills better than the prompt?

My own recommendation on that question: "(d) is the most interesting and the least measured:
nothing here says whether surfaced tools rank the skills better than the prompt does. It should
be measured with this same instrument before it is built, which is the rule DQ-T67 set and that
worked." This is that measurement.

THE COMPARISON, per turn, over the same ground truth DQ-T67's instrument uses (the tools the turn
actually CALLED, mapped to a skill by unambiguous prefix; a turn whose tools map to no skill is
EXCLUDED rather than guessed):

    PROMPT ranking    cosine(prompt embedding, skill vector)      -- what ships
    SURFACED ranking  share of the turn's ADVERTISED tools whose
                      prefix maps to that skill                   -- option (d)

🔴 THE VALIDITY PROBLEM, AND I COULD NOT BUILD A CLEAN CONTROL FOR IT. The surfaced set is
partly the ROUTER'S OWN OUTPUT: a skill the router injects activates its tools, so ranking skills
by surfaced tools is partly the router scoring its own prior decision.

I first added a `--hot-only` flag meant to keep only surfaces the router had not influenced. IT
WAS A NO-OP AND RETURNED IDENTICAL NUMBERS: both arms already read `passes[0]`, and the skill
router runs BEFORE the first surface is built, so pass 1 is not pre-injection either. The flag is
removed rather than left looking like a control. Separating the two needs `injected_skills`, which
the surface snapshot carries and `chat_messages.advertised_tools` does not.

🔴 AND MY FIRST READING OF THE DOMINANCE FIGURE WAS WRONG TOO. I was about to report that
whichever skill owns the most surfaced tools is simply the biggest skill -- a property of
catalogue size, independent of how the surface was chosen. Checked against the live catalogue:

    composition 108 tools  -> dominates    537 turns
    glossary     54 tools  -> dominates  3,228 turns

The SMALLER skill dominates six times as often. So the surfaced set is shaped by the DOMAIN
HOT-SET, not by catalogue size -- which means ranking skills by surfaced tools largely reproduces
a selection decision the platform has already made upstream, rather than reading the request
independently. That makes the feedback caveat above worse, not better.

Reads the chat store directly. Writes nothing. No LLM call on the surfaced arm at all; the prompt
arm reuses the deployed embedding client exactly as the router does.
"""
from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys

#: tool-name prefix -> the skill that owns that domain. VERBATIM from
#: router_score_distribution.py so the two instruments cannot drift.
PREFIX = {"book": "book", "jobs": "jobs", "glossary": "glossary", "composition": "composition",
          "plan": "plan_forge", "kg": "knowledge", "translation": "translation",
          "settings": "settings"}

CAP = 2  # ROUTER_MAX_ADDITIONS as shipped; reported, never changed here

SQL = """
SELECT m.content, m.advertised_tools::text, m.tool_calls::text
FROM chat_messages m
WHERE m.role='assistant' AND m.advertised_tools IS NOT NULL AND m.tool_calls IS NOT NULL
"""


def rows(first_pass_only: bool):
    r = subprocess.run(
        ["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave",
         "-d", "loreweave_chat", "-tA", "-F", "\t"],
        input=SQL, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600)
    if r.returncode != 0:
        raise SystemExit(f"psql failed: {r.stderr[:300]}")
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        _content, adv_s, calls_s = parts
        try:
            adv, calls = json.loads(adv_s), json.loads(calls_s)
        except Exception:
            continue
        if not isinstance(adv, list) or not isinstance(calls, list):
            continue
        passes = [p for p in adv if isinstance(p, dict) and p.get("names")]
        if not passes:
            continue
        if first_pass_only:
            passes = [p for p in passes if p.get("pass") in (1, "1")]
            if not passes:
                continue
        surfaced = list(passes[0].get("names") or [])
        called = [c.get("tool") for c in calls
                  if isinstance(c, dict) and isinstance(c.get("tool"), str)]
        if surfaced and called:
            yield surfaced, called


def skill_of(tool: str) -> str | None:
    return PREFIX.get(tool.split("_")[0])


def main() -> int:
    argparse.ArgumentParser().parse_args()

    n = 0
    ranks = []
    in_cap = 0
    dominated_by = collections.Counter()
    truth_absent = 0

    for surfaced, called in rows(False):
        truth = {s for s in (skill_of(t) for t in called) if s}
        if not truth:
            continue
        n += 1
        counts = collections.Counter(s for s in (skill_of(t) for t in surfaced) if s)
        if not counts:
            truth_absent += 1
            continue
        order = [c for c, _ in counts.most_common()]
        best = min((order.index(t) for t in truth if t in order), default=None)
        if best is None:
            truth_absent += 1
            continue
        ranks.append(best + 1)
        if best < CAP:
            in_cap += 1
        dominated_by[order[0]] += 1

    if not n:
        print("no rows matched — the corpus filter excluded everything")
        return 1

    import statistics
    print(f"turns with a surfaced set AND a mappable called tool: {n}\n")
    print("OPTION (d) — ranking skills by the turn's own surfaced tools:")
    print(f"    the correct skill is TOP-{CAP}          {in_cap} of {n}   "
          f"{100 * in_cap / n:.1f}%")
    if ranks:
        print(f"    its median rank                     {statistics.median(ranks):.0f}")
    print(f"    no surfaced tool maps to any skill  {truth_absent}")
    print("\n  what the surfaced set is DOMINATED by (rank-1 skill, by turn):")
    for c, k in dominated_by.most_common(6):
        print(f"      {k:5}  {c}")
    # 🔴 NOT A LIKE-FOR-LIKE COMPARISON, and saying so is the point. DQ-T67's figure is over 995
    # DEDUPED PROMPTS; this is over turns. Two populations, so the percentages must not be
    # subtracted. What IS comparable is the dominance mechanism printed above.
    print("\nDQ-T67's shipped PROMPT ranking, for context and NOT for subtraction:")
    print("    correct domain IS injected           645 of 995 deduped prompts   64.8%")
    print("    (different population — turns here, prompts there)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
