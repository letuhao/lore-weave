#!/usr/bin/env bash
# diskann-rebuild-scale — how long does the ANN index take to rebuild, ACROSS the parallel-build
# threshold (QC-3, owed by the T25 restore drill).
#
# WHY THIS EXISTS
# ---------------
# The restore drill established that the index rebuild IS the recovery time — 34.3 s of a 35.3 s
# restore at 20 000 rows — and fitted `O(n^1.6)` from two points (5 k and 20 k). Both points sit
# BELOW `diskann.min_vectors_for_parallel_build = 65536`, so both were single-threaded, and
# extrapolating a single-threaded curve across the threshold that turns parallelism ON is
# exactly the kind of number that reads as an RTO and is not one.
#
# This measures on both sides of that threshold at the drill's own 1024 dim, so the two are
# comparable, and prints what the old curve PREDICTED next to what actually happened.
#
# ⚠ The threshold is not the only thing that decides this. Parallel build is bounded by
# `max_parallel_maintenance_workers` and the memory it gets, and the knowledge image ships the
# Postgres defaults — so the script reports those first. A rebuild time measured under settings
# nobody recorded is not reproducible.
#
#   ./scripts/diskann-rebuild-scale.sh [rows-csv]
#   VEC_MAINT_MEM=1GB ./scripts/diskann-rebuild-scale.sh [rows-csv]
#
# The first run of this script found the lever is NOT the parallel threshold. At the image's
# default `maintenance_work_mem = 64MB` the builder logs
#
#     WARNING: Builder neighbor cache is full after processing 14717 vectors
#
# — i.e. the cache binds at ~14.7 k vectors, BELOW the 20 000-row point the restore drill fitted
# its O(n^1.6) curve through and four times below the 65536 parallel threshold. So the drill's
# curve spans a regime change it could not see. `VEC_MAINT_MEM` raises the setting for the index
# build only (session-scoped `SET`, not a server change) so the same rows can be measured on both
# sides of that limit and the two sweeps compared.
#
# Writes only to a throwaway database it creates and drops.

set -uo pipefail

CONTAINER="${VEC_CONTAINER:-lw-t23-vec}"
DB="${VEC_QC3_DB:-lw_vec_qc3}"
DIM="${VEC_DIM:-1024}"
ROWS_CSV="${1:-40000,80000}"
MAINT_MEM="${VEC_MAINT_MEM:-}"
export MSYS_NO_PATHCONV=1

psql_db() { docker exec "$CONTAINER" psql -U postgres -d "$DB" -v ON_ERROR_STOP=1 "$@"; }
psql_adm() { docker exec "$CONTAINER" psql -U postgres -v ON_ERROR_STOP=1 "$@"; }

cleanup() {
  echo
  echo "=== cleanup"
  psql_adm -c "DROP DATABASE IF EXISTS $DB" >/dev/null 2>&1 && echo "  dropped $DB"
}
trap cleanup EXIT

echo "=== settings that bound a parallel build (recorded, because they decide the answer)"
psql_adm -t -A -c "SELECT name || ' = ' || setting || coalesce(' ' || unit, '')
                     FROM pg_settings
                    WHERE name IN ('max_parallel_maintenance_workers','max_worker_processes',
                                   'maintenance_work_mem','max_parallel_workers','shared_buffers')
                    ORDER BY name"
echo "  host cpus visible to the container: $(docker exec "$CONTAINER" nproc)"
if [ -n "$MAINT_MEM" ]; then
  # Session-scoped, applied in the same statement as CREATE INDEX. Deliberately NOT a server
  # change: this measurement must be repeatable against the stock image, and a mutated server
  # would make every LATER measurement in this container quietly incomparable to the first.
  MAINT_SET="SET maintenance_work_mem = '$MAINT_MEM'; "
  echo "  ⚠ OVERRIDE for the index build only: maintenance_work_mem = $MAINT_MEM"
else
  MAINT_SET=""
  echo "  maintenance_work_mem: image default (no override)"
fi

psql_adm -c "DROP DATABASE IF EXISTS $DB" >/dev/null 2>&1
psql_adm -c "CREATE DATABASE $DB" >/dev/null
psql_db -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE" >/dev/null
psql_db -t -A -c "SELECT 'vectorscale ' || extversion FROM pg_extension WHERE extname='vectorscale'"

printf '\n%-10s %-12s %-14s %-16s %-14s %-19s %s\n' \
  "rows" "parallel?" "seed_s" "index_build_s" "index_size" "vs O(n^1.6) 20k" "builder cache"

BASE_ROWS=20000
BASE_SECS=34.3

IFS=',' read -ra ROWS <<< "$ROWS_CSV"
for n in "${ROWS[@]}"; do
  psql_db -c "DROP TABLE IF EXISTS v" >/dev/null

  # `+ 0 * g` is load-bearing, not noise. Without a reference to the outer row, Postgres hoists
  # the uncorrelated subquery to an InitPlan and evaluates it ONCE — every row then gets the
  # SAME vector. T24 shipped a seed helper with that exact bug (3 000 rows, 1 distinct vector),
  # so the distinctness assertion below is not ceremony either.
  seed_start=$(date +%s%3N)
  psql_db -q -c "
    CREATE TABLE v (id bigint PRIMARY KEY, embedding vector($DIM));
    INSERT INTO v (id, embedding)
    SELECT g, (SELECT array_agg(random())::vector
                 FROM generate_series(1, $DIM + 0 * g))
      FROM generate_series(1, $n) g;" >/dev/null || { echo "seed failed at $n"; continue; }
  seed_end=$(date +%s%3N)

  distinct=$(psql_db -t -A -c "SELECT count(DISTINCT embedding) FROM v")
  if [ "$distinct" -lt "$n" ]; then
    echo "  FAIL: $distinct distinct vectors for $n rows — the seed collapsed, numbers meaningless"
    continue
  fi

  # stderr is CAPTURED rather than left to scroll past, because the builder announces the thing
  # this whole measurement turned out to be about on stderr and nowhere else:
  #   "Builder neighbor cache is full after processing N vectors"
  # Reading it per row is what tells you whether a build was memory-bound — the elapsed time
  # alone cannot, and the first run of this script mistook one for the other.
  build_start=$(date +%s%3N)
  build_log=$(psql_db -q -c "${MAINT_SET}CREATE INDEX v_emb ON v USING diskann (embedding vector_cosine_ops)" 2>&1 >/dev/null) \
    || { echo "  index build failed at $n: $build_log"; continue; }
  build_end=$(date +%s%3N)
  # ALL of them, not the first. There is more than one cache: the builder announces
  #   "Builder neighbor cache is full after processing N vectors"      (binds at ~14.7k on 64MB)
  #   "Quantized vector cache is full after processing N vectors"      (binds at ~83.9k on 64MB)
  # and an earlier version of this script printed only the first match, which meant the
  # 100 000-row build reported one limit while it had actually hit two. A measurement whose
  # instrument stops reading at the first finding under-reports exactly where the effect is
  # largest — the `exit` that caused it is deliberately gone.
  cache_full=$(printf '%s\n' "$build_log" \
    | awk 'match($0, /[A-Za-z ]+cache is full after processing [0-9]+/){
             s = substr($0, RSTART, RLENGTH); sub(/ cache is full after processing /, ":", s);
             sub(/^[ \t]*(WARNING:[ \t]*)?/, "", s); out = out (out ? "," : "") s }
           END { print out }')
  [ -n "$cache_full" ] || cache_full="none"

  size=$(psql_db -t -A -c "SELECT pg_size_pretty(pg_relation_size('v_emb'))")
  # Integer milliseconds + awk. Git Bash on Windows has no `bc`, and an inline `python3 -c`
  # here returned empty through the shell layer — a measurement script whose numbers come
  # back blank is worse than one that refuses to run, so this uses only what is present.
  seed_ms=$(( seed_end - seed_start ))
  build_ms=$(( build_end - build_start ))
  seed_s=$(awk -v m=$seed_ms "BEGIN{printf \"%.1f\", m/1000}")
  build_s=$(awk -v m=$build_ms "BEGIN{printf \"%.1f\", m/1000}")
  pred=$(awk -v n=$n -v br=$BASE_ROWS -v bs=$BASE_SECS "BEGIN{printf \"%.1f\", bs*(n/br)^1.6}")
  par=$([ "$n" -ge 65536 ] && echo "eligible" || echo "single")

  printf '%-10s %-12s %-14s %-16s %-14s predicted %-9s cache_full_at=%s\n' \
    "$n" "$par" "$seed_s" "$build_s" "$size" "${pred}s" "$cache_full"
done

echo
echo "Threshold: diskann.min_vectors_for_parallel_build = 65536 — rows at or above it are"
echo "'eligible', which is NOT the same as parallel: the build still needs workers and memory"
echo "from the settings printed at the top."
