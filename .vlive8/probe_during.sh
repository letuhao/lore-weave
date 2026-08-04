#!/bin/bash
S=019fcc55-683c-7c0f-8450-3b51e2b7c193
# wait for a new user row (seq>11) to appear, then immediately probe
for i in $(seq 1 3000); do
  N=$(docker exec infra-postgres-1 psql -U loreweave -d loreweave_chat -tAc "SELECT count(*) FROM chat_messages WHERE session_id='$S' AND sequence_num>11;")
  if [ "$N" != "0" ]; then
    echo "=== live turn detected at $(date -u +%H:%M:%S.%3N) ==="
    echo ">>> PROBE 1: default age bound (5 min) against a LIVE turn"
    MSYS_NO_PATHCONV=1 docker exec infra-chat-service-1 python //app/recon_probe.py 5
    echo
    echo ">>> PROBE 2: age bound DISABLED (0 min) against the SAME live turn"
    MSYS_NO_PATHCONV=1 docker exec infra-chat-service-1 python //app/recon_probe.py 0
    exit 0
  fi
done
echo TIMEOUT
