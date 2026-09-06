#!/usr/bin/env bash
# THE CONTROL THAT WOULD REFUTE CYCLE 2'S FIX. Run ONLY when no batch is in flight — it rebuilds
# chat-service, and rebuilding underneath a running batch invalidates its runs.
#
# Removes the MISSING-ARGUMENT arming arm only (the dispatch-path arming stays), rebuilds, runs
# scenarios-c2-motif.json at K=5, then restores the file from an in-memory copy and rebuilds back.
# Never `git checkout` — that would discard unrelated edits in the same file.
set -euo pipefail
cd "$(dirname "$0")/../.."
SRC=services/chat-service/app/services/stream_service.py
BAK=$(mktemp); cp "$SRC" "$BAK"
restore() { cp "$BAK" "$SRC"; (cd infra && docker compose build chat-service >/dev/null && \
            docker compose up -d --force-recreate chat-service >/dev/null); echo "restored + redeployed"; }
trap restore EXIT

python - <<'PY'
import pathlib
p=pathlib.Path("services/chat-service/app/services/stream_service.py")
s=p.read_text(encoding="utf-8")
a=s.find("                    # ── D-REFUSAL-NAMES-A-TOOL-THE-TURN-CANNOT-SEE")
b=s.find("                    working.append({", a)
assert a>0 and b>a, "anchors moved — retarget this control"
p.write_text(s[:a]+s[b:],encoding="utf-8")
print("missing-argument arming REMOVED for the control")
PY

(cd infra && docker compose build chat-service && docker compose up -d --force-recreate chat-service)
python scripts/toolloop/fe_runner.py scripts/toolloop/scenarios-c2-motif.json \
  --repeats 5 --concurrency 1 --turn-timeout 600 --batch-id c2-motif-noarm \
  --out docs/eval/toolloop/2026-08-14/c2-motif-noarm-raw.json \
  --batch-out docs/eval/toolloop/2026-08-14/c2-motif-noarm.json
