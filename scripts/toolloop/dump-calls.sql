-- Recorded tool calls for the deep-dive loop's group A/B/C ordering.
--   docker exec infra-postgres-1 psql -U loreweave -d loreweave_chat -At -F '\t' \
--     -f - < scripts/toolloop/dump-calls.sql > "$TOOLLOOP_WORKDIR/calls_ts.tsv"
--
-- THE FAILURE PREDICATE IS `error IS NOT NULL`, NOT `ok = false`. Two distinct things set
-- ok=false while the tool is working exactly as designed, and both were measured on 2026-08-13:
--
--   1. A GATED PROPOSAL. A Tier-A/W call that mints a confirm card records
--      ok=false, error=null, task.status='input_required'. Counting those made
--      glossary_propose_curation read as 72 failures in 72 calls; the ledger's own recorded
--      figure for that tool is 29 in 72, and `error IS NOT NULL` reproduces 29 exactly. That
--      agreement is the control for this predicate — if it stops holding, the predicate drifted.
--
--   2. AN OPERATOR DECISION. `denied by user` (23 corpus-wide) is the author pressing Deny on
--      an approval card. The tool never ran, so it cannot have failed. Left in, it put
--      kg_add_nodes at the HEAD of group A on the strength of a single denial — ranking a tool
--      for investigation because its safety gate worked.
--
-- Kept as failures on purpose: the "You have already called X this turn" repeat-guard family
-- (chat-service, stream_service.py). Those are turn-level refusals rather than tool faults, but
-- unlike a denial they signal a real read-then-act loop, and the tool genuinely did not run.
-- They only ever affect the TOTAL-failure tiebreak, never the live count, because the guard's
-- message is emitted by chat-service and every recorded instance long predates its last commit.
select e->>'tool',
       to_char(m.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS'),
       case when e->>'error' is null then 'ok'
            when e->>'error' = 'denied by user' then 'ok'
            else 'failed' end
from chat_messages m, lateral jsonb_array_elements(m.tool_calls) e
where jsonb_typeof(m.tool_calls) = 'array' and e ? 'tool'
order by m.created_at;
