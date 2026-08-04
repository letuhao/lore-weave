#!/bin/bash
S=019fcc55-683c-7c0f-8450-3b51e2b7c193
for i in $(seq 1 3000); do
  N=$(docker exec infra-postgres-1 psql -U loreweave -d loreweave_chat -tAc "SELECT count(*) FROM chat_messages WHERE session_id='$S' AND sequence_num>=14;")
  if [ "$N" != "0" ]; then
    date -u +"%Y-%m-%dT%H:%M:%S.%3NZ KILLING"
    docker kill infra-chat-service-1
    date -u +"%Y-%m-%dT%H:%M:%S.%3NZ KILLED"
    docker exec infra-postgres-1 psql -U loreweave -d loreweave_chat -c "SELECT sequence_num, role, outcome, finish_reason, coalesce(jsonb_array_length(tool_calls),0) tc, created_at FROM chat_messages WHERE session_id='$S' AND sequence_num>=14 ORDER BY sequence_num;"
    exit 0
  fi
done
echo TIMEOUT
