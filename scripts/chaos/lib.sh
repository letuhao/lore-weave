#!/usr/bin/env bash
# Shared helpers for the T2-close-3 chaos scripts. Sourced by
# c05_redis_restart.sh / c06_neo4j_drift.sh / c08_bulk_cascade.sh.
#
# Conventions:
#   - All functions write to stderr so a script's stdout stays clean
#     for the one-line PASS/FAIL at the very end.
#   - All functions exit 1 on any tooling failure (docker missing, a
#     container not running, psql connection refused, etc.) rather
#     than silently skipping — a chaos run must either assert clearly
#     or fail clearly; "maybe-pass" is the failure mode we're
#     trying to prevent.
#
# Every function assumes the lore-weave compose stack is up with the
# default project name (infra-postgres-1 / infra-redis-1 /
# infra-neo4j-1 / infra-knowledge-service-1). If the user launched
# the stack under a different compose project name, set
# LOREWEAVE_INFRA_PREFIX=<prefix> before running and every helper
# picks it up.

set -euo pipefail

: "${LOREWEAVE_INFRA_PREFIX:=infra}"

POSTGRES_CONTAINER="${LOREWEAVE_INFRA_PREFIX}-postgres-1"
REDIS_CONTAINER="${LOREWEAVE_INFRA_PREFIX}-redis-1"
NEO4J_CONTAINER="${LOREWEAVE_INFRA_PREFIX}-neo4j-1"
KNOWLEDGE_CONTAINER="${LOREWEAVE_INFRA_PREFIX}-knowledge-service-1"

PG_USER="${POSTGRES_USER:-loreweave}"
PG_PASSWORD="${POSTGRES_PASSWORD:-loreweave_dev}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
# Default matches NEO4J_AUTH in infra/docker-compose.yml. Override
# via env if your local stack uses different creds.
NEO4J_PASSWORD="${NEO4J_PASSWORD:-loreweave_dev_neo4j}"

# ── logging ────────────────────────────────────────────────────────

log_ts()   { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
log_step() { printf '[%s] \033[0;34m→\033[0m %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
log_pass() { printf '[%s] \033[0;32mPASS\033[0m %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
log_fail() { printf '[%s] \033[0;31mFAIL\033[0m %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
log_warn() { printf '[%s] \033[0;33m!\033[0m %s\n' "$(date +%H:%M:%S)" "$*" >&2; }

die() {
    log_fail "$*"
    exit 1
}

# ── preconditions ──────────────────────────────────────────────────

require_tools() {
    # `docker` is the only hard dep — all container I/O goes
    # through `docker exec` into the infra containers, which have
    # psql / redis-cli / cypher-shell baked in.
    command -v docker >/dev/null 2>&1 || die "missing required tool: docker"
}

require_container_running() {
    local name="$1"
    local status
    status=$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null) \
        || die "container not found: $name (set LOREWEAVE_INFRA_PREFIX if your compose project name differs)"
    [ "$status" = "running" ] || die "container $name not running (status=$status)"
}

require_infra() {
    require_tools
    require_container_running "$POSTGRES_CONTAINER"
    require_container_running "$REDIS_CONTAINER"
    require_container_running "$NEO4J_CONTAINER"
    require_container_running "$KNOWLEDGE_CONTAINER"
}

# ── container exec wrappers ────────────────────────────────────────

# psql_q DB SQL — run SQL against a given Postgres DB, return
# tab-separated rows on stdout (psql -tAc).
psql_q() {
    local db="$1"
    local sql="$2"
    docker exec -e "PGPASSWORD=$PG_PASSWORD" "$POSTGRES_CONTAINER" \
        psql -U "$PG_USER" -d "$db" -tAc "$sql"
}

# psql_exec DB SQL — run a DDL/DML statement, print its command tag
# on stdout (via -c). Errors propagate via set -e.
psql_exec() {
    local db="$1"
    local sql="$2"
    docker exec -e "PGPASSWORD=$PG_PASSWORD" "$POSTGRES_CONTAINER" \
        psql -U "$PG_USER" -d "$db" -c "$sql"
}

# redis_cmd … — run a redis-cli command inside the redis container.
redis_cmd() {
    docker exec "$REDIS_CONTAINER" redis-cli "$@"
}

# redis_pending_count STREAM GROUP — return the integer pending
# count for a consumer group, or 0 if the group / stream doesn't
# exist yet (NOGROUP error on a fresh stack). Guards the probe-
# polling loops in c05 / c08 against a false FAIL on stacks where
# the consumer hasn't yet joined its group.
redis_pending_count() {
    local stream="$1"
    local group="$2"
    local raw
    raw=$(redis_cmd XPENDING "$stream" "$group" 2>&1) || true
    if printf '%s' "$raw" | grep -qi 'NOGROUP'; then
        echo "0"
        return 0
    fi
    # First line of a non-summary XPENDING reply is the count.
    printf '%s' "$raw" | head -n 1 | tr -d '[:space:]'
}

# cypher_q CYPHER — run a Cypher query via the neo4j container's
# cypher-shell. Returns the raw output (including header lines). If
# a caller needs a bare count, pipe through tail/awk.
cypher_q() {
    local cypher="$1"
    docker exec -i "$NEO4J_CONTAINER" cypher-shell \
        -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
        --format plain <<< "$cypher"
}

# cypher_count_scalar CYPHER — convenience wrapper for the common
# "RETURN count(...)" query. Strips the header row and returns the
# bare integer.
cypher_count_scalar() {
    cypher_q "$1" | tail -n 1 | tr -d '[:space:]'
}

# ── polling helpers ────────────────────────────────────────────────

# wait_until SECS DESCRIPTION CMD — polls CMD (a function name or
# shell expression) once per second for up to SECS, exits 0 when CMD
# returns 0. Fails with a clear error if the deadline passes.
wait_until() {
    local deadline="$1"
    local desc="$2"
    shift 2
    local start
    start=$(date +%s)
    while :; do
        if "$@"; then
            return 0
        fi
        local now
        now=$(date +%s)
        if [ $((now - start)) -ge "$deadline" ]; then
            die "timed out after ${deadline}s waiting for: $desc"
        fi
        sleep 1
    done
}

# ── assertions ─────────────────────────────────────────────────────

# assert_eq NAME EXPECTED ACTUAL — pretty pass/fail with labelled
# value on failure. Returns 0 on match, dies with diag on mismatch.
assert_eq() {
    local name="$1"
    local expected="$2"
    local actual="$3"
    if [ "$expected" = "$actual" ]; then
        log_pass "$name = $actual"
        return 0
    fi
    die "$name: expected '$expected', got '$actual'"
}

# assert_ge NAME MIN ACTUAL — integer comparison.
assert_ge() {
    local name="$1"
    local min="$2"
    local actual="$3"
    if [ "$actual" -ge "$min" ] 2>/dev/null; then
        log_pass "$name = $actual (≥ $min)"
        return 0
    fi
    die "$name: expected ≥ $min, got '$actual'"
}

# assert_le NAME MAX ACTUAL — integer comparison.
assert_le() {
    local name="$1"
    local max="$2"
    local actual="$3"
    if [ "$actual" -le "$max" ] 2>/dev/null; then
        log_pass "$name = $actual (≤ $max)"
        return 0
    fi
    die "$name: expected ≤ $max, got '$actual'"
}
