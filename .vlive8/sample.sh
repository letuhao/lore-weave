#!/bin/bash
# Sample the newest rows of the session at high frequency during a live turn,
# specifically looking for the reconciler's two predicates on a LIVE row:
#   assistant: outcome IS NULL AND finish_reason='streaming'
#   user:      outcome IS NULL AND no later assistant row
S=019fcc55-683c-7c0f-8450-3b51e2b7c193
for i in $(seq 1 240); do
  docker exec infra-postgres-1 psql -U loreweave -d loreweave_chat -tAc "
    SELECT now()::time(3)||' seq='||sequence_num||' '||role
        ||' outcome='||coalesce(outcome,'NULL')
        ||' fr='||coalesce(finish_reason,'NULL')
        ||' ASSISTANT_PREDICATE_HIT='||(role='assistant' AND outcome IS NULL AND finish_reason='streaming')::text
        ||' USER_PREDICATE_HIT='||(role='user' AND outcome IS NULL AND NOT EXISTS(
              SELECT 1 FROM chat_messages a WHERE a.session_id=m.session_id AND a.role='assistant'
              AND a.sequence_num>m.sequence_num))::text
    FROM chat_messages m WHERE session_id='$S' AND sequence_num>11 ORDER BY sequence_num;"
done
