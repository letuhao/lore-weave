#!/usr/bin/env bash
# scripts/perf/w4-pgvector-recall.sh
#
# W4.3 — pgvector HNSW recall comparator, LIVE (closes D-S7-PGVECTOR-RECALL).
#
# The S4 pgvector probe asserts presence + dim only. This adds a RECALL/quality
# check: seed K random 1536-d vectors + an HNSW index (m=16, ef_construction=64 —
# mirrors 0008), then for Q queries compare the APPROX top-k (HNSW) to the EXACT
# top-k (brute-force seq scan), recall@k = |approx ∩ exact| / k. Assert mean
# recall ≥ a threshold at default ef_search.
#
# Non-vacuity guards (plan-review):
#   * the EXACT pass MUST be a real Seq Scan (enable_indexscan/bitmapscan off) —
#     EXPLAIN is asserted, else "exact" silently rides the HNSW index → recall≈1
#     vacuously.
#   * the APPROX pass MUST be an Index Scan — EXPLAIN asserted.
#   * BITE: lower hnsw.ef_search → recall collapses well below the clean recall →
#     the comparator CATCHES the quality regression. A vacuous comparator (index
#     vs itself) would not move.
#
# Verdict: NOTRUN(2) pgvector/infra absent; FAIL(1) clean recall < threshold OR
# EXPLAIN wrong OR the low-ef bite does NOT drop recall; PASS(0). foundation-dev PG.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
COMPOSE="infra/foundation-dev/docker-compose.yml"
SHARD_C="foundation-dev-postgres"
DB="w4_recall"
K="${W4_K:-2000}"      # seeded vectors
Q="${W4_Q:-20}"        # query vectors
TOPK="${W4_TOPK:-10}"  # k for recall@k
THRESH="${W4_RECALL_THRESH:-0.90}"
EF_CLEAN="${W4_EF_CLEAN:-40}"   # default-ish ef_search
EF_BITE="${W4_EF_BITE:-2}"      # degraded ef_search (the bite)

log()    { printf '[w4-recall] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }
require() {
  docker compose -f "$COMPOSE" up -d postgres-foundation >/dev/null 2>&1 || notrun "could not start foundation-dev postgres"
  local i
  for i in $(seq 1 30); do
    docker exec "$SHARD_C" pg_isready -U "$PG_USER" >/dev/null 2>&1 && return 0
    sleep 2
  done
  notrun "foundation-dev postgres not ready"
}
psql_adm() { docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation "$@"; }
psql_db()  { docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" "$@"; }
scalar()   { docker exec -i "$SHARD_C" psql -tA -U "$PG_USER" -d "$DB" -c "$1" | tr -d '[:space:]'; }

setup() {
  psql_adm -c "DROP DATABASE IF EXISTS ${DB} WITH (FORCE)" >/dev/null
  psql_adm -c "CREATE DATABASE ${DB}" >/dev/null
  psql_db -c "CREATE EXTENSION IF NOT EXISTS vector" >/dev/null 2>&1 || notrun "pgvector extension unavailable"
  psql_db -c "CREATE TABLE vecs (id int PRIMARY KEY, embedding vector(1536) NOT NULL)" >/dev/null
  # Seed K DISTINCT random vectors. The inner series length is written
  # `1536 + (g - g)` (= 1536) so the generation CORRELATES to the outer row g —
  # forcing PG to re-evaluate the volatile random() per row. Without the
  # correlation PG hoists the subquery + every row is identical (all distances 0 →
  # recall meaningless; verified during build). A post-seed distinctness assert
  # guards this so the idiom can't silently regress.
  psql_db -c "INSERT INTO vecs (id, embedding)
      SELECT g, ARRAY(SELECT random() FROM generate_series(1, 1536 + (g - g)))::vector
      FROM generate_series(1, ${K}) g" >/dev/null || notrun "seed vectors failed"
  local distinct; distinct="$(scalar "SELECT count(DISTINCT embedding) FROM vecs")"
  [ "${distinct:-0}" = "${K}" ] || notrun "seeded vectors not distinct (${distinct}/${K}) — the per-row randomness idiom regressed"
  # HNSW index mirroring 0008 (m=16, ef_construction=64), l2 opclass ↔ the <-> operator.
  psql_db -c "CREATE INDEX vecs_hnsw ON vecs USING hnsw (embedding vector_l2_ops) WITH (m=16, ef_construction=64)" >/dev/null \
    || notrun "hnsw index build failed"
  local n; n="$(scalar "SELECT count(*) FROM vecs")"
  [ "${n:-0}" = "${K}" ] || notrun "expected ${K} vectors, got ${n}"
  log "w4_recall ready (${K} vectors, hnsw m=16 ef_construction=64)"
}

# Build exact_topk ONCE via a forced brute-force seq scan, asserting the plan really
# is a Seq Scan (else the "exact" set silently used the HNSW index → vacuous recall).
build_exact() {
  local plan
  plan="$(docker exec -i "$SHARD_C" psql -tA -U "$PG_USER" -d "$DB" <<SQL
SET enable_indexscan=off; SET enable_bitmapscan=off;
EXPLAIN SELECT v.id FROM vecs v ORDER BY v.embedding <-> (SELECT embedding FROM vecs WHERE id=1) LIMIT ${TOPK};
SQL
)"
  printf '%s' "$plan" | grep -qi 'Seq Scan on vecs' || fail "EXACT pass did NOT use a Seq Scan (would ride the HNSW index → vacuous): ${plan}"
  docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" <<SQL >/dev/null || fail "build exact_topk failed"
SET enable_indexscan=off; SET enable_bitmapscan=off;
DROP TABLE IF EXISTS exact_topk;
CREATE TABLE exact_topk AS
  SELECT q.id AS qid,
         array(SELECT v.id FROM vecs v ORDER BY v.embedding <-> q.embedding LIMIT ${TOPK}) AS ids
  FROM (SELECT id, embedding FROM vecs ORDER BY id LIMIT ${Q}) q;
SQL
  log "exact_topk built (Q=${Q}, k=${TOPK}, forced Seq Scan)"
}

# Compute mean recall@k of the HNSW approx top-k vs exact_topk at a given ef_search.
# Asserts the approx pass is an Index Scan (else it's not testing the index).
recall_at() {
  local ef="$1" plan
  plan="$(docker exec -i "$SHARD_C" psql -tA -U "$PG_USER" -d "$DB" <<SQL
SET hnsw.ef_search=${ef};
EXPLAIN SELECT v.id FROM vecs v ORDER BY v.embedding <-> (SELECT embedding FROM vecs WHERE id=1) LIMIT ${TOPK};
SQL
)"
  printf '%s' "$plan" | grep -qi 'Index Scan using vecs_hnsw' || fail "APPROX pass (ef=${ef}) did NOT use the HNSW index: ${plan}"
  # Build approx_topk at this ef_search (quiet), then return ONLY the recall scalar.
  docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" <<SQL >/dev/null || fail "build approx_topk (ef=${ef}) failed"
SET hnsw.ef_search=${ef};
DROP TABLE IF EXISTS approx_topk;
CREATE TABLE approx_topk AS
  SELECT q.id AS qid,
         array(SELECT v.id FROM vecs v ORDER BY v.embedding <-> q.embedding LIMIT ${TOPK}) AS ids
  FROM (SELECT id, embedding FROM vecs ORDER BY id LIMIT ${Q}) q;
SQL
  scalar "SELECT round(avg(
      cardinality(ARRAY(SELECT unnest(a.ids) INTERSECT SELECT unnest(x.ids)))::numeric / ${TOPK}
    ), 4)
  FROM exact_topk a JOIN approx_topk x USING (qid)"
}

main() {
  require; setup; build_exact

  # Clean recall at default ef_search must meet the threshold.
  clean="$(recall_at "${EF_CLEAN}")"
  log "clean recall@${TOPK} (ef_search=${EF_CLEAN}) = ${clean}  (threshold ${THRESH})"
  awk -v r="$clean" -v t="$THRESH" 'BEGIN{exit !(r+0 >= t+0)}' \
    || fail "clean recall ${clean} < threshold ${THRESH} — HNSW quality below bar"
  log "PASS(clean): recall ${clean} ≥ ${THRESH}"

  # BITE: a degraded ef_search must drop recall WELL below the clean recall.
  bite="$(recall_at "${EF_BITE}")"
  log "bite recall@${TOPK} (ef_search=${EF_BITE}) = ${bite}"
  awk -v b="$bite" -v c="$clean" 'BEGIN{exit !(b+0 < c+0 - 0.10)}' \
    || fail "bite VACUOUS: low ef_search recall ${bite} did NOT drop meaningfully below clean ${clean} — the comparator is not measuring real recall"
  log "PASS(bite): degraded ef_search recall ${bite} ≪ clean ${clean} — the comparator CATCHES the quality regression (non-vacuous)"
}
main "$@"
