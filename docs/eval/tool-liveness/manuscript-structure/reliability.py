#!/usr/bin/env python
"""Effectiveness / reliability: repeat the newly-enabled authoring scenarios N times on the UNIFIED
surface and report the DB-verified pass rate + token cost. Answers 'does it REALLY work effectively?'"""
import sys, os, importlib.util, statistics

here = os.path.dirname(os.path.abspath(sys.argv[0]))
spec = importlib.util.spec_from_file_location("sab", os.path.join(here, "structure_ab.py"))
sab = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0], sys.argv[1]]  # structure_ab reads TOKEN from argv[1]
spec.loader.exec_module(sab)

N = 5
targets = [s for s in sab.SCENARIOS if s[0] in ("create+move", "reorder_chapters", "rename_part")]
print(f"UNIFIED reliability, N={N} each\n")
for name, prompt, verify, flag in targets:
    passes, tin, tout = 0, [], []
    for i in range(N):
        sab.reset()
        r = sab.run_scenario("unified", prompt)
        ok, detail = verify(r["final"])
        passes += 1 if ok else 0
        tin.append(r["tok_in"]); tout.append(r["tok_out"])
        print(f"  {name:16} run{i+1}: {'PASS' if ok else 'FAIL':4} calls={[c['tool'] for c in r['calls']]} tok={r['tok_in']}/{r['tok_out']} {'' if ok else detail}")
    print(f"  >> {name}: {passes}/{N} PASS  mean_tok_in={int(statistics.mean(tin))} mean_tok_out={int(statistics.mean(tout))}\n")
sab.reset()
