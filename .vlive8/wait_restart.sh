#!/bin/bash
S=019fcc55-683c-7c0f-8450-3b51e2b7c193
# wait until row 14 is older than 5 minutes
until [ "$(docker exec infra-postgres-1 psql -U loreweave -d loreweave_chat -tAc "SELECT (now()-created_at > interval '5 minutes 20 seconds') FROM chat_messages WHERE session_id='$S' AND sequence_num=14;")" = "t" ]; do sleep 5; done
echo "row 14 now past the age bound at $(date -u +%H:%M:%S)"
docker exec infra-postgres-1 psql -U loreweave -d loreweave_chat -c "SELECT sequence_num, role, outcome, now()-created_at AS age FROM chat_messages WHERE session_id='$S' AND sequence_num=14;"
echo "=== RESTART 2 ==="
docker compose -f D:/Works/source/lore-weave/infra/docker-compose.yml up -d --force-recreate --no-deps chat-service 2>&1 | tail -2
until [ "$(docker inspect -f '{{.State.Health.Status}}' infra-chat-service-1)" = "healthy" ]; do sleep 3; done
echo "healthy at $(date -u +%H:%M:%S)"
echo "=== reconciler log ==="
docker logs --since 2m infra-chat-service-1 2>&1 | grep -i reconciler || echo "(none)"
echo "=== row 14 after RESTART 2 ==="
docker exec infra-postgres-1 psql -U loreweave -d loreweave_chat -c "SELECT sequence_num, role, outcome, finish_reason, now()-created_at AS age FROM chat_messages WHERE session_id='$S' AND sequence_num=14;"
