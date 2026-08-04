#!/bin/bash
# Fire docker kill the instant sequence_num >= 11 user row appears in the session.
S=019fcc55-683c-7c0f-8450-3b51e2b7c193
for i in $(seq 1 600); do
  N=$(docker exec infra-postgres-1 psql -U loreweave -d loreweave_chat -tAc "SELECT count(*) FROM chat_messages WHERE session_id='$S' AND sequence_num>=11;")
  if [ "$N" != "0" ]; then
    date -u +"%Y-%m-%dT%H:%M:%S.%3NZ KILLING (rows>=11: $N)"
    docker kill infra-chat-service-1
    date -u +"%Y-%m-%dT%H:%M:%S.%3NZ KILLED"
    docker exec infra-postgres-1 psql -U loreweave -d loreweave_chat -c "SELECT sequence_num, role, outcome, finish_reason, coalesce(jsonb_array_length(tool_calls),0) tc, left(content,40) c FROM chat_messages WHERE session_id='$S' AND sequence_num>=9 ORDER BY sequence_num;"
    exit 0
  fi
done
echo "TIMEOUT - no new row"
