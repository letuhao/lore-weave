"""QC-5 arm 1a at FIVE runs — PO §7.3, 2026-08-21.

§2.1 kept three runs and majority-2. That rule was retired by the measurement it produced:
chapter 12 scored `1/SEVERE` and `2/warn` on unchanged inputs, so three was the sample size
that failed to settle the question it was chosen to settle. §7.3 replaces it with **five runs,
temperature 0, seeded where the provider supports it, reporting the DISTRIBUTION**.

Temperature is already 0 on the judge (`engine/critic.py:265`). **Seeding has no plumbing in
the critic path**, so this run is UNSEEDED and says so — §7.3's own caveat is that an unseeded
five-run spread is weaker evidence than a seeded one, and writing it up as if it were seeded
would be the substitution this whole gate exists to refuse.

TWO ARMS, and the second is the point. Running only the planted arm cannot tell a
discriminating check from one that fires on everything — the C10/C11 finding. So the SAME
passage with one string changed (the invented name replaced by the canon antagonist) runs the
same five times. Planted flags + corrected clean = discrimination. Both flag = noise.

Runs on lw-iso (rule 1: code on iso; rule 6: a critique call WRITES an LLM job row, so it does
not touch the dev composition DB).
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time

JOB = "019ff423-db33-78b1-aa5f-3348e433e9c8"
URL = f"http://localhost:28217/v1/composition/jobs/{JOB}/critique"
RUNS = 5
INVENTED = "Lục Vô Tội"           # doc-language-gate: ok -- the token IS the measurement
CANON_ANTAGONIST = "Lâm Trạch"     # doc-language-gate: ok -- the token IS the measurement


def critique(token: str, passage: str) -> dict:
    r = subprocess.run(
        ["curl", "-s", "-m", "300", "-X", "POST", URL,
         "-H", f"Authorization: Bearer {token}",
         "-H", "Content-Type: application/json",
         "-d", json.dumps({"passage": passage}, ensure_ascii=False)],
        capture_output=True, text=True, encoding="utf-8")
    try:
        return json.loads(r.stdout)["critic"]
    except Exception as exc:                       # noqa: BLE001
        return {"error": f"unparsable: {exc}", "_raw": r.stdout[:200]}


def one(token: str, arm: str, passage: str, i: int) -> dict:
    t0 = time.monotonic()
    c = critique(token, passage)
    dt = time.monotonic() - t0
    row = {
        "arm": arm,
        "canon": c.get("canon_consistency"),
        "attributed": len(c.get("violations") or []),
        "raw": c.get("violations_raw_count", 0),
        "dropped": c.get("violations_dropped", 0),
        "rules": c.get("active_rule_count"),
        "error": c.get("error"),
        "secs": round(dt, 1),
    }
    print(f"  {arm:9s} #{i}  canon={row['canon']}  attributed={row['attributed']}  "
          f"raw={row['raw']}  dropped={row['dropped']}  rules={row['rules']}  "
          f"{row['secs']}s  {row['error'] or ''}", flush=True)
    return row


def spread(rows: list[dict], key: str) -> str:
    vals = [r[key] for r in rows if r[key] is not None]
    if not vals:
        return "no values"
    uniq = sorted(set(vals))
    st = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    return (f"{vals}  distinct={uniq}  "
            f"{'STABLE' if len(uniq) == 1 else 'SPREAD'}  sd={st:.2f}")


def main() -> int:
    token = open(sys.argv[1], encoding="utf-8").read().strip()
    planted = open(sys.argv[2], encoding="utf-8").read().strip()

    if INVENTED not in planted:
        raise SystemExit("the planted arm does not carry the invented betrayer — wrong file")
    # DERIVED, never read from a file. The scratchpad's arm_canon.txt LOOKS like the control
    # and is NOT one: it still carries the invented name once of three, so a run against it
    # would compare a misattributed passage with a *partly* misattributed passage and call the
    # difference discrimination. The original harness derived it too; this keeps that property
    # rather than inheriting a stale dump.
    corrected = planted.replace(INVENTED, CANON_ANTAGONIST)
    swapped = planted.count(INVENTED)
    assert INVENTED not in corrected and corrected != planted
    print(f"  control DERIVED: {swapped} occurrence(s) of the invented name swapped; the two "
          f"arms differ by that string and nothing else")

    print(f"QC-5 arm 1a — {RUNS} runs per arm, temperature 0 (judge), UNSEEDED (no plumbing)")
    print(f"  target: lw-iso {URL}\n")

    rows: list[dict] = []
    for arm, passage in (("planted", planted), ("corrected", corrected)):
        for i in range(1, RUNS + 1):
            rows.append(one(token, arm, passage, i))
        print()

    print("── DISTRIBUTION, not a number ──────────────────────────────────────────")
    for arm in ("planted", "corrected"):
        a = [r for r in rows if r["arm"] == arm]
        print(f"  {arm:9s} canon       {spread(a, 'canon')}")
        print(f"  {arm:9s} attributed  {spread(a, 'attributed')}")
        print(f"  {arm:9s} raw         {spread(a, 'raw')}")

    p = [r for r in rows if r["arm"] == "planted"]
    c = [r for r in rows if r["arm"] == "corrected"]
    p_ok = [r for r in p if (r["canon"] or 9) <= 3 and r["attributed"] >= 1]
    c_ok = [r for r in c if (r["canon"] or 0) >= 4 and r["attributed"] == 0]
    print(f"\n  1a  planted runs that flagged it   : {len(p_ok)}/{len(p)}  (majority 3 needed)")
    print(f"  CTRL corrected runs left clean     : {len(c_ok)}/{len(c)}")
    print("\n  DISCRIMINATION: " + (
        "the check separates the two arms"
        if len(p_ok) >= 3 and len(c_ok) >= 3 else
        "NOT PROVEN — it fires on both arms, or on neither"))

    out = "qc5_five_run_rows.json"
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n  rows -> {out}")
    return 0


sys.exit(main())
