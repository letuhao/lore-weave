"""Re-derive the claimed ~45x drop in missing-id failures around 2026-08-31.

The figure (7.61% -> 0.18%) is MINE, from a session summary; it is in no contract and no ledger
row, so it is a lead, not a fact. Re-derived here from the recorded corpus.

DISCIPLINE APPLIED, both learned the hard way today:
  - count DISTINCT toolCallId, never TOOL_CALL_START events (they fire twice per call)
  - numerator and denominator must be the same population: the rate is over CALLS THAT
    RETURNED A RESULT, not over runs and not over all events
"""
import collections
import glob
import json
import re

# The platform's own marker plus the shapes its refusals actually use.
PAT = re.compile(
    r"missing required argument|is required\b|must be a UUID|"
    r"missing/blank required arguments|not found or not accessible|"
    r"no .* with that id|book not accessible",
    re.I)
ID_PAT = re.compile(r"missing required argument\(s\): \[[^\]]*_id|"
                    r"'[a-z_]*_id' is required|[a-z_]*_id must be a UUID", re.I)

by_day = collections.defaultdict(lambda: collections.Counter())
by_batch = collections.defaultdict(lambda: collections.Counter())

for path in sorted(glob.glob("docs/eval/toolloop/*/*-raw.json")):
    day = path.replace("\\", "/").split("/")[-2]
    batch = path.replace("\\", "/").split("/")[-1][: -len("-raw.json")]
    try:
        recs = json.load(open(path, encoding="utf-8"))
    except Exception:
        continue
    if not isinstance(recs, list):
        continue
    for r in recs:
        if not isinstance(r, dict):
            continue
        # DISTINCT calls only
        ids = {}
        for c in (r.get("tool_calls") or []):
            if c.get("type") == "TOOL_CALL_START" and c.get("toolCallId"):
                ids[c["toolCallId"]] = c.get("toolCallName")
        results = {x.get("id"): (x.get("content") or "") for x in (r.get("results") or [])}
        for cid, name in ids.items():
            content = results.get(cid)
            if content is None:
                continue                      # no result recorded -> not in the denominator
            for d in (by_day[day], by_batch[(day, batch)]):
                d["calls_with_a_result"] += 1
                if '"ok": false' in content or '"ok":false' in content:
                    d["failed"] += 1
                    if ID_PAT.search(content):
                        d["missing_id"] += 1
                    elif PAT.search(content):
                        d["other_arg_or_lookup"] += 1

print(f"{'day':<14}{'calls':>8}{'failed':>8}{'missing_id':>12}{'rate':>9}")
for day in sorted(by_day):
    c = by_day[day]
    n = c["calls_with_a_result"]
    print(f"{day:<14}{n:>8}{c['failed']:>8}{c['missing_id']:>12}"
          f"{(c['missing_id']/n if n else 0):>8.2%}")

print("\nPER BATCH around the claimed transition (2026-08-30 .. 2026-09-02):")
for (day, batch), c in sorted(by_batch.items()):
    if day < "2026-08-30":
        continue
    n = c["calls_with_a_result"]
    if n < 5:
        continue
    print(f"   {day}  {batch:<34} calls {n:>4}  missing_id {c['missing_id']:>3}  "
          f"{(c['missing_id']/n if n else 0):>7.2%}")
