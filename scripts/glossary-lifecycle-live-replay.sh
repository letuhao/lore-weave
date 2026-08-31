#!/usr/bin/env bash
# glossary-lifecycle-live-replay — carry a lifecycle/curation event end-to-end (plan
# D-T27-LIVE-REPLAY, extended to T28's event).
#
# WHY THIS EXISTS
# ---------------
# T27 and T28 each proved their halves separately: the Go suite asserts real `outbox_events`
# rows on a live Postgres, and the Python suite asserts which archive/restore call each handler
# makes. Neither touches the leg BETWEEN them — worker-infra's relay reading the row, shipping
# it to the Redis stream, and knowledge-service's dispatcher routing it to a handler that
# writes Neo4j. That is exactly where a payload-shape mismatch first appears, and a mismatch
# there is silent: the relay ships, the consumer shrugs, and nothing anywhere goes red.
#
# The dev stack agreed. Before this ran, `glossary.entity_deleted` had a lifetime count of ZERO
# rows in the dev outbox — the T27 events had never once flowed through this stack.
#
# ISOLATION
# ---------
# The dev Postgres and Neo4j hold real data, so this writes only under a SYNTHETIC tenant: a
# generated user_id/project_id/book_id/entity_id that no real row references. Every Neo4j query
# in this schema is scoped `WHERE e.user_id = $user_id`, so a node under a generated user is
# unreachable from any real read. Everything it creates is removed on exit, including on
# failure (see the trap).
#
#   ./scripts/glossary-lifecycle-live-replay.sh
#
# Exit 0 = the events crossed all three legs · 1 = a leg dropped them.

set -uo pipefail

PG=infra-postgres-1
NEO=infra-neo4j-1
REDIS=infra-redis-1
NEO_PW="${NEO4J_PASSWORD:-loreweave_dev_neo4j}"
export MSYS_NO_PATHCONV=1

# python, not uuidgen — Git Bash on Windows has no uuidgen, and the first run of this script
# discovered that by generating four EMPTY ids. The setup failed loudly, but the cleanup trap
# then ran `MATCH (e:Entity {user_id: ''}) DETACH DELETE e` against the dev graph. Nothing
# matched, and nothing about that was by design. Hence the guard below: this script deletes by
# tenant id, so an unset tenant id must stop it before it can delete by a predicate that means
# something other than what it says.
newid() { python -c "import uuid;print(uuid.uuid4())"; }
USER_ID=$(newid)
PROJECT_ID=$(newid)
BOOK_ID=$(newid)
ENTITY_ID=$(newid)
NODE_ID="replay-node-${ENTITY_ID}"

_UUID_RE='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
for _v in "$USER_ID" "$PROJECT_ID" "$BOOK_ID" "$ENTITY_ID"; do
  [[ "$_v" =~ $_UUID_RE ]] || {
    echo "FAIL(setup): generated a non-UUID tenant id ('${_v}') — refusing to run," >&2
    echo "  because every cleanup in this script deletes BY tenant id." >&2
    exit 2
  }
done

FAIL=0
note() { printf '\n=== %s\n' "$*"; }
ok()   { printf '  PASS  %s\n' "$*"; }
bad()  { printf '  FAIL  %s\n' "$*"; FAIL=1; }

psql_k() { docker exec "$PG" psql -U loreweave -d loreweave_knowledge -t -A -c "$1"; }
psql_g() { docker exec "$PG" psql -U loreweave -d loreweave_glossary -t -A -c "$1"; }
cypher() { docker exec "$NEO" cypher-shell -u neo4j -p "$NEO_PW" --format plain "$1"; }

cleanup() {
  note "cleanup — removing the synthetic tenant"
  cypher "MATCH (e:Entity {user_id: '$USER_ID'}) DETACH DELETE e;" >/dev/null 2>&1
  psql_k "DELETE FROM knowledge_projects WHERE user_id='$USER_ID';" >/dev/null 2>&1
  psql_g "DELETE FROM outbox_events WHERE aggregate_id='$ENTITY_ID';" >/dev/null 2>&1
  echo "  synthetic user $USER_ID removed"
}
trap cleanup EXIT

# `emit` writes the row the producer writes. The payload is copied from what
# `setEntityStatusCore` / `mutateEntityLifecycleTx` actually produced against a live Postgres
# in the Go suite — same keys, same order, same types. Hand-writing a DIFFERENT shape here
# would prove the relay can carry a message this script invented, which is not the question.
emit() {
  local event_type="$1" payload="$2"
  psql_g "INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
          VALUES ('glossary', '$ENTITY_ID', '$event_type', '$payload'::jsonb);" >/dev/null
}

# Poll rather than sleep-and-hope: the relay and the consumer are independent loops, and a
# fixed sleep either flakes or wastes time. 30 s is generous for a local stack.
await() {
  local label="$1" query="$2" want="$3" tries=60 got=""
  while [ $tries -gt 0 ]; do
    got=$(cypher "$query" 2>/dev/null | tail -n +2 | tr -d '"' | tr -d '\r' | head -1)
    [ "$got" = "$want" ] && { ok "$label (${got})"; return 0; }
    tries=$((tries - 1)); sleep 0.5
  done
  bad "$label — wanted '$want', Neo4j still reports '${got:-<nothing>}' after 30s"
  return 1
}

note "setup — synthetic tenant"
echo "  user=$USER_ID book=$BOOK_ID entity=$ENTITY_ID"
psql_k "INSERT INTO knowledge_projects (project_id, user_id, name, project_type, book_id)
        VALUES ('$PROJECT_ID', '$USER_ID', 'T28 replay', 'book', '$BOOK_ID');" >/dev/null \
  || { echo "FAIL(setup): could not create the knowledge project"; exit 2; }

cypher "CREATE (e:Entity {
          id: '$NODE_ID', user_id: '$USER_ID', project_id: '$PROJECT_ID',
          glossary_entity_id: '$ENTITY_ID', name: 'Replay Subject', canonical_name: 'replay subject',
          kind: 'character', aliases: [], short_description: '', confidence: 1.0,
          source_type: 'glossary', source_types: ['glossary'], canonical_version: 1,
          anchor_score: 1.0, evidence_count: 0, mention_count: 0,
          archived_at: NULL, created_at: datetime(), updated_at: datetime()});" >/dev/null \
  || { echo "FAIL(setup): could not create the KG node"; exit 2; }
ok "KG node created, un-archived and anchored"

STREAM_BEFORE=$(docker exec "$REDIS" redis-cli XLEN loreweave:events:glossary | tr -d '\r')

# ── Leg 1+2+3: retire the entity (T28) ───────────────────────────────────────
note "T28 — glossary.entity_status_changed (active → rejected) must ARCHIVE the node"
emit "glossary.entity_status_changed" \
  "{\"status\": \"rejected\", \"book_id\": \"$BOOK_ID\", \"actor_type\": \"user\", \"actor_id\": \"$USER_ID\", \"emitted_at\": \"2026-08-10T12:00:00Z\", \"prior_status\": \"active\", \"glossary_entity_id\": \"$ENTITY_ID\"}"

await "node archived" \
  "MATCH (e:Entity {user_id: '$USER_ID'}) RETURN CASE WHEN e.archived_at IS NULL THEN 'live' ELSE 'archived' END AS s;" \
  "archived"

# The REASON is the load-bearing half: the restore paths are scoped by it, so an archive that
# lands with the wrong reason is an archive nothing can correctly undo.
REASON=$(cypher "MATCH (e:Entity {user_id: '$USER_ID'}) RETURN e.archive_reason AS r;" 2>/dev/null | tail -n +2 | tr -d '"\r' | head -1)
[ "$REASON" = "glossary_status_rejected" ] \
  && ok "archive_reason = $REASON" \
  || bad "archive_reason — wanted glossary_status_rejected, got '${REASON:-<null>}'"

# `user_archive_entity`, not `archive_entity`: the anchor must SURVIVE a status retirement, or
# the next content edit MERGEs a second, un-archived twin of the node.
ANCHOR=$(cypher "MATCH (e:Entity {user_id: '$USER_ID'}) RETURN coalesce(e.glossary_entity_id, 'NULL') AS g;" 2>/dev/null | tail -n +2 | tr -d '"\r' | head -1)
[ "$ANCHOR" = "$ENTITY_ID" ] \
  && ok "glossary anchor preserved through the status archive" \
  || bad "glossary anchor — wanted $ENTITY_ID, got '$ANCHOR' (a status archive must not sever it)"

STREAM_AFTER=$(docker exec "$REDIS" redis-cli XLEN loreweave:events:glossary | tr -d '\r')
[ "$STREAM_AFTER" -gt "$STREAM_BEFORE" ] \
  && ok "relay shipped to loreweave:events:glossary ($STREAM_BEFORE → $STREAM_AFTER)" \
  || bad "relay did not grow the stream ($STREAM_BEFORE → $STREAM_AFTER)"

# ── The boundary between the two axes ────────────────────────────────────────
note "T27/T28 boundary — a recycle-bin restore must NOT un-archive a rejected entity"
emit "glossary.entity_restored" \
  "{\"op\": \"restored\", \"book_id\": \"$BOOK_ID\", \"actor_type\": \"user\", \"actor_id\": \"$USER_ID\", \"emitted_at\": \"2026-08-10T12:00:05Z\", \"glossary_entity_id\": \"$ENTITY_ID\"}"
sleep 6
STILL=$(cypher "MATCH (e:Entity {user_id: '$USER_ID'}) RETURN CASE WHEN e.archived_at IS NULL THEN 'live' ELSE 'archived' END AS s;" 2>/dev/null | tail -n +2 | tr -d '"\r' | head -1)
[ "$STILL" = "archived" ] \
  && ok "still archived — the delete axis did not steal the status axis's un-archive" \
  || bad "a recycle-bin restore un-archived a REJECTED entity (reason-scoping is not holding)"

# ── Reinstate ────────────────────────────────────────────────────────────────
note "T28 — glossary.entity_status_changed (rejected → active) must UN-ARCHIVE the node"
emit "glossary.entity_status_changed" \
  "{\"status\": \"active\", \"book_id\": \"$BOOK_ID\", \"actor_type\": \"user\", \"actor_id\": \"$USER_ID\", \"emitted_at\": \"2026-08-10T12:00:10Z\", \"prior_status\": \"rejected\", \"glossary_entity_id\": \"$ENTITY_ID\"}"
await "node un-archived" \
  "MATCH (e:Entity {user_id: '$USER_ID'}) RETURN CASE WHEN e.archived_at IS NULL THEN 'live' ELSE 'archived' END AS s;" \
  "live"

# ── T27's own event, which had never flowed ──────────────────────────────────
note "T27 — glossary.entity_deleted must ARCHIVE and SEVER the anchor"
emit "glossary.entity_deleted" \
  "{\"op\": \"deleted\", \"book_id\": \"$BOOK_ID\", \"actor_type\": \"user\", \"actor_id\": \"$USER_ID\", \"emitted_at\": \"2026-08-10T12:00:15Z\", \"glossary_entity_id\": \"$ENTITY_ID\"}"
await "node archived by the delete" \
  "MATCH (e:Entity {user_id: '$USER_ID'}) RETURN CASE WHEN e.archived_at IS NULL THEN 'live' ELSE 'archived' END AS s;" \
  "archived"
BREADCRUMB=$(cypher "MATCH (e:Entity {user_id: '$USER_ID'}) RETURN coalesce(e.prior_glossary_entity_id,'NULL') AS p;" 2>/dev/null | tail -n +2 | tr -d '"\r' | head -1)
[ "$BREADCRUMB" = "$ENTITY_ID" ] \
  && ok "prior_glossary_entity_id breadcrumb left for the restore to match" \
  || bad "breadcrumb missing — a restore would find no node and silently succeed"

note "T27 — glossary.entity_purged must REMOVE the node"
emit "glossary.entity_purged" \
  "{\"op\": \"purged\", \"book_id\": \"$BOOK_ID\", \"actor_type\": \"user\", \"actor_id\": \"$USER_ID\", \"emitted_at\": \"2026-08-10T12:00:20Z\", \"glossary_entity_id\": \"$ENTITY_ID\"}"
await "node gone" \
  "MATCH (e:Entity {user_id: '$USER_ID'}) RETURN count(e) AS n;" \
  "0"

note "result"
[ $FAIL -eq 0 ] && echo "  ALL LEGS GREEN — outbox → relay → Redis → dispatcher → Neo4j" \
                || echo "  SOME LEGS FAILED (see FAIL above)"
exit $FAIL
