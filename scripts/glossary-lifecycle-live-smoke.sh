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

pass=0; fail=0; skip=0
log()  { printf '[qc4] %s\n' "$*"; }
ok()   { pass=$((pass+1)); printf '[qc4] PASS  %s\n' "$*"; }
bad()  { fail=$((fail+1)); printf '[qc4] FAIL  %s\n' "$*"; }
# Counted, and counted against the run. QC-4's contract is "assert the effect in EVERY
# consumer"; a leg that did not run has not asserted anything, and printing "0 failed" over
# three silent skips is the exact shape this plan has been burned by twice.
skipped() { skip=$((skip+1)); printf '[qc4] SKIP  %s\n' "$*"; }
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
# A book with a KNOWLEDGE PROJECT is strongly preferred, and the preference is the whole
# difference between QC-4 proving something and QC-4 reporting SKIPPED. The first live run
# picked the book with the most glossary entities, which had no KG project, so three of the
# six legs — the KG archive, the <facts> block, and the graph half of the story — skipped and
# the run still printed "6 passed, 0 failed". **A suite that skips its hardest assertions and
# reports green is the failure this plan keeps rediscovering**, so the pass is now taken from
# the KG-capable set first and falling back is announced loudly.
BOOK_ID="${SMOKE_BOOK_ID:-}"; OWNER_ID="${SMOKE_OWNER_ID:-}"
pick_from() {
  for cand in $1; do
    [ -z "$cand" ] && continue
    gq "SELECT 1 FROM glossary_entities WHERE book_id='$cand' AND deleted_at IS NULL LIMIT 1;" | grep -q 1 || continue
    gq "SELECT 1 FROM book_kinds WHERE book_id='$cand' AND deprecated_at IS NULL LIMIT 1;" | grep -q 1 || continue
    o="$(bq "SELECT owner_user_id FROM books WHERE id='$cand' AND lifecycle_state='active';")"
    [ -n "$o" ] && { BOOK_ID="$cand"; OWNER_ID="$o"; return 0; }
  done
  return 1
}
if [ -z "$BOOK_ID" ]; then
  pick_from "$(kq "SELECT DISTINCT book_id FROM knowledge_projects WHERE book_id IS NOT NULL;")" \
    && log "fixture: a book WITH a knowledge project (the KG legs will run)"
fi
if [ -z "$BOOK_ID" ]; then
  pick_from "$(gq "SELECT book_id FROM glossary_entities WHERE deleted_at IS NULL GROUP BY book_id ORDER BY count(*) DESC LIMIT 25;")" \
    && log "⚠ fixture: NO book with a knowledge project was usable — the KG legs will SKIP, and a run with skipped legs is not a QC-4 pass"
fi
[ -n "$BOOK_ID" ] && [ -n "$OWNER_ID" ] || die "no usable fixture book — pass SMOKE_BOOK_ID and SMOKE_OWNER_ID"
KIND_ID="$(gq "SELECT book_kind_id FROM book_kinds WHERE book_id='$BOOK_ID' AND deprecated_at IS NULL ORDER BY code LIMIT 1;")"
[ -n "$KIND_ID" ] || die "book $BOOK_ID has no live kind"

# A name nothing else can collide with, so "absent from the cast" is a statement about THIS
# entity. A generic name would be indistinguishable from some other row carrying it.
MARK="qc4-$(python -c 'import uuid;print(uuid.uuid4().hex[:12])')"
[ ${#MARK} -eq 16 ] || die "could not mint a unique marker (python missing?) — got '${MARK}'"

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

# The scratch entity is created through the REAL create route, not by INSERT.
#
# This is not fastidiousness. **The name does not live on `glossary_entities`** — it is an
# attribute value, and `cached_name` is trigger-maintained from it. An INSERT that set
# `cached_name` directly would produce a row no writer in this service ever produces, and the
# repo has already paid for that exact shape twice: `D-GLOSS-CREATE-DROPS-DOCUMENTED-FIELDS`
# (a create returning 201 with a NAMELESS entity) and the lore that fixtures can seed a field
# the writer never sets. A fixture that is not what the writer writes tests a row that cannot
# occur.
CREATE_BODY="{\"kind_id\":\"$KIND_ID\",\"display_name\":\"$MARK\",\"status\":\"active\"}"
CREATE_OUT="$(curl -s -m 30 -w '\n%{http_code}' -X POST \
              -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
              -d "$CREATE_BODY" "$GLOSSARY_URL/v1/glossary/books/$BOOK_ID/entities")"
CREATE_CODE="$(printf '%s' "$CREATE_OUT" | tail -1)"
case "$CREATE_CODE" in
  200|201) : ;;
  *) die "create returned $CREATE_CODE — $(printf '%s' "$CREATE_OUT" | head -c 300)" ;;
esac
ENTITY_ID="$(printf '%s' "$CREATE_OUT" | head -n -1 | python -c 'import json,sys
try: print(json.load(sys.stdin).get("entity_id") or "")
except Exception: print("")' 2>/dev/null)"
[ -n "$ENTITY_ID" ] || die "create succeeded ($CREATE_CODE) but returned no entity_id"

# The name is what every downstream reader matches on, so verify the create actually set it
# rather than trusting the 2xx — that is the precise failure D-GLOSS-CREATE-DROPS-DOCUMENTED-
# FIELDS records, and a nameless fixture would make every "absent" leg below pass vacuously.
CACHED="$(gq "SELECT coalesce(cached_name,'') FROM glossary_entities WHERE entity_id='$ENTITY_ID';")"
[ "$CACHED" = "$MARK" ] || die "the created entity's cached_name is '${CACHED:-<empty>}', not '$MARK' — a nameless fixture cannot be found by any consumer, so every absence below would be meaningless"
log "fixture book resolved (id withheld); scratch entity created via the API, name verified"

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

# ── the LEG 6 race, closed at the source ─────────────────────────────────────
# Creating the entity emits `glossary.entity_updated`, which is an event translation-service
# DOES act on. If the scratch translation row exists when that event is consumed, the flag
# flips and LEG 6 later credits the DELETE for the CREATE's effect.
#
# An earlier version tried to absorb this with a settle-and-clear loop. The QC-4 bite proved
# that insufficient: with the outbox emit removed from the producer entirely, LEG 6 still
# PASSED — it was measuring a late create event, not the delete. A fixed sleep cannot fix a
# race, it can only make it rarer and harder to see.
#
# So the row is not created until the staleness consumer has CAUGHT UP to the stream tip. An
# UPDATE cannot flag a row that does not exist yet, which removes the interference instead of
# waiting it out.
# Requires lag=0 AND pending=0, twice in a row.
#
# `lag` alone is not enough, and the run that taught me that is worth the comment: this
# consumer "processes pending on startup", so restarting translation-service replays every
# delivered-but-unacked event. Those replays are invisible to `lag` — the group has already
# read to the tip — and they flagged the scratch row seconds after it was created. `pending`
# is the field that sees them. Two consecutive clean reads, because a backlog being drained
# passes through 0 momentarily between deliveries.
wait_consumer_caught_up() {
  local clean=0 lag pending grp
  for _ in $(seq 1 90); do
    grp="$(docker exec "$REDIS_CONTAINER" redis-cli XINFO GROUPS "$STREAM" 2>/dev/null \
           | grep -A 12 '^translation-staleness$')"
    lag="$(printf '%s\n' "$grp"     | grep -A1 '^lag$'     | tail -1 | tr -d '\r')"
    pending="$(printf '%s\n' "$grp" | grep -A1 '^pending$' | tail -1 | tr -d '\r')"
    if [ "${lag:-x}" = "0" ] && [ "${pending:-x}" = "0" ]; then
      clean=$((clean+1)); [ "$clean" -ge 2 ] && return 0
    else
      clean=0
    fi
    sleep 0.5
  done
  return 1
}
# …and consumer lag is still not sufficient on its own, because it only measures the REDIS
# side. Creating an entity writes TWO `glossary.entity_updated` outbox rows (the entity, then
# its name attribute), and an outbox row that the relay has not shipped yet is invisible to
# `lag` — the group has read to the tip precisely because the row is not there yet. So this
# also waits for OUR entity's own events to stop arriving on the stream.
# `outbox_events.published_at` is the relay's OWN marker — a deterministic signal that beats
# every timing heuristic tried before it. While any row for this entity is unpublished, the
# relay still has something to ship and a late `entity_updated` can still land on the row.
wait_outbox_drained() {
  for _ in $(seq 1 90); do
    [ "$(gq "SELECT count(*) FROM outbox_events WHERE aggregate_id='$ENTITY_ID' AND published_at IS NULL;")" = "0" ] && return 0
    sleep 0.5
  done
  return 1
}
if wait_outbox_drained && wait_consumer_caught_up; then
  log "the CREATE's own events have stopped arriving and the consumer is drained — nothing but the DELETE can flag the row below"
else
  log "⚠ the CREATE's events did not settle; LEG 6 may attribute a late CREATE event and the guard below will refuse the run"
fi

# A scratch translation row, so the translation leg has something that COULD be flagged.
# `model_ref` is a uuid, not free text — the first version of this passed 'qc4' for it and the
# insert failed, which silently turned the translation leg into a SKIP. A leg that skips because
# the fixture is malformed looks identical to a leg that skips because the feature is absent.
JOB_ID="$(tq "INSERT INTO translation_jobs(book_id,owner_user_id,target_language,model_source,model_ref,
                system_prompt,user_prompt_tpl,chapter_ids)
              VALUES('$BOOK_ID','$OWNER_ID','fr','qc4',gen_random_uuid(),'qc4','qc4','{}')
              RETURNING job_id;" 2>&1)"
case "$JOB_ID" in *ERROR*) log "translation_jobs insert failed: $JOB_ID"; JOB_ID="" ;; esac
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
# LEG 6 is attributed by EVIDENCE, not by timing. Every waiting scheme tried here failed the
# same way: creating an entity writes two `glossary.entity_updated` outbox rows, the relay
# ships them on its own schedule, and no sleep can be proven long enough. So the flag is
# cleared immediately before the delete and the stream tip is recorded; afterwards LEG 6 asks
# which of THIS entity's events arrived after that tip. A flag that flips while an
# `entity_updated` also arrived is reported as inconclusive rather than as a pass.
if [ -n "$CT_ID" ]; then
  tq "UPDATE chapter_translations SET is_glossary_stale=false WHERE id='$CT_ID';" >/dev/null
fi
B_STALE="$(stale_flag)";  log "chapter_translation is_glossary_stale: ${B_STALE:-<skipped>} (cleared immediately before the delete)"
# Database clock, not the shell's — the comparison below is against `published_at`, which
# Postgres writes, and two clocks would make the window silently wrong.
CLEARED_AT="$(gq "SELECT now();")"

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
# Looks for OUR event on the stream, not merely for the stream getting longer. Length is a
# shared counter: on a busy dev stack it grows because somebody else's entity moved, and on a
# MAXLEN-capped stream it cannot grow at all no matter what arrives. Either way "it grew" is
# not the question — "did THIS delete arrive" is.
#
# Matched by the stream entry's own `outbox_id`, which is the row's primary key — unique,
# unambiguous, and immune to how many other events are in flight. An earlier version grepped
# for the entity id and looked a couple of lines either side for the event type; on a busy
# stream that window slid off the entry and reported "not relayed" for an event Neo4j had
# visibly already acted on. A proximity match is a guess about formatting, not an assertion.
OUTBOX_ID="$(gq "SELECT id FROM outbox_events WHERE aggregate_id='$ENTITY_ID' AND event_type='glossary.entity_deleted' ORDER BY created_at DESC LIMIT 1;")"
SEEN=0
for _ in $(seq 1 40); do
  [ -n "$OUTBOX_ID" ] && SEEN="$(docker exec "$REDIS_CONTAINER" redis-cli XREVRANGE "$STREAM" + - COUNT 500 2>/dev/null | grep -c "$OUTBOX_ID")"
  [ "${SEEN:-0}" -gt 0 ] && break
  sleep 0.5
done
STREAM_AFTER="$(docker exec "$REDIS_CONTAINER" redis-cli XLEN "$STREAM" | tr -d '\r')"
[ "${SEEN:-0}" -gt 0 ] \
  && ok "relay carried THIS entity's glossary.entity_deleted onto $STREAM (len $STREAM_BEFORE → $STREAM_AFTER)" \
  || bad "no glossary.entity_deleted for $ENTITY_ID on $STREAM after 20s (len $STREAM_BEFORE → $STREAM_AFTER) — the outbox row exists but nothing carried it"

# ── LEG 3 · knowledge-service archived the node ──────────────────────────────
note "LEG 3 · consumer effect — Neo4j archived_at"
if [ -z "$PROJECT_ID" ]; then
  skipped "LEG 3 — the fixture book has no knowledge project"
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
  skipped "LEG 4 — no knowledge project"
elif [ "${B_FACTS:-0}" -eq 0 ]; then
  skipped "LEG 4 — the entity was not in the <facts> block BEFORE the delete either, so its"
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
  skipped "LEG 6 — no scratch chapter_translation"
else
  A_STALE=""
  for _ in $(seq 1 30); do
    A_STALE="$(stale_flag)"; [ "$A_STALE" = "t" ] && break; sleep 0.5
  done
  # Attribution, from the producer's own ledger rather than by parsing the stream: did any
  # OTHER event for this entity get relayed inside the window the flag could have flipped in?
  SINCE="$(gq "SELECT coalesce(string_agg(DISTINCT event_type, ' ' ORDER BY event_type), '')
               FROM outbox_events
               WHERE aggregate_id='$ENTITY_ID' AND published_at > '$CLEARED_AT'::timestamptz;")"
  if [ "$A_STALE" = "t" ] && [ "$SINCE" = "glossary.entity_deleted" ]; then
    ok "translation flagged stale, and the ONLY event for this entity since the delete was glossary.entity_deleted"
  elif [ "$A_STALE" = "t" ]; then
    bad "translation went stale but this entity ALSO produced [${SINCE}] since the tip —"
    log "      attribution is not established, so this is not a LEG 6 pass. Re-run; if it"
    log "      persists, the create path's entity_updated is racing the delete."
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
printf '[qc4] %d passed, %d failed, %d skipped\n' "$pass" "$fail" "$skip"
if [ "$fail" -gt 0 ]; then
  log "A CONSUMER DID NOT OBSERVE THE EFFECT (see FAIL above)"
elif [ "$skip" -gt 0 ]; then
  log "INCOMPLETE — $skip leg(s) never ran. QC-4's contract is every consumer, so this is"
  log "  NOT a pass: the skipped legs are unproven, not proven-absent. Re-run against a"
  log "  fixture that satisfies them (a book with a knowledge project, a translation row)."
else
  log "EVERY CONSUMER OBSERVED THE EFFECT"
fi
exit $(( fail > 0 ? 1 : (skip > 0 ? 3 : 0) ))
