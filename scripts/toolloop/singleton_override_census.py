"""DQ-T72 option (c): de-advertise the competing sibling. WHICH sibling, on what evidence?

    THE FINDING, 2026-09-01: THE "SIBLING" IS OFTEN THE SUPPLIER. Over 380 runs where R1's
    answer was a singleton and the turn called something else first, there are 38 distinct
    pairs and the top 3 winners cover only 36% -- and 4 of the top 10 pairs name a tool the
    contract registry declares as the EMITTER of the single answer's required id (jobs_list ->
    jobs_cancel.job_id, glossary_search -> glossary_create_evidence.entity_id, and two more).
    R1 force-advertises those suppliers deliberately, so de-advertising them would remove the
    tool the platform put on the wire to make the single answer callable.

My own note on that option: "it needs its own precision measurement -- which sibling, on what
evidence -- and I have not done it, so I am not recommending it yet." This is that measurement.

THE RULE BEING PRICED: when R1's answer is a SINGLETON and the turn calls something ELSE, that
other tool is the "competing sibling". De-advertising it would leave the model the single answer.
The question is whether those siblings are a small, nameable set (a rule with a target) or a long
tail (a rule with none).
"""
import collections
import json
import pathlib
import sys

sys.path.insert(0, "services/chat-service")
from app.services.tool_surface import answerable_tools          # noqa: E402
from app.services.tool_discovery import tool_tier                # noqa: E402

raw = json.loads(pathlib.Path("contracts/tool-catalog-cache.json").read_text(encoding="utf-8"))
defs = [{"type": "function", "function": {"name": n, "description": t.get("description") or "",
         "parameters": t.get("inputSchema") or {}, "_meta": t.get("meta") or {}}}
        for n, t in raw.items()]
by = {d["function"]["name"]: d for d in defs}

pairs = collections.Counter()
victims = collections.Counter()
runs_seen = 0
for f in sorted(pathlib.Path("docs/eval/toolloop").glob("*/*-raw.json")):
    try:
        runs = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        continue
    if not isinstance(runs, list):
        continue
    for r in runs:
        if not isinstance(r, dict):
            continue
        p = r.get("prompt") or ""
        if not p:
            continue
        got = sorted(answerable_tools(p, defs))
        if len(got) != 1 or got[0] not in by:
            continue
        want = got[0]
        called = [ev.get("toolCallName") for ev in (r.get("tool_calls") or [])
                  if ev["type"] == "TOOL_CALL_START"]
        if not called or want in called:
            continue
        runs_seen += 1
        pairs[(want, called[0])] += 1
        victims[called[0]] += 1

print(f"runs where R1 answered with ONE tool and the turn called something else first: {runs_seen}\n")
print("THE SIBLING THAT WON, by how often:")
for name, n in victims.most_common(12):
    t = tool_tier(by[name]) if name in by else "?"
    print(f"  {n:4}  {name:38} tier={t}")
print(f"\ndistinct winners: {len(victims)}   distinct (wanted, won) PAIRS: {len(pairs)}")
top = sum(n for _, n in victims.most_common(3))
print(f"top 3 winners cover {top} of {runs_seen} ({100*top/max(runs_seen,1):.0f}%)")
print("\nTHE PAIRS A RULE WOULD HAVE TO NAME (top 10):")
for (w, g), n in pairs.most_common(10):
    print(f"  {n:4}  de-advertise {g:34} when {w} is the single answer")
