#!/usr/bin/env bash
# vector-backup-drill.sh — back up the vector store, destroy it, restore it, prove it.
#
# Plan T25. Decision T4 says vectors are **durable primary data**: restored, never
# recomputed. That is not a preference. Embeddings are produced with the project owner's
# BYOK credential, so "just re-embed it" spends THE USER'S money to recover from OUR data
# loss — at 63 M passage vectors, a great deal of it. A restore path is the only acceptable
# recovery, and the plan's own words are the standard this script has to meet:
#
#     "an untested restore is not a backup"
#
# So this does not verify that a dump FILE exists. It destroys the data and gets it back:
#
#   1. seed a corpus with genuinely distinct vectors
#   2. fingerprint it — row counts, a checksum over every vector, and the ANSWER to a
#      nearest-neighbour query
#   3. pg_dump -Fc
#   4. DROP the tables (the disaster), and prove the data is really gone
#   5. pg_restore
#   6. verify all three fingerprints, and time the phases separately
#
# Step 4 is the one that makes the rest mean anything. A drill that restores over intact
# data verifies nothing — it would pass just as happily if pg_restore were a no-op.
#
# WHAT THIS MEASURES THAT A ROW COUNT WOULD NOT
# ---------------------------------------------
# Restoring an ANN index is not the same as restoring a table. pg_restore REBUILDS the
# index from the data rather than copying its pages, so the recovered graph is a different
# graph — and an approximate index that is a different graph can return different
# neighbours for the same query even though every byte of data is correct. This drill
# therefore checks the exact answer (must be identical — it is arithmetic over restored
# bytes) and the approximate answer (reported, not asserted) separately, and times the
# index rebuild on its own because at scale that IS the recovery time.
#
# Exit codes:  0 pass · 1 a verification failed · 2 misuse / preflight
#
# Usage:
#   scripts/vector-backup-drill.sh --dsn postgresql://…/loreweave_vectors_test [--rows 5000]
#
# db-safety-gate: file-ok -- refuses a DSN whose database is not marked throwaway, BEFORE
# it drops anything, and never connects to a service database.

set -uo pipefail

DSN=""
ROWS=5000
DIM=1024
K=10
KEEP=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dsn)   DSN="$2"; shift 2 ;;
    --rows)  ROWS="$2"; shift 2 ;;
    --dim)   DIM="$2"; shift 2 ;;
    --keep)  KEEP=1; shift ;;
    -h|--help) sed -n '1,45p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[ -n "$DSN" ] || { echo "FAIL(setup): --dsn is required" >&2; exit 2; }

DB="${DSN##*/}"; DB="${DB%%\?*}"
case "$DB" in
  *test*|*smoke*|*audit*|*scratch*|*throwaway*|*tmp*|*sandbox*|*ephemeral*) ;;
  *) echo "REFUSING: database '$DB' is not a throwaway — this script DROPS TABLES." >&2
     exit 2 ;;
esac

TABLE="passage_vectors_${DIM}"
DUMP="$(mktemp -d)/vectors.dump"
pass=0; fail=0
log()  { printf '[vec-drill] %s\n' "$*"; }
ok()   { pass=$((pass+1)); printf '[vec-drill] PASS  %s\n' "$*"; }
bad()  { fail=$((fail+1)); printf '[vec-drill] FAIL  %s\n' "$*"; }
q()    { psql "$DSN" -tAX -v ON_ERROR_STOP=1 -c "$1" 2>&1 | tr -d '\r'; }
run()  { psql "$DSN" -qX -v ON_ERROR_STOP=1 -c "SET client_min_messages TO warning;" -c "$1" >/dev/null; }
now()  { date +%s.%N; }
took() { awk -v a="$1" -v b="$2" 'BEGIN{printf "%.1f", b-a}'; }

command -v pg_dump >/dev/null || { echo "FAIL(setup): pg_dump not on PATH" >&2; exit 2; }
psql "$DSN" -tAc "SELECT 1" >/dev/null 2>&1 || { echo "FAIL(setup): cannot reach $DB" >&2; exit 2; }

cleanup() { [ "$KEEP" = "1" ] || rm -rf "$(dirname "$DUMP")"; }
trap cleanup EXIT

# ── 1. seed ──────────────────────────────────────────────────────────────────
log "seeding $ROWS rows × ${DIM}d into $TABLE"
run "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;"
run "DROP TABLE IF EXISTS $TABLE CASCADE"
run "CREATE TABLE $TABLE (
       id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id text NOT NULL,
       project_id text, source_type text NOT NULL, source_id text NOT NULL,
       chunk_index integer NOT NULL, text text NOT NULL, embedding vector($DIM) NOT NULL,
       embedding_model text, is_hub boolean NOT NULL DEFAULT false, chapter_index integer,
       canon boolean NOT NULL DEFAULT true, block_index integer,
       source_lang text NOT NULL DEFAULT 'unknown', mixed boolean NOT NULL DEFAULT false,
       content_hash text, updated_at timestamptz NOT NULL DEFAULT now(),
       UNIQUE (user_id, source_type, source_id, chunk_index))"
# `+ 0 * g` CORRELATES the subquery. Uncorrelated, Postgres hoists it into an InitPlan and
# evaluates it ONCE however volatile random() is — which is how a sibling test seeded 3000
# rows holding one distinct vector and measured nothing (T24). A drill over identical
# vectors would "verify" a restore that returned any row at all.
run "INSERT INTO $TABLE (user_id, project_id, source_type, source_id, chunk_index, text, embedding)
     SELECT 'drill-user', 'drill-project', 'chapter', 'p-'||g, 0, 'row '||g,
            (SELECT array_agg(random())::vector($DIM) FROM generate_series(1, $DIM + 0 * g))
     FROM generate_series(1, $ROWS) g"
run "CREATE INDEX ${TABLE}_emb ON $TABLE USING diskann (embedding vector_cosine_ops)"
run "CREATE INDEX ${TABLE}_tenant ON $TABLE (user_id, project_id)"
run "ANALYZE $TABLE"

distinct="$(q "SELECT count(DISTINCT embedding::text) FROM $TABLE")"
[ "$distinct" = "$ROWS" ] \
  && ok "seed produced $ROWS distinct vectors" \
  || { bad "seed collapsed to $distinct distinct vectors — the drill would prove nothing"; exit 1; }

# ── 2. fingerprint ───────────────────────────────────────────────────────────
# A checksum over every vector, order-independent (sum of per-row hashes) so it does not
# depend on physical row order, which a restore is free to change.
before_rows="$(q "SELECT count(*) FROM $TABLE")"
before_sum="$(q "SELECT sum(hashtext(embedding::text)::bigint) FROM $TABLE")"
probe="$(q "SELECT embedding::text FROM $TABLE WHERE source_id = 'p-42'")"
before_exact="$(q "SET LOCAL enable_indexscan=off; SET LOCAL enable_bitmapscan=off;
                   SELECT string_agg(source_id, ',' ORDER BY source_id) FROM (
                     SELECT source_id FROM $TABLE ORDER BY embedding <=> '$probe'::vector LIMIT $K) t")"
before_ann="$(q "SELECT string_agg(source_id, ',' ORDER BY source_id) FROM (
                   SELECT source_id FROM $TABLE ORDER BY embedding <=> '$probe'::vector LIMIT $K) t")"
log "fingerprint: rows=$before_rows checksum=$before_sum"

# ── 3. back up ───────────────────────────────────────────────────────────────
t0="$(now)"
pg_dump -Fc -f "$DUMP" -t "$TABLE" "$DSN" || { bad "pg_dump failed"; exit 1; }
t1="$(now)"
dump_bytes="$(wc -c < "$DUMP" | tr -d ' ')"
table_bytes="$(q "SELECT pg_total_relation_size('$TABLE')")"
log "backup: $(took "$t0" "$t1")s  dump=$((dump_bytes/1024))kB  live=$((table_bytes/1024))kB"

# ── 4. destroy, and PROVE it ─────────────────────────────────────────────────
run "DROP TABLE $TABLE CASCADE"
if psql "$DSN" -tAc "SELECT count(*) FROM $TABLE" >/dev/null 2>&1; then
  bad "the table survived DROP — this drill cannot tell a restore from a no-op"; exit 1
fi
ok "data destroyed (the drill is restoring, not overwriting)"

# ── 5. restore ───────────────────────────────────────────────────────────────
t2="$(now)"
pg_restore -d "$DSN" --no-owner --no-privileges "$DUMP" >/dev/null 2>&1 \
  || { bad "pg_restore failed"; exit 1; }
t3="$(now)"
restore_s="$(took "$t2" "$t3")"

# Time the ANN index rebuild on its own: pg_restore re-CREATEs it from the data rather than
# copying pages, and at scale that rebuild is the recovery time, not the data copy.
idx_present="$(q "SELECT count(*) FROM pg_indexes WHERE indexname = '${TABLE}_emb'")"
run "DROP INDEX IF EXISTS ${TABLE}_emb"
t4="$(now)"
run "CREATE INDEX ${TABLE}_emb ON $TABLE USING diskann (embedding vector_cosine_ops)"
t5="$(now)"
index_s="$(took "$t4" "$t5")"
run "ANALYZE $TABLE"
log "restore: ${restore_s}s total  (index rebuild alone: ${index_s}s)"

# ── 6. verify ────────────────────────────────────────────────────────────────
[ "$idx_present" = "1" ] \
  && ok "the dump carried the ANN index definition" \
  || bad "the restored table has NO ANN index — every search would silently seq-scan"

after_rows="$(q "SELECT count(*) FROM $TABLE")"
[ "$after_rows" = "$before_rows" ] && ok "row count $after_rows" || bad "rows $before_rows → $after_rows"

after_sum="$(q "SELECT sum(hashtext(embedding::text)::bigint) FROM $TABLE")"
[ "$after_sum" = "$before_sum" ] \
  && ok "every vector is byte-identical (checksum $after_sum)" \
  || bad "vector checksum changed: $before_sum → $after_sum"

after_exact="$(q "SET LOCAL enable_indexscan=off; SET LOCAL enable_bitmapscan=off;
                  SELECT string_agg(source_id, ',' ORDER BY source_id) FROM (
                    SELECT source_id FROM $TABLE ORDER BY embedding <=> '$probe'::vector LIMIT $K) t")"
[ "$after_exact" = "$before_exact" ] \
  && ok "the EXACT nearest-neighbour answer is unchanged — the restore returns the same results, not merely the same rows" \
  || bad "exact top-$K changed across the restore: [$before_exact] → [$after_exact]"

# Reported, NOT asserted. pg_restore rebuilds the ANN graph rather than copying it, so the
# recovered index is a different graph and may legitimately return different approximate
# neighbours. Failing on that would make a correct restore look broken; hiding it would let
# a real recall regression pass unnoticed. So it is measured and printed.
after_ann="$(q "SELECT string_agg(source_id, ',' ORDER BY source_id) FROM (
                  SELECT source_id FROM $TABLE ORDER BY embedding <=> '$probe'::vector LIMIT $K) t")"
if [ "$after_ann" = "$before_ann" ]; then
  log "NOTE  the rebuilt ANN index returns the same top-$K as the original"
else
  overlap="$(python -c "
a=set('''$before_ann'''.split(',')); b=set('''$after_ann'''.split(','))
print(f'{len(a&b)}/{len(a)}')" 2>/dev/null || echo '?')"
  # The explanation is conditioned on the checksum having ACTUALLY passed. The first
  # version asserted "data is intact (checksum matched)" unconditionally, and printed
  # exactly that during the bite run where the checksum had just failed — a reassuring
  # sentence on the one run that most needed an alarming one.
  if [ "$fail" -eq 0 ]; then
    log "NOTE  the rebuilt ANN index returns a DIFFERENT top-$K (overlap $overlap) — expected:"
    log "      every check above passed, so the data is intact and it is the APPROXIMATION"
    log "      that differs: pg_restore rebuilds the graph rather than copying it. QC-3"
    log "      should re-measure recall after a real restore instead of assuming it survived."
  else
    log "NOTE  the top-$K also changed (overlap $overlap), but checks above already FAILED —"
    log "      do not read this as an index-rebuild artefact; the data itself is wrong."
  fi
fi

log "-----------------------------------------------------------------"
log "rows=$before_rows dim=$DIM  dump=$((dump_bytes/1024))kB (live $((table_bytes/1024))kB)"
log "backup=$(took "$t0" "$t1")s  restore=${restore_s}s  of which index rebuild=${index_s}s"
log "passed=$pass failed=$fail"
[ "$fail" -eq 0 ] || exit 1
