#!/usr/bin/env bash
# state-asof-ceiling.sh — plan T10: the synthetic 4,000-chapter ceiling for `state@as_of`.
#
# The dev corpus tops out at 26k facts on a 97-chapter book. That is not where this read
# breaks, so the ceiling has to be BUILT: 1,500 entities x 12 single-valued attributes x 60
# revisions = 1.08M facts on ONE book, revisions spread across ordinals 0..3,960.
#
# What the shape is chosen to expose, and what it deliberately is not:
#
#   - The as-of predicate matches ~18,000 rows AT ANY POSITION, no matter how long the book
#     is: at one ordinal exactly one interval per (entity, attribute) can cover it. So book
#     length grows the rows SCANNED, never the rows RETURNED. That asymmetry is the whole
#     point of the ceiling run, and it is what makes the T9 index a scan fix rather than the
#     sort fix the plan originally called it.
#   - Nine decoy books are seeded alongside so `book_id` is SELECTIVE. Without them the
#     target book IS the table, a sequential scan is genuinely the right plan, and the rig
#     would "prove" the index useless for a reason production never has.
#
#   bash scripts/perf/state-asof-ceiling.sh
#   CEILING_DB=loreweave_glossary_ceiling_test bash scripts/perf/state-asof-ceiling.sh
#
# Exit 0 = the run completed and printed its table; 2 = setup could not run.
#
# db-safety-gate: file-ok -- this script REFUSES any database whose name lacks a throwaway
# marker (the same rule internal/testsafe.EnsureThrowawayDB enforces for Go tests), it
# CREATES its own database rather than writing into an existing one, and it drops that
# database at the end. It never connects to a service DB.

set -uo pipefail

PG_CONTAINER="${PG_CONTAINER:-infra-postgres-1}"
PG_USER="${PG_USER:-loreweave}"
CEILING_DB="${CEILING_DB:-loreweave_glossary_ceiling_test}"
KEEP_DB="${KEEP_DB:-0}"

# Rig dimensions. Entities x attrs x revisions = facts; revisions x STRIDE = chapter span.
ENTITIES="${ENTITIES:-1500}"
ATTRS="${ATTRS:-12}"
REVISIONS="${REVISIONS:-60}"
STRIDE="${STRIDE:-66}"          # 60 revisions x 66 = 3,960 -- a 4,000-chapter book
DECOY_BOOKS="${DECOY_BOOKS:-9}"
AS_OF="${AS_OF:-2000}"          # mid-book: the worst case for the as-of filter
RUNS="${RUNS:-5}"

log() { printf '[asof-ceiling] %s\n' "$*"; }
die() { printf '[asof-ceiling] FAIL(setup): %s\n' "$*"; exit 2; }

# The same guard testsafe.EnsureThrowawayDB applies in Go. This script writes 2.16M rows and
# drops its database at the end; pointed at a service DB that is a catastrophe, so the name
# must carry a throwaway marker or nothing runs.
case "$CEILING_DB" in
  *test*|*smoke*|*audit*|*scratch*|*tmp*) ;;
  *) die "CEILING_DB='$CEILING_DB' is not a recognizable throwaway database name (needs test/smoke/audit/scratch/tmp). This script CREATES and DROPS its database." ;;
esac

docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 \
  || die "postgres container '$PG_CONTAINER' is not accepting connections"

P()  { docker exec -i "$PG_CONTAINER" psql -qtAX -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$CEILING_DB" -c "$1" 2>&1 | tr -d '\r'; }
PA() { docker exec -i "$PG_CONTAINER" psql -qtAX -v ON_ERROR_STOP=1 -U "$PG_USER" -d postgres -c "$1" 2>&1 | tr -d '\r'; }

cleanup() {
  if [ "$KEEP_DB" = "1" ]; then
    log "KEEP_DB=1 — leaving $CEILING_DB in place for inspection"
    return
  fi
  PA "DROP DATABASE IF EXISTS $CEILING_DB;" >/dev/null 2>&1
  log "dropped $CEILING_DB"
}

log "creating $CEILING_DB ..."
PA "DROP DATABASE IF EXISTS $CEILING_DB;" >/dev/null 2>&1
PA "CREATE DATABASE $CEILING_DB;" >/dev/null || die "could not create $CEILING_DB"
trap cleanup EXIT

# Schema comes from the real migration chain, not a hand-written CREATE TABLE — a rig on a
# hand-copied schema measures a table that does not exist in production. This also applies
# 0062, so the index under test is the SHIPPED one.
log "applying the migration chain (this also applies 0062, the index under test) ..."
URL="postgres://${PG_USER}:$(docker exec "$PG_CONTAINER" printenv POSTGRES_PASSWORD | tr -d '\r')@localhost:5555/${CEILING_DB}?sslmode=disable"
( cd "$(dirname "$0")/../../services/glossary-service" \
  && GLOSSARY_TEST_DB_URL="$URL" go test ./internal/migrate/ \
       -run TestEntityFactsAsOfIndex_ExistsAfterTheChain -count=1 ) >/dev/null 2>&1 \
  || die "migration chain did not apply — run it manually to see the error"

BOOK='019f0000-00ff-7000-8000-000000000099'
log "seeding: ${ENTITIES} entities x ${ATTRS} attrs x ${REVISIONS} revisions on the target book, plus ${DECOY_BOOKS} decoy books ..."
P "
-- A fresh chain DB has an empty book_kinds (no book has adopted an ontology yet), and
-- glossary_entities.kind_id is NOT NULL — so the rig mints its own kind rather than
-- assuming one exists. The first version of this script did assume, and died with a
-- null-violation that read as 'seeding failed'.
INSERT INTO book_kinds (book_kind_id, book_id, code, name)
VALUES ('019f4000-0000-7000-8000-000000000001'::uuid, '${BOOK}'::uuid, 'character', 'Character')
ON CONFLICT DO NOTHING;

INSERT INTO glossary_entities (entity_id, book_id, kind_id, status, short_description)
SELECT ('019f3000-0000-7000-8000-' || lpad(g::text, 12, '0'))::uuid, '${BOOK}'::uuid,
       '019f4000-0000-7000-8000-000000000001'::uuid, 'active', 'ceiling rig'
FROM generate_series(1, ${ENTITIES}) g;

INSERT INTO entity_facts
  (book_id, entity_id, fact_kind, attr_or_predicate, value, valid_from_ordinal, valid_to_ordinal, cardinality)
SELECT '${BOOK}'::uuid, ('019f3000-0000-7000-8000-' || lpad(g::text, 12, '0'))::uuid,
       'attribute', 'attr_' || a, 'v' || g || '_' || a || '_' || r,
       r * ${STRIDE}, CASE WHEN r < ${REVISIONS} - 1 THEN (r + 1) * ${STRIDE} ELSE NULL END, 'single'
FROM generate_series(1, ${ENTITIES}) g, generate_series(1, ${ATTRS}) a, generate_series(0, ${REVISIONS} - 1) r;

INSERT INTO glossary_entities (entity_id, book_id, kind_id, status, short_description)
SELECT ('019f2000-000' || b || '-7000-8000-' || lpad(g::text, 12, '0'))::uuid,
       ('019f0000-000' || b || '-7000-8000-000000000099')::uuid,
       '019f4000-0000-7000-8000-000000000001'::uuid, 'active', 'decoy'
FROM generate_series(1, ${DECOY_BOOKS}) b, generate_series(1, ${ENTITIES}) g;

INSERT INTO entity_facts
  (book_id, entity_id, fact_kind, attr_or_predicate, value, valid_from_ordinal, valid_to_ordinal, cardinality)
SELECT ('019f0000-000' || b || '-7000-8000-000000000099')::uuid,
       ('019f2000-000' || b || '-7000-8000-' || lpad(g::text, 12, '0'))::uuid,
       'attribute', 'attr_' || a, 'v' || g || '_' || a || '_' || r,
       r * 16, CASE WHEN r < 5 THEN (r + 1) * 16 ELSE NULL END, 'single'
FROM generate_series(1, ${DECOY_BOOKS}) b, generate_series(1, ${ENTITIES}) g,
     generate_series(1, ${ATTRS}) a, generate_series(0, 5) r;
" >/dev/null || die "seeding failed"

# VACUUM (ANALYZE), not ANALYZE alone. An Index ONLY Scan is only available once the
# visibility map marks pages all-visible, and a bulk insert leaves it unset — so a rig that
# skips this measures the index at its Index-Scan cost and concludes it does not help.
# (This script did exactly that on its first run: identical timings with and without.)
P "ANALYZE glossary_entities;" >/dev/null
docker exec -i "$PG_CONTAINER" psql -qtAX -U "$PG_USER" -d "$CEILING_DB" -c "VACUUM (ANALYZE) entity_facts;" >/dev/null 2>&1

# REINDEX, and here is why it is not cheating. The chain creates this index on an EMPTY
# table, so the rig then grows it through a 2M-row insert that lands in seconds. That
# produces a ~40% bloated index (301 MB vs 216 MB rebuilt) and the planner correctly
# refuses it. A real deployment writes those facts over months with autovacuum running, so
# the bloat is an artifact of HOW the rig loads, not of the workload it models. Measuring
# the bloated index would answer a question nobody has.
log "reindexing after the bulk load (the seeding method bloats it, the workload does not) ..."
P "REINDEX INDEX idx_entity_facts_book_asof;" >/dev/null
docker exec -i "$PG_CONTAINER" psql -qtAX -U "$PG_USER" -d "$CEILING_DB" -c "VACUUM (ANALYZE) entity_facts;" >/dev/null 2>&1

log "target book facts: $(P "SELECT count(*) FROM entity_facts WHERE book_id='${BOOK}'::uuid;")"
log "table total      : $(P "SELECT count(*) FROM entity_facts;")"
log "table / index size: $(P "SELECT pg_size_pretty(pg_relation_size('entity_facts')) || ' / ' || pg_size_pretty(pg_relation_size('idx_entity_facts_book_asof'));")"

# The query under test is state_handler.go's, verbatim in shape.
cat > /tmp/asof-ceiling-query.sql <<SQL
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT DISTINCT ON (f.entity_id, f.attr_or_predicate)
       f.entity_id, f.attr_or_predicate, f.value, f.fact_kind, f.valid_from_ordinal,
       count(*) OVER () AS pre_distinct_rows
FROM entity_facts f
JOIN glossary_entities e ON e.entity_id = f.entity_id AND e.book_id = f.book_id
WHERE f.book_id = '${BOOK}'::uuid
  AND f.cardinality = 'single' AND f.invalidated_at IS NULL
  AND f.valid_from_ordinal <= ${AS_OF} AND ${AS_OF} < f.valid_to_eff
  AND e.deleted_at IS NULL AND e.permanently_deleted_at IS NULL
ORDER BY f.entity_id, f.attr_or_predicate, f.valid_from_ordinal DESC;
SQL

median_ms() {
  for _ in $(seq "$RUNS"); do
    docker exec -i "$PG_CONTAINER" psql -qtAX -U "$PG_USER" -d "$CEILING_DB" < /tmp/asof-ceiling-query.sql 2>&1 \
      | tr -d '\r' | grep 'Execution Time' | sed 's/.*: //; s/ ms//'
  done | sort -n | sed -n "$(( (RUNS + 1) / 2 ))p"
}
scan_node() {
  # `[a-z ]*` cannot match "using idx_entity_facts_book_asof" — index names carry underscores
  # and digits. The first version of this line silently matched nothing and the result table
  # reported the wrong node for both runs.
  docker exec -i "$PG_CONTAINER" psql -qtAX -U "$PG_USER" -d "$CEILING_DB" < /tmp/asof-ceiling-query.sql 2>&1 \
    | tr -d '\r' | grep -oE '(Index Only Scan|Index Scan|Seq Scan|Bitmap Heap Scan)( using [A-Za-z0-9_]+)? on entity_facts' | head -1
}

log "measuring WITH the T9 index (${RUNS} runs, median) ..."
WITH_MS="$(median_ms)"; WITH_NODE="$(scan_node)"

# Non-vacuity guard. If the planner did not choose the index, every number below compares
# the same plan against itself and the "ratio" is host noise wearing a decimal point. Say so
# and stop rather than publish it.
case "$WITH_NODE" in
  *"Index Only Scan using idx_entity_facts_book_asof"*) ;;
  *) printf '[asof-ceiling] FAIL: the planner did NOT choose idx_entity_facts_book_asof — it used: %s\n' "${WITH_NODE:-<no entity_facts scan node found>}"
     printf '[asof-ceiling]       Any ratio below would compare one plan with itself. Common cause:\n'
     printf '[asof-ceiling]       the visibility map is unset (needs VACUUM after the bulk seed), so an\n'
     printf '[asof-ceiling]       Index ONLY Scan is not available to the planner.\n'
     exit 1 ;;
esac

# The bite the plan asks for. Dropping the index must move the plan, not just the clock --
# a timing that changed by itself proves nothing about which index was responsible.
log "dropping idx_entity_facts_book_asof and re-measuring (the bite) ..."
P "DROP INDEX idx_entity_facts_book_asof;" >/dev/null
P "ANALYZE entity_facts;" >/dev/null
WITHOUT_MS="$(median_ms)"; WITHOUT_NODE="$(scan_node)"

printf '\n[asof-ceiling] ── result ─────────────────────────────────────────────\n'
printf '[asof-ceiling]   as_of=%s over %s facts in one book (%s total)\n' \
  "$AS_OF" "$(P "SELECT count(*) FROM entity_facts WHERE book_id='${BOOK}'::uuid;")" \
  "$(P "SELECT count(*) FROM entity_facts;")"
printf '[asof-ceiling]   WITH    idx_entity_facts_book_asof : %8s ms   %s\n' "$WITH_MS" "$WITH_NODE"
printf '[asof-ceiling]   WITHOUT it (bite)                  : %8s ms   %s\n' "$WITHOUT_MS" "$WITHOUT_NODE"
if [ -n "$WITH_MS" ] && [ -n "$WITHOUT_MS" ]; then
  # Heredoc, not `python3 -c`: on a Windows host the -c form of the launcher can exit
  # silently with no output, which turned this line into a bare "ratio : x".
  RATIO="$(python3 - "$WITHOUT_MS" "$WITH_MS" <<'PY' | tr -d '\r'
import sys
print(f"{float(sys.argv[1]) / float(sys.argv[2]):.2f}")
PY
)"
  printf '[asof-ceiling]   ratio                              : x%s\n' "${RATIO:-?}"
fi
printf '[asof-ceiling]   Ratios, not absolutes: this host is not production.\n'
