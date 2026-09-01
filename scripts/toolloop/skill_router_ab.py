"""DQ-T90 A/B: does the router's preload put the CORRECT skill body on the turn more often
than the model does when asked to fetch it itself?

OWNER 2026-09-01: "A/B test for proposals".

    CONTROL   skill_router_preload=True   the shipped path, byte-for-byte
    ARM (e)   skill_router_preload=False  base/pinned skills + the L1 index; the model pulls a
                                          body with `load_skill` (the twin of tool_load)

THE MEASURE, and it is deliberately NOT "did the model call load_skill". A turn where the model
declines to load and answers anyway is a LOSS, because absent domain guidance is the defect this
question was opened on. What is scored is PRESENCE:

    ground truth   the skill owning the tools the turn actually CALLED, by unambiguous prefix
                   (a turn whose calls map to no skill is EXCLUDED, never guessed)
    hit            that skill appears in the turn's `injected_skills`

THE BAR IS THE ROUTER'S OWN HIT RATE. An arm does not win by being cheaper: it must put the
correct body on MORE turns than the control does on the same scenarios. Token cost is reported
alongside, because the router exists precisely because a bare floor re-injected ~15.5k tokens.

WHY THE ARMS MUST BE RUN FRESH AND PAIRED: an older control run is not a control. The platform
changed underneath this loop twice today (a glossary migration restored at 06:05, a chat-service
rebuild), and a paired same-day run is the only way the two arms differ by one flag.
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

#: tool-name prefix -> owning skill. VERBATIM from router_score_distribution.py /
#: router_surfaced_rank.py so the three instruments cannot drift apart.
PREFIX = {"book": "book", "jobs": "jobs", "glossary": "glossary", "composition": "composition",
          "plan": "plan_forge", "kg": "knowledge", "translation": "translation",
          "settings": "settings"}


def skill_of(tool: str) -> str | None:
    return PREFIX.get(tool.split("_")[0])


def called_tools(run: dict) -> list[str]:
    out = []
    for c in run.get("tool_calls") or []:
        if isinstance(c, dict):
            n = c.get("toolCallName") or c.get("tool")
            if n:
                out.append(n)
    return out


def injected(run: dict) -> set[str]:
    """Every skill injected at any point in the turn — the union across passes, because a body
    that arrived on pass 3 was still present when the tool was called on pass 4."""
    got: set[str] = set()
    for s in (run.get("surfaces") or ([run["surface"]] if isinstance(run.get("surface"), dict) else [])):
        if isinstance(s, dict):
            got.update(s.get("injected_skills") or [])
    return got


def score(path: pathlib.Path) -> dict:
    runs = json.loads(path.read_text(encoding="utf-8"))
    runs = runs if isinstance(runs, list) else runs.get("runs") or []
    n = hit = 0
    excluded = 0
    load_skill_calls = 0
    tokens = []
    missed = collections.Counter()
    for r in runs:
        if not isinstance(r, dict):
            continue
        tools = called_tools(r)
        load_skill_calls += sum(1 for t in tools if t == "load_skill")
        truth = {s for s in (skill_of(t) for t in tools) if s}
        for s in (r.get("surfaces") or []):
            # `schema_tokens` is a BREAKDOWN ({"frontend": n, "mcp": n}), not a scalar — summing
            # is the only reading that survives a new key being added to it.
            st = s.get("schema_tokens") if isinstance(s, dict) else None
            if isinstance(st, dict):
                tokens.append(sum(v for v in st.values() if isinstance(v, (int, float))))
            elif isinstance(st, (int, float)):
                tokens.append(st)
        if not truth:
            excluded += 1
            continue
        n += 1
        got = injected(r)
        if truth & got:
            hit += 1
        else:
            for t in truth:
                missed[t] += 1
    import statistics
    return {"file": path.name, "scored": n, "hit": hit,
            "pct": (100.0 * hit / n) if n else 0.0,
            "excluded_no_mappable_tool": excluded,
            "load_skill_calls": load_skill_calls,
            "median_schema_tokens": (statistics.median(tokens) if tokens else 0),
            "missed": missed.most_common(5)}


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: skill_router_ab.py <control-raw.json> <arm-raw.json>")
        return 2
    ctl, arm = (score(pathlib.Path(p)) for p in sys.argv[1:3])

    for r in (ctl, arm):
        if not r["scored"]:
            print(f"ABORT, NOT A VERDICT: {r['file']} scored ZERO turns — every run was excluded "
                  f"for having no tool that maps to a skill ({r['excluded_no_mappable_tool']} "
                  "excluded). Nothing here is about the router.")
            return 1

    print(f"{'arm':10} {'scored':>7} {'correct skill PRESENT':>23} {'load_skill':>11} "
          f"{'median schema tok':>18}")
    for label, r in (("CONTROL", ctl), ("ARM (e)", arm)):
        print(f"{label:10} {r['scored']:7} {r['hit']:>10} = {r['pct']:5.1f}%  "
              f"{r['load_skill_calls']:>11} {r['median_schema_tokens']:>18}")
        if r["missed"]:
            print(f"           missed: {r['missed']}")

    print()
    delta = arm["pct"] - ctl["pct"]
    if arm["pct"] > ctl["pct"]:
        print(f"ARM (e) IS AHEAD by {delta:.1f} points on this scenario set.")
    elif arm["pct"] < ctl["pct"]:
        print(f"ARM (e) IS BEHIND by {-delta:.1f} points — the model did not fetch what the "
              "router was preloading, which is the round-trip risk this arm carries.")
    else:
        print("NO DIFFERENCE on this scenario set.")
    print("🔴 n is small on a scenario batch. This ranks the arms on THESE scenarios; it does not "
          "reproduce the 64.8% corpus figure, which is over deduped prompts from the chat store "
          "and is a different population. Do not subtract the two.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
