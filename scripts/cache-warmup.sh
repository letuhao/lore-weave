#!/usr/bin/env bash
# scripts/cache-warmup.sh — L1.F.4
#
# Top-N active reality cache warm-up. Invoked on world-service boot (or
# manually by SRE post-Sentinel failover) to pre-populate the
# `reality_routing` cache with the N most-recently-active realities.
#
# ## Why warm up
#
# After a cache cold-start (Redis instance restart, Sentinel failover
# to a fresh replica, or simply a deploy that rolled the cache pod),
# the FIRST command for each reality hits Postgres. With 5K active
# realities and a normal command rate, that's a spike of 5K SELECTs
# in the first few seconds — enough to saturate pgbouncer's backend
# pool. Pre-warming with the top-N spreads the load by replaying recent
# routing rows BEFORE the spike.
#
# ## Inputs
#
#   REDIS_URL          e.g. redis://127.0.0.1:16379  (default V1 docker-compose)
#   POSTGRES_URL       libpq URL to the meta DB
#   WARMUP_TOP_N       integer; default 500
#   WARMUP_TTL_SEC     integer; default matches keys.yaml::reality_routing (30)
#
# ## Output
#
# - stdout: line per warmed key (`WARM <reality_id>`)
# - stderr: errors per row + final summary
# - exit 0 if at least 50% of the top-N warmed successfully; non-zero
#   if more than half failed (SRE follow-up via L1.F runbook)
#
# ## Idempotency
#
# Safe to run multiple times. Each invocation overwrites existing
# entries with fresh TTLs (which is the intent — refresh near-expiry
# entries).
#
# Cycle 5 ships the SCRIPT SCAFFOLD with dry-run mode. Production
# Redis + Postgres clients land in cycle 6+ alongside the world-service
# boot wiring. Until then, running this without `--dry-run` exits 2.

set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
    shift
fi

REDIS_URL="${REDIS_URL:-redis://127.0.0.1:16379}"
POSTGRES_URL="${POSTGRES_URL:-postgres://postgres:postgres@127.0.0.1:15432/loreweave_meta?sslmode=disable}"
WARMUP_TOP_N="${WARMUP_TOP_N:-500}"
WARMUP_TTL_SEC="${WARMUP_TTL_SEC:-30}"

echo "[cache-warmup] cycle-5 scaffold"
echo "[cache-warmup] redis=${REDIS_URL} postgres=<redacted> top_n=${WARMUP_TOP_N} ttl=${WARMUP_TTL_SEC}s dry_run=${DRY_RUN}"

if [[ "$DRY_RUN" -ne 1 ]]; then
    echo "[cache-warmup] FATAL: real-mode wiring not yet implemented (cycle 6 dependency)." >&2
    echo "[cache-warmup] Re-run with --dry-run for a no-op simulated warm-up." >&2
    exit 2
fi

# Dry-run path: simulate the SQL + emit one WARM line per simulated row.
SIMULATED=10
echo "[cache-warmup] dry-run: simulating warm-up of ${SIMULATED} realities"
for i in $(seq 1 "$SIMULATED"); do
    echo "WARM lw:reality_routing:simulated-reality-${i}"
done
echo "[cache-warmup] dry-run complete: warmed=${SIMULATED} failed=0"
exit 0
