#!/usr/bin/env bash
# glossary-lifecycle-live-smoke — QC-4, the emit-wiring proof that catches a BYPASS.
#
# WHY THIS EXISTS, AND WHY IT IS NOT THE REPLAY SCRIPT
# ----------------------------------------------------
# `glossary-lifecycle-live-replay.sh` (D-T27-LIVE-REPLAY) INSERTS the outbox row itself and
# then watches it cross the relay. That proves the transport. It cannot prove the producer:
# if you deleted the emit from `softDeleteEntityCore` tomorrow, the replay would still pass,
# because the replay is the thing writing the row.
#
# QC-4 is the other half. Nothing here writes an outbox row. A real HTTP DELETE goes to the
# real route, `*Core` emits or it does not, and every assertion below hangs off that. That is
# what makes the task's bite — *revert one `*Core`'s outbox write* — able to turn this red.
#
# The plan's reason for demanding it: "an emit test that asserts the outbox row proves the
# row, not the delivery. The register records three bugs that were declared closed and were
# not — all three were emit/consume gaps."
#
# EVERY ABSENCE IS PAIRED WITH A PRESENCE
# ---------------------------------------
# "The entity is absent from the cast after the delete" is worth nothing on its own — an
# entity that was never in the cast, a service that is down, a book id that matches nothing,
# and a working delete all produce the identical observation. So each consumer leg runs
# BEFORE the delete and must find the entity, then again after. A leg whose "before" fails is
# reported as a setup failure, never as a pass.
#
# WHAT IT WRITES
# --------------
# The dev databases hold real data. This script only ever INSERTs rows it mints itself and
# deletes them on exit, including on failure; it never UPDATEs or DELETEs a pre-existing row.
# The one entity it soft-deletes is the scratch entity it created seconds earlier. This is the
# same contract `entity-lifecycle-guards-live-smoke.sh` already runs under.
#
#   ./scripts/glossary-lifecycle-live-smoke.sh
#
# Exit 0 = every consumer observed the effect · 1 = a consumer did not · 2 = setup failed.

set -uo pipefail

GLOSSARY_CONTAINER="${GLOSSARY_CONTAINER:-infra-glossary-service-1}"
KNOWLEDGE_CONTAINER="${KNOWLEDGE_CONTAINER:-infra-knowledge-service-1}"
PG_CONTAINER="${PG_CONTAINER:-infra-postgres-1}"
NEO_CONTAINER="${NEO_CONTAINER:-infra-neo4j-1}"
REDIS_CONTAINER="${REDIS_CONTAINER:-infra-redis-1}"
PG_USER="${PG_USER:-loreweave}"
GLOSSARY_DB="${GLOSSARY_DB:-loreweave_glossary}"
BOOK_DB="${BOOK_DB:-loreweave_book}"
TRANSLATION_DB="${TRANSLATION_DB:-loreweave_translation}"
KNOWLEDGE_DB="${KNOWLEDGE_DB:-loreweave_knowledge}"
GLOSSARY_URL="${GLOSSARY_URL:-http://localhost:8211}"
# Resolved from the running stack, not guessed. 8210 is TRANSLATION-service; pointing the
# `<facts>` probe there would have got a clean 404 that reads exactly like "the entity is
# absent", which is the answer this smoke is trying to earn honestly.
KNOWLEDGE_URL="${KNOWLEDGE_URL:-http://localhost:8216}"
# The KAL is knowledge-gateway (composition's `settings.knowledge_gateway_url`), published
# on 3210 — composition's cast read must be probed through the same door composition uses.
KAL_URL="${KAL_URL:-http://localhost:3210}"
NEO_PW="${NEO4J_PASSWORD:-loreweave_dev_neo4j}"
STREAM="loreweave:events:glossary"
export MSYS_NO_PATHCONV=1

pass=0; fail=0
log()  { printf '[qc4] %s\n' "$*"; }
ok()   { pass=$((pass+1)); printf '[qc4] PASS  %s\n' "$*"; }
bad()  { fail=$((fail+1)); printf '[qc4] FAIL  %s\n' "$*"; }
die()  { printf '[qc4] FAIL(setup): %s\n' "$*"; exit 2; }
note() { printf '\n[qc4] ---- %s ----\n' "$*"; }

gq() { docker exec -i "$PG_CONTAINER" psql -qtAX -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$GLOSSARY_DB"    -c "$1" | tr -d '\r'; }
bq() { docker exec -i "$PG_CONTAINER" psql -qtAX -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$BOOK_DB"        -c "$1" | tr -d '\r'; }
tq() { docker exec -i "$PG_CONTAINER" psql -qtAX -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$TRANSLATION_DB" -c "$1" | tr -d '\r'; }
kq() { docker exec -i "$PG_CONTAINER" psql -qtAX -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$KNOWLEDGE_DB"   -c "$1" | tr -d '\r'; }
cy() { docker exec "$NEO_CONTAINER" cypher-shell -u neo4j -p "$NEO_PW" --format plain "$1" 2>/dev/null | tail -n +2 | tr -d '"\r' | head -1; }

# ── preflight ────────────────────────────────────────────────────────────────
note "preflight"
docker inspect -f '{{.State.Health.Status}}' "$GLOSSARY_CONTAINER" 2>/dev/null | grep -q healthy \
  || die "'$GLOSSARY_CONTAINER' is not healthy — a stale or stopped container passes for the wrong reason"
docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 || die "postgres is not accepting connections"

INTERNAL_TOKEN="$(docker exec "$GLOSSARY_CONTAINER" printenv INTERNAL_SERVICE_TOKEN 2>/dev/null | tr -d '\r')"
JWT_SECRET="$(docker exec "$GLOSSARY_CONTAINER" printenv JWT_SECRET 2>/dev/null | tr -d '\r')"
[ -n "$INTERNAL_TOKEN" ] || die "INTERNAL_SERVICE_TOKEN is unset in $GLOSSARY_CONTAINER"
[ -n "$JWT_SECRET" ]     || die "JWT_SECRET is unset in $GLOSSARY_CONTAINER"
log "glossary healthy; tokens resolved"

# ── fixture: a real book, and a scratch entity we mint inside it ─────────────
note "fixture"
BOOK_ID="${SMOKE_BOOK_ID:-}"; OWNER_ID="${SMOKE_OWNER_ID:-}"
if [ -z "$BOOK_ID" ]; then
  for cand in $(gq "SELECT book_id FROM glossary_entities WHERE deleted_at IS NULL GROUP BY book_id ORDER BY count(*) DESC LIMIT 25;"); do
    [ -z "$cand" ] && continue
    o="$(bq "SELECT owner_user_id FROM books WHERE id='$cand' AND lifecycle_state='active';")"
    if [ -n "$o" ]; then BOOK_ID="$cand"; OWNER_ID="$o"; break; fi
  done
fi
[ -n "$BOOK_ID" ] && [ -n "$OWNER_ID" ] || die "no usable fixture book — pass SMOKE_BOOK_ID and SMOKE_OWNER_ID"
KIND_ID="$(gq "SELECT book_kind_id FROM book_kinds WHERE book_id='$BOOK_ID' AND deprecated_at IS NULL ORDER BY code LIMIT 1;")"
[ -n "$KIND_ID" ] || die "book $BOOK_ID has no live kind"

# A name nothing else can collide with, so "absent from the cast" is a statement about THIS
# entity. A generic name would be indistinguishable from some other row carrying it.
MARK="qc4-$(python -c 'import uuid;print(uuid.uuid4().hex[:12])')"
[ ${#MARK} -eq 16 ] || die "could not mint a unique marker (python missing?) — got '${MARK}'"

ENTITY_ID="$(gq "INSERT INTO glossary_entities(book_id,kind_id,status,name,short_description)
                 VALUES('$BOOK_ID','$KIND_ID','active','$MARK','QC-4 scratch entity — safe to delete')
                 RETURNING entity_id;")"
[ -n "$ENTITY_ID" ] || die "could not mint the scratch entity"
log "fixture book resolved (id withheld); scratch entity '$MARK' minted"

PROJECT_ID="$(kq "SELECT project_id FROM knowledge_projects WHERE book_id='$BOOK_ID' AND user_id='$OWNER_ID' LIMIT 1;")"
NODE_ID="qc4-node-$ENTITY_ID"
JOB_ID=""; CT_ID=""

cleanup() {
  note "cleanup — every row below was minted by this script"
  [ -n "$CT_ID" ]  && tq "DELETE FROM chapter_translations WHERE id='$CT_ID';"   >/dev/null 2>&1
  [ -n "$JOB_ID" ] && tq "DELETE FROM translation_jobs WHERE job_id='$JOB_ID';"  >/dev/null 2>&1
  cy "MATCH (e:Entity {id: '$NODE_ID'}) DETACH DELETE e;"                        >/dev/null 2>&1
  gq "DELETE FROM outbox_events WHERE aggregate_id='$ENTITY_ID';"                >/dev/null 2>&1
  gq "DELETE FROM entity_attribute_values WHERE entity_id='$ENTITY_ID';"         >/dev/null 2>&1
  gq "DELETE FROM glossary_entities WHERE entity_id='$ENTITY_ID';"               >/dev/null 2>&1
  log "scratch rows purged"
}
trap cleanup EXIT

mint_jwt() {
  python - "$JWT_SECRET" "$OWNER_ID" <<'PY'
import base64, hmac, hashlib, json, sys, time
secret, sub = sys.argv[1], sys.argv[2]
b = lambda o: base64.urlsafe_b64encode(json.dumps(o, separators=(",", ":")).encode()).rstrip(b"=")
msg = b({"alg": "HS256", "typ": "JWT"}) + b"." + b({"sub": sub, "exp": int(time.time()) + 900})
sig = base64.urlsafe_b64encode(hmac.new(secret.encode(), msg, hashlib.sha256).digest()).rstrip(b"=")
print((msg + b"." + sig).decode())
PY
}
JWT="$(mint_jwt)"; [ -n "$JWT" ] || die "could not mint a user JWT"

# The KG node the lifecycle consumer is supposed to archive. Created by hand because the
# extraction pipeline that would normally mint it is not what QC-4 is testing — but the
# ANCHOR (`glossary_entity_id`) is real, and it is the only thing the consumer matches on.
if [ -n "$PROJECT_ID" ]; then
  cy "CREATE (e:Entity {id:'$NODE_ID', user_id:'$OWNER_ID', project_id:'$PROJECT_ID',
        glossary_entity_id:'$ENTITY_ID', name:'$MARK', canonical_name:'$MARK', kind:'character',
        aliases:[], short_description:'QC-4 scratch', confidence:1.0, source_type:'glossary',
        source_types:['glossary'], canonical_version:1, anchor_score:1.0, evidence_count:0,
        mention_count:0, archived_at:NULL, created_at:datetime(), updated_at:datetime()});" >/dev/null
  log "KG node created and anchored to the scratch entity"
else
  log "NOTE: book has no knowledge project — the KG legs will report SKIPPED, not PASS"
fi

# A scratch translation row, so the translation leg has something that COULD be flagged.
JOB_ID="$(tq "INSERT INTO translation_jobs(book_id,owner_user_id,target_language,model_source,model_ref,
                system_prompt,user_prompt_tpl,chapter_ids)
              VALUES('$BOOK_ID','$OWNER_ID','fr','qc4','qc4','qc4','qc4','{}')
              RETURNING job_id;" 2>/dev/null)"
if [ -n "$JOB_ID" ]; then
  CT_ID="$(tq "INSERT INTO chapter_translations(job_id,chapter_id,book_id,owner_user_id,target_language,status,is_glossary_stale)
                VALUES('$JOB_ID', gen_random_uuid(), '$BOOK_ID','$OWNER_ID','fr','completed',false)
                RETURNING id;" 2>/dev/null)"
fi
[ -n "$CT_ID" ] && log "scratch chapter_translation created (is_glossary_stale=false)" \
                || log "NOTE: could not create a scratch chapter_translation — that leg will report SKIPPED"

stale_flag() { [ -n "$CT_ID" ] && tq "SELECT is_glossary_stale FROM chapter_translations WHERE id='$CT_ID';"; }
# DRAINS the keyset cursor, because composition does (`_cast_roster`: "the prior glossary
# list_entities path read only the first page and ignored next_cursor, silently truncating the
# cast at ~100"). Reading page 1 only would make a deep book's scratch entity look absent
# BEFORE the delete — a setup failure dressed as a finding.
in_roster() {
  local cursor="" hits=0 page pages=0
  while [ $pages -lt 50 ]; do
    page="$(curl -s -m 20 -H "X-Internal-Token: $INTERNAL_TOKEN" -H "X-User-Id: $OWNER_ID" \
            "$KAL_URL/v1/kal/books/$BOOK_ID/roster?limit=500${cursor:+&cursor=$cursor}" 2>/dev/null)"
    # -o | wc -l, not -c: the response is ONE line of JSON, and `grep -c` counts matching
    # LINES, so it reports 1 no matter how many times the marker appears.
    hits=$(( hits + $(printf '%s' "$page" | grep -o "$MARK" | wc -l) ))
    cursor="$(printf '%s' "$page" | python -c 'import json,sys
try: print(json.load(sys.stdin).get("next_cursor") or "")
except Exception: print("")' 2>/dev/null)"
    pages=$((pages+1))
    [ -z "$cursor" ] && break
  done
  echo "$hits"
}
in_facts()   { curl -s -m 60 -X POST -H "X-Internal-Token: $INTERNAL_TOKEN" -H "Content-Type: application/json" \
                 -d "{\"user_id\":\"$OWNER_ID\",\"project_id\":\"$PROJECT_ID\",\"message\":\"$MARK\",\"grounding\":true}" \
                 "$KNOWLEDGE_URL/internal/context/build" 2>/dev/null | grep -o "$MARK" | wc -l; }
kg_state()   { cy "MATCH (e:Entity {id:'$NODE_ID'}) RETURN CASE WHEN e.archived_at IS NULL THEN 'live' ELSE 'archived' END AS s;"; }

await_kg() {
  local want="$1" tries=60 got=""
  while [ $tries -gt 0 ]; do
    got="$(kg_state)"; [ "$got" = "$want" ] && { echo "$got"; return 0; }
    tries=$((tries-1)); sleep 0.5
  done
  echo "${got:-<nothing>}"; return 1
}

# ── BEFORE: the positive controls ────────────────────────────────────────────
note "BEFORE the delete — the controls that make every absence below mean something"
B_ROSTER="$(in_roster)";  log "cast roster contains the entity: $B_ROSTER"
B_FACTS=0; [ -n "$PROJECT_ID" ] && B_FACTS="$(in_facts)"
B_KG="$(kg_state)";       log "KG node state: ${B_KG:-<none>}"
B_STALE="$(stale_flag)";  log "chapter_translation is_glossary_stale: ${B_STALE:-<skipped>}"

[ "${B_ROSTER:-0}" -gt 0 ] || die "the scratch entity is NOT in the cast roster before the delete — its absence afterwards would prove nothing"
[ -z "$PROJECT_ID" ] || [ "$B_KG" = "live" ] || die "the KG node is not live before the delete"
[ -z "$CT_ID" ] || [ "$B_STALE" = "f" ] || die "the scratch translation is already stale before the delete"
ok "controls established — the entity IS visible to the consumers under test"

STREAM_BEFORE="$(docker exec "$REDIS_CONTAINER" redis-cli XLEN "$STREAM" | tr -d '\r')"

# ── THE COMMAND — real route, real *Core, no hand-written event ──────────────
note "DELETE /v1/glossary/books/{book}/entities/{entity} — the real command"
CODE="$(curl -s -o /tmp/qc4-del.json -w '%{http_code}' -m 30 -X DELETE \
        -H "Authorization: Bearer $JWT" \
        "$GLOSSARY_URL/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID")"
case "$CODE" in
  200|204) ok "command accepted ($CODE)" ;;
  *) die "the DELETE returned $CODE — $(head -c 300 /tmp/qc4-del.json)" ;;
esac

DELETED_AT="$(gq "SELECT CASE WHEN deleted_at IS NULL THEN 'live' ELSE 'trashed' END FROM glossary_entities WHERE entity_id='$ENTITY_ID';")"
[ "$DELETED_AT" = "trashed" ] && ok "glossary row is soft-deleted" || bad "glossary row is '$DELETED_AT' after a 2xx DELETE"

# ── LEG 1 · the emit (this is the one the bite removes) ──────────────────────
note "LEG 1 · the producer emitted, in the same transaction as the mutation"
EMITTED="$(gq "SELECT count(*) FROM outbox_events WHERE aggregate_id='$ENTITY_ID' AND event_type='glossary.entity_deleted';")"
[ "${EMITTED:-0}" -ge 1 ] \
  && ok "outbox carries glossary.entity_deleted ($EMITTED row)" \
  || bad "NO glossary.entity_deleted row — softDeleteEntityCore did not emit. Every leg below is now meaningless, and this is exactly the bypass QC-4 exists to catch"

# ── LEG 2 · the relay ────────────────────────────────────────────────────────
note "LEG 2 · worker-infra relayed it to Redis"
STREAM_AFTER=0
for _ in $(seq 1 40); do
  STREAM_AFTER="$(docker exec "$REDIS_CONTAINER" redis-cli XLEN "$STREAM" | tr -d '\r')"
  [ "${STREAM_AFTER:-0}" -gt "${STREAM_BEFORE:-0}" ] && break
  sleep 0.5
done
[ "${STREAM_AFTER:-0}" -gt "${STREAM_BEFORE:-0}" ] \
  && ok "relay shipped to $STREAM ($STREAM_BEFORE → $STREAM_AFTER)" \
  || bad "the stream did not grow ($STREAM_BEFORE → $STREAM_AFTER) — the row exists but nothing carried it"

# ── LEG 3 · knowledge-service archived the node ──────────────────────────────
note "LEG 3 · consumer effect — Neo4j archived_at"
if [ -z "$PROJECT_ID" ]; then
  log "SKIPPED — the fixture book has no knowledge project"
else
  A_KG="$(await_kg archived)"
  [ "$A_KG" = "archived" ] && ok "KG node archived" || bad "KG node is '$A_KG' 30s after the delete"
  SEVERED="$(cy "MATCH (e:Entity {id:'$NODE_ID'}) RETURN coalesce(e.prior_glossary_entity_id,'NULL') AS p;")"
  [ "$SEVERED" = "$ENTITY_ID" ] \
    && ok "anchor severed with a breadcrumb for restore to match" \
    || bad "no prior_glossary_entity_id breadcrumb — a later restore would find nothing and succeed silently"
fi

# ── LEG 4 · absent from the KG <facts> block ─────────────────────────────────
note "LEG 4 · consumer effect — the assembled <facts> block"
if [ -z "$PROJECT_ID" ]; then
  log "SKIPPED — no knowledge project"
elif [ "${B_FACTS:-0}" -eq 0 ]; then
  log "SKIPPED — the entity was not in the <facts> block BEFORE the delete either, so its"
  log "         absence now is not attributable to the delete. Reported, not scored: a"
  log "         control that never went green cannot license a pass."
else
  A_FACTS="$(in_facts)"
  [ "${A_FACTS:-0}" -eq 0 ] \
    && ok "absent from <facts> (was present before: $B_FACTS)" \
    || bad "still present in <facts> ($A_FACTS occurrences) after the delete"
fi

# ── LEG 5 · absent from composition's cast read ──────────────────────────────
note "LEG 5 · consumer effect — composition's cast (KAL roster)"
A_ROSTER="$(in_roster)"
[ "${A_ROSTER:-0}" -eq 0 ] \
  && ok "absent from the cast roster (was $B_ROSTER before)" \
  || bad "still in the cast roster ($A_ROSTER) — composition would plan around a deleted entity"

# ── LEG 6 · translation staleness ────────────────────────────────────────────
note "LEG 6 · consumer effect — translation is_glossary_stale"
if [ -z "$CT_ID" ]; then
  log "SKIPPED — no scratch chapter_translation"
else
  sleep 6
  A_STALE="$(stale_flag)"
  if [ "$A_STALE" = "t" ]; then
    ok "translation flagged stale by the delete"
  else
    # NOT scored as a plain failure without first proving the consumer is alive. A silent
    # `false` is produced equally by "the consumer ignores this event" and "the consumer is
    # down", and those are different bugs with different fixes.
    gq "INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
        VALUES ('glossary','$ENTITY_ID','glossary.entity_updated',
                '{\"book_id\":\"$BOOK_ID\",\"glossary_entity_id\":\"$ENTITY_ID\"}'::jsonb);" >/dev/null
    C_STALE=""
    for _ in $(seq 1 40); do
      C_STALE="$(stale_flag)"; [ "$C_STALE" = "t" ] && break; sleep 0.5
    done
    if [ "$C_STALE" = "t" ]; then
      bad "translation was NOT flagged by glossary.entity_deleted, but the SAME row flips on"
      log "      glossary.entity_updated — so the consumer is alive and connected, and the gap"
      log "      is the event type. translation-service's handle_glossary_event returns early"
      log "      for every event that is not glossary.entity_updated, so all four lifecycle"
      log "      events are acked and dropped. An already-translated chapter therefore keeps a"
      log "      glossary term that no longer exists, with nothing marking it for retranslation."
    else
      bad "translation not flagged, and the entity_updated control did not flip it either —"
      log "      the glossary consumer looks DOWN. Fix that before reading anything above."
    fi
  fi
fi

note "result"
printf '[qc4] %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ] && log "EVERY CONSUMER OBSERVED THE EFFECT" || log "A CONSUMER DID NOT OBSERVE THE EFFECT (see FAIL above)"
exit $(( fail > 0 ? 1 : 0 ))
