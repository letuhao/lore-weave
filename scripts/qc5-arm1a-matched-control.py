"""QC-5 arm 1a on CHAPTER 12's OWN DRAFT — the matched half C23 said was missing.

C23 measured arm 1b (five authoring runs on ch12) and got 5/5 canon=5, raw=0. The gate refused
it: `1a needs 5 planted runs, got 0`, and clause 2 called five perfect scores with nothing found
*indistinguishable from the defect signature*. C21 had a planted arm, but on a DIFFERENT passage
— so combining them would have manufactured a verdict from mismatched inputs.

This closes that gap the only honest way: the planted arm is built from **the very draft the flow
arm produced** (revision `01a024e9-…`, run A), with the canon antagonist replaced by an invented
name. Same chapter, same project, same rules.  `doc-language-gate: ok -- the swapped NAME
is the measurement; the arms differ by that string and nothing else`

THREE ARMS:
  planted    ch12's draft with `Lâm Trạch` -> `Lục Vô Tội` (0 canon entities) — the betrayal is
             now attributed to someone who does not exist. The critic MUST notice.
  clean      ch12's draft exactly as the flow produced it — the specificity control. If this
             scores the same as `planted`, the check is not discriminating and the planted
             result means nothing.
  (flow)     already measured in C23, five authoring runs.

Runs on lw-iso. `doc-language-gate: ok -- the names ARE the measurement.`
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys

JOB = "019ff423-db33-78b1-aa5f-3348e433e9c8"
URL = f"http://localhost:28217/v1/composition/jobs/{JOB}/critique"
RUNS = 5
CANON_ANTAGONIST = "Lâm Trạch"
INVENTED = "Lục Vô Tội"


def critique(token: str, passage: str) -> dict:
    r = subprocess.run(
        ["curl", "-s", "-m", "300", "-X", "POST", URL,
         "-H", f"Authorization: Bearer {token}",
         "-H", "Content-Type: application/json",
         "-d", json.dumps({"passage": passage}, ensure_ascii=False)],
        capture_output=True, text=True, encoding="utf-8")
    try:
        body = json.loads(r.stdout)
    except Exception as exc:                       # noqa: BLE001
        return {"error": f"unparsable: {exc}", "_raw": r.stdout[:160]}
    # An auth failure must NOT read as a clean critique. This is the harness defect C23 caught
    # in its own poller, one layer over: `{"detail": "invalid token"}` has no `critic` key, and
    # `.get("critic", {})` would have turned it into canon=None with zero violations.
    if "critic" not in body:
        return {"error": f"no critic in response: {str(body)[:120]}"}
    return body["critic"]


def spread(vals: list) -> str:
    vals = [v for v in vals if v is not None]
    if not vals:
        return "no values"
    st = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    return f"{vals} distinct={sorted(set(vals))} {'STABLE' if len(set(vals)) == 1 else 'SPREAD'} sd={st:.2f}"


def main() -> int:
    token = open(sys.argv[1], encoding="utf-8").read().strip()
    clean = open(sys.argv[2], encoding="utf-8").read().strip()

    n = clean.count(CANON_ANTAGONIST)
    if n == 0:
        raise SystemExit("this draft never names the canon antagonist — nothing to misattribute")
    planted = clean.replace(CANON_ANTAGONIST, INVENTED)
    assert CANON_ANTAGONIST not in planted and planted != clean
    print(f"ch12 draft {len(clean)} chars; planted arm swaps {n} occurrence(s) of "
          f"{CANON_ANTAGONIST!r} -> {INVENTED!r}; the two arms differ by that string alone\n")

    rows: list[dict] = []
    for arm, passage in (("planted", planted), ("clean", clean)):
        for i in range(1, RUNS + 1):
            c = critique(token, passage)
            row = {"arm": arm, "canon": c.get("canon_consistency"),
                   "attributed": len(c.get("violations") or []),
                   "raw": c.get("violations_raw_count", 0),
                   "rules": c.get("active_rule_count"), "error": c.get("error")}
            rows.append(row)
            print(f"  {arm:8s} #{i}  canon={row['canon']}  attributed={row['attributed']}  "
                  f"raw={row['raw']}  rules={row['rules']}  {row['error'] or ''}", flush=True)
        print()

    for arm in ("planted", "clean"):
        a = [r for r in rows if r["arm"] == arm]
        print(f"  {arm:8s} canon      {spread([r['canon'] for r in a])}")
        print(f"  {arm:8s} attributed {spread([r['attributed'] for r in a])}")

    p = [r for r in rows if r["arm"] == "planted"]
    c = [r for r in rows if r["arm"] == "clean"]
    p_ok = sum(1 for r in p if (r["canon"] or 9) <= 3 and r["attributed"] >= 1)
    c_ok = sum(1 for r in c if (r["canon"] or 0) >= 4 and r["attributed"] == 0)
    print(f"\n  1a  planted runs flagging it : {p_ok}/{len(p)}  (majority 3)")
    print(f"  CTRL clean runs left alone   : {c_ok}/{len(c)}")

    out = sys.argv[3] if len(sys.argv) > 3 else "qc5_ch12_arms.json"
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n  rows -> {out}")
    return 0


sys.exit(main())
