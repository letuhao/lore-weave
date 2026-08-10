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
#
# Writes only to a throwaway database it creates and drops.

set -uo pipefail

CONTAINER="${VEC_CONTAINER:-lw-t23-vec}"
DB="${VEC_QC3_DB:-lw_vec_qc3}"
DIM="${VEC_DIM:-1024}"
ROWS_CSV="${1:-40000,80000}"
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

psql_adm -c "DROP DATABASE IF EXISTS $DB" >/dev/null 2>&1
psql_adm -c "CREATE DATABASE $DB" >/dev/null
psql_db -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE" >/dev/null
psql_db -t -A -c "SELECT 'vectorscale ' || extversion FROM pg_extension WHERE extname='vectorscale'"

printf '\n%-10s %-12s %-14s %-16s %-14s %s\n' \
  "rows" "parallel?" "seed_s" "index_build_s" "index_size" "vs O(n^1.6) from 20k"

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

  build_start=$(date +%s%3N)
  psql_db -q -c "CREATE INDEX v_emb ON v USING diskann (embedding vector_cosine_ops)" >/dev/null \
    || { echo "  index build failed at $n"; continue; }
  build_end=$(date +%s%3N)

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

  printf '%-10s %-12s %-14s %-16s %-14s predicted %ss\n' \
    "$n" "$par" "$seed_s" "$build_s" "$size" "$pred"
done

echo
echo "Threshold: diskann.min_vectors_for_parallel_build = 65536 — rows at or above it are"
echo "'eligible', which is NOT the same as parallel: the build still needs workers and memory"
echo "from the settings printed at the top."
