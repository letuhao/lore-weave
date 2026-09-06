#!/bin/bash
# QC-5 arm 1b at FIVE runs -- PO 7.3. Chapter 12: the betrayal chapter that did NOT set 2.1's
# rule, so the arm is not scored on the case it was derived from.
#
# THIS is the arm where sample size matters. C21 measured the judge at temperature 0 and found
# ZERO variance across 10 fixed-passage calls, so QC-5's recorded spread lives in the DRAFTER.
# Each run below re-drafts.
#
# HARNESS DEFECT FIXED 2026-08-21, and it is this plan's own defect class: the poll read
# `.get('status','')`, so an EXPIRED JWT returned {"detail":"invalid token"} -> '' -> "not
# finished yet", and the loop spun for the full 15 minutes on a run that had been report_ready
# for most of it. An error that is indistinguishable from "not ready" is the same shape as a
# drop that is indistinguishable from "nothing found". It now aborts, loudly, naming the cause.
set -u
SP="$1"; shift; BASE=http://localhost:28217; TOK=$(cat "$SP/qc5.jwt")
for n in "$@"; do
  RID=$(curl -s -m 30 -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
        -d @"$SP/qc5_ch12.json" "$BASE/v1/composition/authoring-runs" \
        | python -c "import json,sys
try:
    d=json.load(sys.stdin)
except Exception: print(''); raise SystemExit
if 'run_id' not in d: print('ERR:'+str(d.get('detail'))[:60]); raise SystemExit
print(d['run_id'])")
  case "$RID" in ERR:*) echo "run $n: create refused -- ${RID#ERR:}"; exit 2;; "") echo "run $n: no run_id"; exit 2;; esac
  curl -s -m 30 -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" -d '{}' \
       "$BASE/v1/composition/authoring-runs/$RID/gate" >/dev/null
  curl -s -m 30 -X POST -H "Authorization: Bearer $TOK" \
       "$BASE/v1/composition/authoring-runs/$RID/start" >/dev/null
  ST=""
  for i in $(seq 1 180); do
    ST=$(curl -s -m 15 -H "Authorization: Bearer $TOK" "$BASE/v1/composition/authoring-runs/$RID" \
         | python -c "import json,sys
try: d=json.load(sys.stdin)
except Exception: print('AUTH_OR_PARSE_ERROR'); raise SystemExit
print(d.get('status') or ('AUTH_OR_PARSE_ERROR:'+str(d.get('detail'))[:40]))")
    case "$ST" in
      AUTH_OR_PARSE_ERROR*) echo "run $n: ABORT -- status unreadable ($ST). Not 'still running'."; exit 3;;
      report_ready|closed|failed|error|cancelled|paused) break;;
    esac
    sleep 5
  done
  curl -s -m 30 -H "Authorization: Bearer $TOK" "$BASE/v1/composition/authoring-runs/$RID/report" \
    > "$SP/ch12_five_$n.json"
  python - "$SP/ch12_five_$n.json" "$n" "$ST" <<'PY'
import json,sys
try:
    d=json.load(open(sys.argv[1],encoding="utf-8")); det=(d["units"][0].get("critic_verdict") or {}).get("detail") or {}
except Exception as e:
    print(f"run {sys.argv[2]}: status={sys.argv[3]} NO REPORT ({e})", flush=True); raise SystemExit
v=det.get("violations") or []
print(f"run {sys.argv[2]}: status={sys.argv[3]} canon={det.get('canon_consistency')} "
      f"raw={det.get('violations_raw_count')} dropped={det.get('violations_dropped')} "
      f"attributed={len(v)} rules={det.get('active_rule_count')} "
      f"notes={len(det.get('craft_notes') or [])}", flush=True)
PY
  curl -s -m 20 -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" -d '{}' \
       "$BASE/v1/composition/authoring-runs/$RID/close" >/dev/null 2>&1
done
