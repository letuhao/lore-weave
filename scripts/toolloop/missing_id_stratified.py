"""Is the missing-id decline a real effect, or a change in what the batches RUN?

The pooled rate falls 6.36% -> 3.74% -> 2.68% -> 0.00% -> 0.38% across five dates. But
2026-08-14 was a broad 4,936-call sweep and the later days are targeted batches, so a pooled
comparison across them can be pure composition change -- the exact failure recorded in
`feedback_a_pooled_rate_across_a_triggerless_population_is_diluted`.

STRATIFY: compare only TOOLS that appear on BOTH sides of the transition, and only calls that
returned a result. If the same tools improved, something landed. If the later corpus simply
stopped calling the tools that used to fail, nothing did.
"""
import collections
import glob
import json
import re

ID_PAT = re.compile(r"missing required argument\(s\): \[[^\]]*_id|"
                    r"'[a-z_]*_id' is required|[a-z_]*_id must be a UUID", re.I)
CUT = "2026-08-30"          # before < CUT <= after

era = {"before": collections.defaultdict(collections.Counter),
       "after": collections.defaultdict(collections.Counter)}

for path in sorted(glob.glob("docs/eval/toolloop/*/*-raw.json")):
    day = path.replace("\\", "/").split("/")[-2]
    side = "before" if day < CUT else "after"
    try:
        recs = json.load(open(path, encoding="utf-8"))
    except Exception:
        continue
    if not isinstance(recs, list):
        continue
    for r in recs:
        if not isinstance(r, dict):
            continue
        ids = {c["toolCallId"]: c.get("toolCallName")
               for c in (r.get("tool_calls") or [])
               if c.get("type") == "TOOL_CALL_START" and c.get("toolCallId")}
        results = {x.get("id"): (x.get("content") or "") for x in (r.get("results") or [])}
        for cid, name in ids.items():
            content = results.get(cid)
            if content is None or not name:
                continue
            e = era[side][name]
            e["calls"] += 1
            if ('"ok": false' in content or '"ok":false' in content) and ID_PAT.search(content):
                e["missing_id"] += 1

shared = [t for t in era["before"]
          if t in era["after"] and era["before"][t]["calls"] >= 10
          and era["after"][t]["calls"] >= 10]

def rate(side, tools):
    c = sum(era[side][t]["calls"] for t in tools)
    m = sum(era[side][t]["missing_id"] for t in tools)
    return m, c, (m / c if c else 0)

print(f"tools seen >=10 times on BOTH sides of {CUT}: {len(shared)}")
mb, cb, rb = rate("before", shared)
ma, ca, ra = rate("after", shared)
print(f"   BEFORE  {mb:>4} missing_id / {cb:>5} calls   {rb:.2%}")
print(f"   AFTER   {ma:>4} missing_id / {ca:>5} calls   {ra:.2%}")
print(f"   -> {'no change' if rb == 0 else f'{rb/ra:.1f}x lower' if ra else 'to ZERO'}")

print("\nThe tools that carried the BEFORE failures, and what they did after:")
rows = sorted(shared, key=lambda t: -era["before"][t]["missing_id"])
for t in rows[:15]:
    b, a = era["before"][t], era["after"][t]
    if b["missing_id"] == 0:
        continue
    print(f"   {t:<42} before {b['missing_id']:>3}/{b['calls']:<5}"
          f"({b['missing_id']/b['calls']:>6.1%})   after {a['missing_id']:>3}/{a['calls']:<5}"
          f"({a['missing_id']/a['calls']:>6.1%})")

# The composition question, asked directly.
only_before = [t for t in era["before"] if t not in era["after"]
               and era["before"][t]["missing_id"] > 0]
mob = sum(era["before"][t]["missing_id"] for t in only_before)
tot_before = sum(era["before"][t]["missing_id"] for t in era["before"])
print(f"\nCOMPOSITION CHECK -- of {tot_before} missing_id failures before {CUT}, "
      f"{mob} ({mob/tot_before:.0%}) are on tools the later corpus NEVER CALLS AGAIN.")
print(f"   ({len(only_before)} such tools)")
for t in sorted(only_before, key=lambda x: -era["before"][x]["missing_id"])[:8]:
    print(f"      {t:<44} {era['before'][t]['missing_id']:>3} failures, then never called")
