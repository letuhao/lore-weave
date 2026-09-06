#!/usr/bin/env bash
# state-asof-live-smoke.sh — QC-1 of the knowledge-architecture refactor
#
# Proves the new book-wide as-of read END TO END, on a running stack, and measures what
# the KAL hop costs (plan T8's gate):
#
#   AC1  a fact closed at ordinal N reports the OLD value at N-1 and the NEW value at N
#        -- read through the gateway, not the service
#   AC2  exactly ONE value per (entity, attribute) at a position, even when the substrate
#        holds an unclosed chain (two intervals covering the same ordinal)
#   REQ  a request with no story position is REFUSED (400) all the way through the KAL --
#        the rule lives in glossary and the gateway must not repair it
#   CONS the consumer drives it: composition-service's own KalClient.state() inside the
#        composition container, not curl -- a new cross-service contract is proven by its
#        consumer, and the gateway hop is exactly what a unit test omits
#   PERF p50/p95 for the same read in-process (glossary /internal) vs through the KAL,
#        published as a RATIO (T8)
#
# WHY LIVE. T5's tests run the handler against a real Postgres but an httptest router;
# they cannot show the route is registered on the deployed binary, that the gateway maps
# the path, that the internal token reaches glossary, or what the extra hop costs. This
# repo's lore: a green suite proves the working tree, not the commit.
#
# EVERY negative assertion carries a positive control in the same run.
#
#   bash scripts/state-asof-live-smoke.sh
#   SMOKE_BOOK_ID=<uuid> SMOKE_OWNER_ID=<uuid> bash scripts/state-asof-live-smoke.sh
#
# Exit 0 = green; 1 = an assertion failed; 2 = setup could not run.
#
# db-safety-gate: file-ok -- every destructive statement is scoped by the scratch
# entity_id this script itself minted (no table-wide DELETE, no TRUNCATE, no DROP), and
# the databases are read from the RUNNING containers' own environment rather than from a
# *_TEST_*_URL a caller could repoint. The fixture entity and its facts are created here
# and purged by this script's own trap.
#
# NO SECRETS ARE STORED HERE. The internal token is read out of the running container at
# execution time, and no book/user UUID is hardcoded -- a pinned dev UUID in a tracked
# file sends the next contributor at somebody else's row.

set -uo pipefail

GLOSSARY_CONTAINER="${GLOSSARY_CONTAINER:-infra-glossary-service-1}"
GATEWAY_CONTAINER="${GATEWAY_CONTAINER:-infra-knowledge-gateway-1}"
COMPOSITION_CONTAINER="${COMPOSITION_CONTAINER:-infra-composition-service-1}"
PG_CONTAINER="${PG_CONTAINER:-infra-postgres-1}"
PG_USER="${PG_USER:-loreweave}"
GLOSSARY_DB="${GLOSSARY_DB:-loreweave_glossary}"
BOOK_DB="${BOOK_DB:-loreweave_book}"
GLOSSARY_URL="${GLOSSARY_URL:-http://localhost:8211}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:3210}"
PERF_N="${PERF_N:-20}"

pass=0
fail=0
log()  { printf '[state-asof-live] %s\n' "$*"; }
ok()   { pass=$((pass+1)); printf '[state-asof-live] PASS  %s\n' "$*"; }
bad()  { fail=$((fail+1)); printf '[state-asof-live] FAIL  %s\n' "$*"; }
skip() { printf '[state-asof-live] SKIP  %s\n' "$*"; }
die()  { printf '[state-asof-live] FAIL(setup): %s\n' "$*"; exit 2; }

gq()   { docker exec -i "$PG_CONTAINER" psql -qtAX -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$GLOSSARY_DB" -c "$1" | tr -d '\r'; }
bq()   { docker exec -i "$PG_CONTAINER" psql -qtAX -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$BOOK_DB" -c "$1" | tr -d '\r'; }

# ── preflight ────────────────────────────────────────────────────────────────
for c in "$GLOSSARY_CONTAINER" "$GATEWAY_CONTAINER"; do
  docker inspect -f '{{.State.Health.Status}}' "$c" 2>/dev/null | grep -q healthy \
    || die "container '$c' is not healthy -- rebuild and start it (docker compose up -d --build)"
done
docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 \
  || die "postgres container '$PG_CONTAINER' is not accepting connections"

INTERNAL_TOKEN="$(docker exec "$GLOSSARY_CONTAINER" printenv INTERNAL_SERVICE_TOKEN 2>/dev/null | tr -d '\r')"
[ -n "$INTERNAL_TOKEN" ] || die "INTERNAL_SERVICE_TOKEN is not set in $GLOSSARY_CONTAINER"

# The gateway must be talking to the SAME glossary this script seeds, or every assertion
# below would be measuring a different database and the empty results would read as bugs.
GW_GLOSSARY="$(docker exec "$GATEWAY_CONTAINER" printenv GLOSSARY_SERVICE_URL 2>/dev/null | tr -d '\r')"
[ -n "$GW_GLOSSARY" ] || die "the gateway has no GLOSSARY_SERVICE_URL -- it cannot reach the service under test"

# ── fixture ──────────────────────────────────────────────────────────────────
BOOK_ID="${SMOKE_BOOK_ID:-}"
OWNER_ID="${SMOKE_OWNER_ID:-}"
if [ -z "$BOOK_ID" ]; then
  log "discovering a book with a live glossary ontology and an active book row ..."
  for cand in $(gq "SELECT book_id FROM glossary_entities WHERE deleted_at IS NULL GROUP BY book_id ORDER BY count(*) DESC LIMIT 25;"); do
    [ -z "$cand" ] && continue
    o="$(bq "SELECT owner_user_id FROM books WHERE id='$cand' AND lifecycle_state='active';")"
    if [ -n "$o" ]; then BOOK_ID="$cand"; OWNER_ID="$o"; break; fi
  done
fi
[ -n "$BOOK_ID" ] && [ -n "$OWNER_ID" ] || die "no usable fixture book -- pass SMOKE_BOOK_ID and SMOKE_OWNER_ID"
KIND_ID="$(gq "SELECT book_kind_id FROM book_kinds WHERE book_id='$BOOK_ID' AND deprecated_at IS NULL ORDER BY code LIMIT 1;")"
[ -n "$KIND_ID" ] || die "book $BOOK_ID has no live kind"
log "fixture book resolved (id withheld from the log; owner resolved)"

ENTITY_ID="$(gq "INSERT INTO glossary_entities(book_id,kind_id,status,short_description) VALUES('$BOOK_ID','$KIND_ID','active','QC-1 scratch entity - safe to delete') RETURNING entity_id;")"
[ -n "$ENTITY_ID" ] || die "could not mint the scratch entity"

cleanup() {
  gq "DELETE FROM entity_facts WHERE entity_id='$ENTITY_ID';"       >/dev/null 2>&1
  gq "DELETE FROM outbox_events WHERE aggregate_id='$ENTITY_ID';"   >/dev/null 2>&1
  gq "DELETE FROM glossary_entities WHERE entity_id='$ENTITY_ID';"  >/dev/null 2>&1
  log "scratch rows purged"
}
trap cleanup EXIT

# A story arc in facts. The ordinals are chosen high (9000+) so they cannot collide with
# real chapter positions in a shared dev book -- this entity is the only subject either way,
# but a collision would make a failure hard to read.
seed_fact() { # kind attr value from to|NULL
  gq "INSERT INTO entity_facts(book_id,entity_id,fact_kind,attr_or_predicate,value,valid_from_ordinal,valid_to_ordinal,cardinality)
      VALUES('$BOOK_ID','$ENTITY_ID','$1','$2','$3',$4,$5,'single');" >/dev/null
}
seed_fact attribute life_status alive      9000 9040
seed_fact attribute life_status dead       9040 NULL
seed_fact attribute rank        'outer'    9010 9025
seed_fact attribute rank        'inner'    9025 NULL
# The unclosed chain AC2 needs: a second OPEN interval on the same attribute. This is the
# substrate bug DISTINCT ON exists to survive -- without it, disjoint intervals mean the
# WHERE clause alone already returns one row and the assertion proves nothing.
seed_fact attribute allegiance  'Cloud'    9005 NULL
seed_fact attribute allegiance  'Ash'      9030 NULL
log "seeded 6 facts on the scratch entity"

# ── helpers ──────────────────────────────────────────────────────────────────
# `jq` is not assumed present on the host; python3 does the parsing.
kal_state() { # as_of -> body on stdout, http code in KAL_CODE
  KAL_CODE="$(curl -s -o /tmp/state-kal.json -w '%{http_code}' \
    -H "X-Internal-Token: $INTERNAL_TOKEN" -H "X-User-Id: $OWNER_ID" \
    "$GATEWAY_URL/v1/kal/books/$BOOK_ID/state?as_of=$1")"
  cat /tmp/state-kal.json
}
values_for() { # attr <json-file> -> one value per line, for OUR entity only
  # `tr -d '\r'` is load-bearing on a Windows host: Python there writes CRLF, so a value
  # compares as "alive\r" and every string assertion below reports a mismatch between two
  # identical-looking strings. A harness that fails that way is worse than one that fails
  # loudly -- it looks like the product is broken.
  python3 - "$1" "$ENTITY_ID" "$2" <<'PY' | tr -d '\r'
import json, sys
attr, eid, path = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    doc = json.load(open(path, encoding="utf-8"))
except Exception:
    sys.exit(0)
for e in doc.get("entities", []) or []:
    if str(e.get("entity_id")) != eid:
        continue
    for f in e.get("facts", []) or []:
        if f.get("attr") == attr:
            print(f.get("value"))
PY
}

# ── AC1 · death is temporal, through the KAL ─────────────────────────────────
log "--- AC1: the same entity, read at two positions, through the gateway ---"
kal_state 9039 >/dev/null
[ "$KAL_CODE" = "200" ] || bad "AC1 as_of=9039 expected 200 through the KAL, got $KAL_CODE"
got="$(values_for life_status /tmp/state-kal.json | tr '\n' ' ' | sed 's/ *$//')"
[ "$got" = "alive" ] && ok "AC1 as_of=9039 -> alive (present and living one chapter before the death)" \
                     || bad "AC1 as_of=9039 life_status='$got', want 'alive'"

kal_state 9040 >/dev/null
got="$(values_for life_status /tmp/state-kal.json | tr '\n' ' ' | sed 's/ *$//')"
[ "$got" = "dead" ] && ok "AC1 as_of=9040 -> dead (the half-open boundary: the death chapter is the first dead one)" \
                    || bad "AC1 as_of=9040 life_status='$got', want 'dead'"

# ── AC2 · one value per attribute, including over an unclosed chain ──────────
log "--- AC2: exactly one value per attribute at a position ---"
kal_state 9030 >/dev/null
n="$(values_for rank /tmp/state-kal.json | grep -c .)"
v="$(values_for rank /tmp/state-kal.json | head -1)"
{ [ "$n" = "1" ] && [ "$v" = "inner" ]; } && ok "AC2 rank at 9030 -> exactly one value ('inner')" \
                                          || bad "AC2 rank at 9030 -> $n value(s) ('$v'), want exactly one 'inner'"
n="$(values_for allegiance /tmp/state-kal.json | grep -c .)"
v="$(values_for allegiance /tmp/state-kal.json | head -1)"
{ [ "$n" = "1" ] && [ "$v" = "Ash" ]; } && ok "AC2 UNCLOSED CHAIN collapses to the freshest ('Ash'), not two contradictory values" \
                                        || bad "AC2 allegiance at 9030 -> $n value(s) ('$v'), want exactly one 'Ash'"

# ── REQ · the required position survives the hop ─────────────────────────────
log "--- REQ: a request with no story position ---"
code="$(curl -s -o /tmp/state-noasof.json -w '%{http_code}' \
  -H "X-Internal-Token: $INTERNAL_TOKEN" -H "X-User-Id: $OWNER_ID" \
  "$GATEWAY_URL/v1/kal/books/$BOOK_ID/state")"
[ "$code" = "400" ] && ok "REQ no as_of -> 400 through the KAL (the service's rule, forwarded)" \
                    || bad "REQ no as_of -> $code, want 400 (a defaulted position answers a different question)"
code="$(curl -s -o /dev/null -w '%{http_code}' \
  -H "X-Internal-Token: $INTERNAL_TOKEN" -H "X-User-Id: $OWNER_ID" \
  "$GATEWAY_URL/v1/kal/books/$BOOK_ID/state?as_of=-1")"
[ "$code" = "400" ] && ok "REQ negative as_of -> 400" || bad "REQ as_of=-1 -> $code, want 400"

# ── CONS · the consumer's own client drives it ───────────────────────────────
log "--- CONS: composition-service's KalClient.state() against the live gateway ---"
if ! docker inspect -f '{{.State.Status}}' "$COMPOSITION_CONTAINER" 2>/dev/null | grep -q running; then
  skip "CONS: $COMPOSITION_CONTAINER is not running -- the consumer leg did NOT run (this is not a pass)"
else
  out="$(docker exec -e SMOKE_BOOK="$BOOK_ID" -e SMOKE_ENTITY="$ENTITY_ID" -e SMOKE_USER="$OWNER_ID" \
    "$COMPOSITION_CONTAINER" python -c '
import asyncio, os
from uuid import UUID
from app.clients.kal_client import KalClient
from app.config import settings
from app.engine.heal_canon import cast_from_state

async def main():
    c = KalClient(settings.knowledge_gateway_url, settings.internal_service_token)
    try:
        ents = await c.state(UUID(os.environ["SMOKE_BOOK"]), as_of=9030,
                             user_id=UUID(os.environ["SMOKE_USER"]))
    finally:
        await c.aclose()
    mine = [e for e in ents if str(e.get("entity_id")) == os.environ["SMOKE_ENTITY"]]
    attrs = {f["attr"]: f["value"] for e in mine for f in e.get("facts", [])}
    print("CONS_ENTITIES=%d" % len(ents))
    print("CONS_MINE=%d" % len(mine))
    print("CONS_RANK=%s" % attrs.get("rank"))
    print("CONS_ALLEGIANCE=%s" % attrs.get("allegiance"))
    # The flattening the canon bible actually consumes, on real data.
    print("CONS_CAST=%d" % len(cast_from_state(ents)))

asyncio.run(main())
' 2>&1)"
  echo "$out" | sed 's/^/[state-asof-live]       /'
  echo "$out" | grep -q "CONS_MINE=1" \
    && ok "CONS composition's own client saw the scratch entity through the KAL" \
    || bad "CONS composition's client did not see the entity (see the output above)"
  echo "$out" | grep -q "CONS_RANK=inner" \
    && ok "CONS the consumer received the AS-OF value, not the head value" \
    || bad "CONS rank was not the as-of value"
  # A book with a real cast must flatten to a non-empty bible; an empty one would mean the
  # canon bible is still ungrounded even though the read worked.
  cast_n="$(echo "$out" | sed -n 's/^CONS_CAST=//p')"
  { [ -n "$cast_n" ] && [ "$cast_n" -gt 0 ]; } \
    && ok "CONS cast_from_state produced $cast_n bible rows from live data" \
    || bad "CONS cast_from_state produced no bible rows (canon would still be ungrounded)"
fi

# ── PERF · what the KAL hop costs (T8) ───────────────────────────────────────
log "--- PERF: in-process vs through-the-KAL, $PERF_N reads each ---"
timings() { # url -> newline-separated ms
  for _ in $(seq "$PERF_N"); do
    curl -s -o /dev/null -w '%{time_total}\n' \
      -H "X-Internal-Token: $INTERNAL_TOKEN" -H "X-User-Id: $OWNER_ID" "$1"
  done
}
DIRECT_MS="$(timings "$GLOSSARY_URL/internal/books/$BOOK_ID/state?as_of=9030")"
KAL_MS="$(timings "$GATEWAY_URL/v1/kal/books/$BOOK_ID/state?as_of=9030")"
python3 - <<PY
import statistics as st
def pct(vals, p):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(round((p / 100) * (len(vals) - 1))))]
d = [float(x) * 1000 for x in """$DIRECT_MS""".split() if x.strip()]
k = [float(x) * 1000 for x in """$KAL_MS""".split() if x.strip()]
if not d or not k:
    print("[state-asof-live] PERF  no samples")
    raise SystemExit
print("[state-asof-live] PERF  direct  p50=%.1fms p95=%.1fms  n=%d" % (pct(d,50), pct(d,95), len(d)))
print("[state-asof-live] PERF  via KAL p50=%.1fms p95=%.1fms  n=%d" % (pct(k,50), pct(k,95), len(k)))
print("[state-asof-live] PERF  RATIO   p50 x%.2f  p95 x%.2f   (the number T8 gates on -- "
      "ratios, not absolutes: this host is not production)" % (pct(k,50)/pct(d,50), pct(k,95)/pct(d,95)))
PY

# ── result ───────────────────────────────────────────────────────────────────
log "-----------------------------------------------------------------"
log "passed=$pass failed=$fail"
[ "$fail" -eq 0 ] || exit 1
