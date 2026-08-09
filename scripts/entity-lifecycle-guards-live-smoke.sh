#!/usr/bin/env bash
# entity-lifecycle-guards-live-smoke.sh — QC-0 of the knowledge-architecture refactor
#
# Proves the three Phase-0 lifecycle guards on a RUNNING glossary-service, against the
# real Postgres and the real Redis event stream:
#
#   T1  a trashed entity is refused by entityExistsInBook  -> canonical-translation
#       404s and buys NO machine translation
#   T3  a trashed entity that is nonetheless edited publishes NO glossary.entity_updated
#       -- neither an outbox row nor a stream frame
#   T2  the contract T2's prune depends on: POST /internal/…/entities/by-ids drops a
#       soft-deleted id ("soft-absent", DI3). The worker half is unit-covered; what
#       crosses a service boundary is this endpoint's behaviour, so this is the half
#       that needs a live stack.
#
# WHY LIVE. All three are BYPASS bugs: the write lands and some other path behaves as
# though it had not. A unit test with a mocked pool proves the guard is in the function;
# it cannot prove the function is on the deployed path. This repo's own lore: a green
# suite proves the working tree, not the commit -- and injecting a fake at the chokepoint
# cannot show the chokepoint is wired.
#
# EVERY assertion carries a positive control in the same run. "No row appeared" is
# satisfied just as well by a broken fixture, so each negative is paired with the same
# call against a LIVE entity, which must succeed.
#
#   bash scripts/entity-lifecycle-guards-live-smoke.sh
#   SMOKE_BOOK_ID=<uuid> SMOKE_OWNER_ID=<uuid> bash scripts/…   # pin the fixture book
#
# Exit 0 = green; 1 = an assertion failed; 2 = setup could not run.
#
# db-safety-gate: file-ok -- the only destructive statements here are DELETEs scoped by
# the scratch entity_id this script itself minted (never a table-wide DELETE, no TRUNCATE,
# no DROP), and the target database is read from the RUNNING container's own environment
# rather than a *_TEST_*_URL a caller could repoint. Nothing pre-existing is written: the
# fixture entity is created by this script and purged by its own trap.
#
# NO SECRETS ARE STORED HERE. The internal token and the JWT secret are read out of the
# running container's environment at execution time. Do not paste either into this file,
# and do not hardcode a book or user UUID -- both are discovered below (or supplied via
# the env vars above), because a pinned dev UUID in a tracked file sends the next
# contributor at somebody else's row.

set -uo pipefail

GLOSSARY_CONTAINER="${GLOSSARY_CONTAINER:-infra-glossary-service-1}"
PG_CONTAINER="${PG_CONTAINER:-infra-postgres-1}"
REDIS_CONTAINER="${REDIS_CONTAINER:-infra-redis-1}"
PG_USER="${PG_USER:-loreweave}"
GLOSSARY_DB="${GLOSSARY_DB:-loreweave_glossary}"
BOOK_DB="${BOOK_DB:-loreweave_book}"
GLOSSARY_URL="${GLOSSARY_URL:-http://localhost:8211}"
STREAM="loreweave:events:glossary"

pass=0
fail=0
log()  { printf '[lifecycle-live] %s\n' "$*"; }
ok()   { pass=$((pass+1)); printf '[lifecycle-live] PASS  %s\n' "$*"; }
bad()  { fail=$((fail+1)); printf '[lifecycle-live] FAIL  %s\n' "$*"; }
die()  { printf '[lifecycle-live] FAIL(setup): %s\n' "$*"; exit 2; }

gq()   { docker exec -i "$PG_CONTAINER" psql -qtAX -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$GLOSSARY_DB" -c "$1" | tr -d '\r'; }
bq()   { docker exec -i "$PG_CONTAINER" psql -qtAX -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$BOOK_DB" -c "$1" | tr -d '\r'; }

# ── preflight ────────────────────────────────────────────────────────────────
docker inspect -f '{{.State.Health.Status}}' "$GLOSSARY_CONTAINER" 2>/dev/null | grep -q healthy \
  || die "container '$GLOSSARY_CONTAINER' is not healthy -- rebuild and start it first (docker compose up -d glossary-service)"
docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 \
  || die "postgres container '$PG_CONTAINER' is not accepting connections"

INTERNAL_TOKEN="$(docker exec "$GLOSSARY_CONTAINER" printenv INTERNAL_SERVICE_TOKEN 2>/dev/null | tr -d '\r')"
JWT_SECRET="$(docker exec "$GLOSSARY_CONTAINER" printenv JWT_SECRET 2>/dev/null | tr -d '\r')"
[ -n "$INTERNAL_TOKEN" ] || die "INTERNAL_SERVICE_TOKEN is not set in $GLOSSARY_CONTAINER"
[ -n "$JWT_SECRET" ]     || die "JWT_SECRET is not set in $GLOSSARY_CONTAINER"

TL_URL="$(docker exec "$GLOSSARY_CONTAINER" printenv TRANSLATION_SERVICE_URL 2>/dev/null | tr -d '\r')"
[ -n "$TL_URL" ] || die "TRANSLATION_SERVICE_URL is empty -- the paid-fill path would be unreachable, so 'spent nothing' would pass for the wrong reason"

# ── fixture: a book that exists on BOTH sides, and a scratch entity we mint ──
BOOK_ID="${SMOKE_BOOK_ID:-}"
OWNER_ID="${SMOKE_OWNER_ID:-}"
if [ -z "$BOOK_ID" ]; then
  log "discovering a book that has an adopted glossary ontology AND a live book row ..."
  for cand in $(gq "SELECT book_id FROM glossary_entities WHERE deleted_at IS NULL GROUP BY book_id ORDER BY count(*) DESC LIMIT 25;"); do
    [ -z "$cand" ] && continue
    o="$(bq "SELECT owner_user_id FROM books WHERE id='$cand' AND lifecycle_state='active';")"
    if [ -n "$o" ]; then BOOK_ID="$cand"; OWNER_ID="$o"; break; fi
  done
fi
[ -n "$BOOK_ID" ] && [ -n "$OWNER_ID" ] || die "could not find a usable fixture book -- pass SMOKE_BOOK_ID and SMOKE_OWNER_ID"
KIND_ID="$(gq "SELECT book_kind_id FROM book_kinds WHERE book_id='$BOOK_ID' AND deprecated_at IS NULL ORDER BY code LIMIT 1;")"
[ -n "$KIND_ID" ] || die "book $BOOK_ID has no live kind"
log "fixture book resolved (id withheld from the log; owner resolved)"

# The scratch entity is FIXTURE, not the thing under test -- created by SQL so the smoke
# stays about the guards. short_description is non-empty so getCanonicalContent's degrade
# path yields buildable content and the paid fill is genuinely reachable.
ENTITY_ID="$(gq "INSERT INTO glossary_entities(book_id,kind_id,status,short_description) VALUES('$BOOK_ID','$KIND_ID','active','QC-0 scratch entity - safe to delete') RETURNING entity_id;")"
[ -n "$ENTITY_ID" ] || die "could not mint the scratch entity"
log "scratch entity minted"

cleanup() {
  gq "DELETE FROM canonical_snapshot_translations WHERE entity_id='$ENTITY_ID';" >/dev/null 2>&1
  gq "DELETE FROM outbox_events WHERE aggregate_id='$ENTITY_ID';"                >/dev/null 2>&1
  gq "DELETE FROM entity_attribute_values WHERE entity_id='$ENTITY_ID';"          >/dev/null 2>&1
  gq "DELETE FROM glossary_entities WHERE entity_id='$ENTITY_ID';"                >/dev/null 2>&1
  log "scratch rows purged"
}
trap cleanup EXIT

mint_jwt() {
  python3 - "$JWT_SECRET" "$OWNER_ID" <<'PY'
import base64, hmac, hashlib, json, sys, time
secret, sub = sys.argv[1], sys.argv[2]
b = lambda o: base64.urlsafe_b64encode(json.dumps(o, separators=(",", ":")).encode()).rstrip(b"=")
msg = b({"alg": "HS256", "typ": "JWT"}) + b"." + b({"sub": sub, "exp": int(time.time()) + 900})
sig = base64.urlsafe_b64encode(hmac.new(secret.encode(), msg, hashlib.sha256).digest()).rstrip(b"=")
print((msg + b"." + sig).decode())
PY
}
JWT="$(mint_jwt)"
[ -n "$JWT" ] || die "could not mint a user JWT"

soft_delete() { gq "UPDATE glossary_entities SET deleted_at=now() WHERE entity_id='$ENTITY_ID';" >/dev/null; }
restore()     { gq "UPDATE glossary_entities SET deleted_at=NULL  WHERE entity_id='$ENTITY_ID';" >/dev/null; }
claim_rows()  { gq "SELECT count(*) FROM canonical_snapshot_translations WHERE entity_id='$ENTITY_ID';"; }
events()      { gq "SELECT count(*) FROM outbox_events WHERE aggregate_id='$ENTITY_ID' AND event_type='glossary.entity_updated';"; }
version()     { gq "SELECT to_char(updated_at AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.USOF:00') FROM glossary_entities WHERE entity_id='$ENTITY_ID';"; }

get_translation() {
  curl -s -o /tmp/lifecycle-tl.json -w '%{http_code}' \
    -H "X-Internal-Token: $INTERNAL_TOKEN" -H "X-User-Id: $OWNER_ID" \
    "$GLOSSARY_URL/internal/books/$BOOK_ID/entities/$ENTITY_ID/canonical-translation?lang=fr"
}
apply_edit() {
  curl -s -o /tmp/lifecycle-edit.json -w '%{http_code}' -X POST \
    -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
    -d "{\"base_version\":\"$(version)\",\"short_description\":\"$1\"}" \
    "$GLOSSARY_URL/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/apply-edit"
}
by_ids_hit() {
  curl -s -H "X-Internal-Token: $INTERNAL_TOKEN" -H "Content-Type: application/json" \
    -d "{\"entity_ids\":[\"$ENTITY_ID\"]}" \
    "$GLOSSARY_URL/internal/books/$BOOK_ID/entities/by-ids" | grep -c "$ENTITY_ID"
}

# ── T1 · a trashed entity buys no translation ────────────────────────────────
log "--- T1: canonical-translation on a TRASHED entity ---"
soft_delete
code="$(get_translation)"
[ "$code" = "404" ] && ok "T1 refused with 404" || bad "T1 expected 404, got $code ($(head -c 200 /tmp/lifecycle-tl.json))"
n="$(claim_rows)"
# The single-flight claim row is inserted 1:1 with a launched fill, so zero rows is a
# causal proof that nothing was bought -- and it does not race the fill goroutine.
[ "$n" = "0" ] && ok "T1 spent nothing (0 translation claim rows)" || bad "T1 claimed $n translation row(s) on deleted content -- that is a paid call"

log "--- T1 control: the SAME call on a LIVE entity ---"
restore
code="$(get_translation)"
[ "$code" = "200" ] && ok "T1 control reached the fill path (200)" || bad "T1 control expected 200, got $code -- the 404 above proves nothing if this path is unreachable"
n="$(claim_rows)"
[ "$n" = "1" ] && ok "T1 control claimed exactly 1 translation row" || bad "T1 control claimed $n rows, want 1"
gq "DELETE FROM canonical_snapshot_translations WHERE entity_id='$ENTITY_ID';" >/dev/null

# ── T3 · a trashed entity that is edited publishes nothing ───────────────────
stream_frames_since() {
  docker exec "$REDIS_CONTAINER" redis-cli --no-raw XRANGE "$STREAM" "($1" + 2>/dev/null | grep -c "$ENTITY_ID"
}
stream_tip() {
  local id
  id="$(docker exec "$REDIS_CONTAINER" redis-cli --no-raw XREVRANGE "$STREAM" + - COUNT 1 2>/dev/null | grep -oE '[0-9]+-[0-9]+' | head -1)"
  printf '%s' "${id:-0-0}"
}
# The relay POLLS the outbox (~33s between cycles on this stack); it is not push. An
# absence asserted 3 seconds after the write is therefore vacuous -- it would hold just as
# well for an event that simply had not shipped yet. Both legs below wait on the relay's
# real cadence, and the control leg has to actually ARRIVE before the negative is trusted.
RELAY_ARRIVE_DEADLINE="${RELAY_ARRIVE_DEADLINE:-150}"

log "--- T3 control: editing a LIVE entity DOES publish ---"
last_id="$(stream_tip)"
before="$(events)"
code="$(apply_edit "QC-0 live edit")"
[ "$code" = "200" ] && ok "T3 control edit accepted (200)" || bad "T3 control edit expected 200, got $code ($(head -c 200 /tmp/lifecycle-edit.json))"
after="$(events)"
[ "$after" -gt "$before" ] && ok "T3 control published an outbox row ($before -> $after)" || bad "T3 control published nothing ($before -> $after) -- the negative below would pass for the wrong reason"

log "waiting up to ${RELAY_ARRIVE_DEADLINE}s for the relay to ship the control frame ..."
deadline=$(( $(date +%s) + RELAY_ARRIVE_DEADLINE ))
control_frames=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  control_frames="$(stream_frames_since "$last_id")"
  [ "$control_frames" -ge 1 ] && break
  sleep 5
done
# THIS is what makes the absence below meaningful: it proves the stream query can see a
# frame for this entity at all. Without it, "0 frames" is indistinguishable from a broken
# query, a stale relay, or the wrong Redis.
if [ "$control_frames" -ge 1 ]; then
  ok "T3 control frame reached $STREAM (the stream leg is observable)"
else
  bad "T3 control frame never reached $STREAM within ${RELAY_ARRIVE_DEADLINE}s -- the stream assertion below cannot be trusted, so it is not made"
fi
mid_id="$(stream_tip)"

log "--- T3: editing a TRASHED entity must publish NOTHING ---"
soft_delete
before="$(events)"
code="$(apply_edit "QC-0 edit on a trashed entity")"
log "apply-edit on a trashed entity returned $code (the write itself is T27's call; only the emission is under test here)"
after="$(events)"
[ "$after" = "$before" ] && ok "T3 published no outbox row ($before -> $after)" || bad "T3 published $((after-before)) entity_updated row(s) for a trashed entity -- the deletion is reversed downstream"

if [ "$control_frames" -ge 1 ]; then
  # Wait longer than the observed control latency, so "nothing arrived" means the relay
  # had its chance rather than that we asked too early.
  log "waiting ${RELAY_ARRIVE_DEADLINE}s for the relay to prove nothing else ships ..."
  sleep "$RELAY_ARRIVE_DEADLINE"
  frames="$(stream_frames_since "$mid_id")"
  [ "$frames" -eq 0 ] && ok "T3 no frame for the trashed entity reached $STREAM" \
                       || bad "T3 $frames frame(s) for the trashed entity reached the stream -- a consumer re-anchors a deleted entity"
else
  log "SKIP  T3 stream absence -- the control frame never arrived, so absence proves nothing here"
fi

# ── T2 · the cross-service contract the worker's prune leans on ──────────────
log "--- T2: entities/by-ids must drop a soft-deleted id ---"
hits="$(by_ids_hit)"   # still trashed from the T3 block
[ "$hits" = "0" ] && ok "T2 by-ids omitted the trashed id (soft-absent holds)" || bad "T2 by-ids returned the trashed id -- the worker's liveness prune would never fire"
restore
hits="$(by_ids_hit)"
[ "$hits" -ge 1 ] && ok "T2 control: by-ids returns the id while live" || bad "T2 control: by-ids omitted a LIVE id -- the prune would strip real context"

# ── verdict ──────────────────────────────────────────────────────────────────
log "-----------------------------------------------------------------"
log "passed=$pass failed=$fail"
[ "$fail" -eq 0 ] && { log "GREEN"; exit 0; } || { log "RED"; exit 1; }
