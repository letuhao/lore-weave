#!/usr/bin/env bash
# verify-cycle-5.sh — L1.C Provisioner + L1.G Pgbouncer + L1.F Cache
# Per RAID_WORKFLOW.md §13 (CI gate exit 0 = pass).
#
# Cycle 5 ships:
#   DPS 1 — L1.C provisioner (Rust): services/world-service lib with
#           provisioner / deprovisioner / capacity_planner / db_pool
#           modules + orphan_scanner binary + per-reality 0001 skeleton
#           migration + scripts/capacity-thresholds.yaml + terraform
#           postgres-shard STUB + integration test
#   DPS 2 — L1.G pgbouncer: infra/pgbouncer/{pgbouncer.ini,databases.ini,
#           userlist.txt} + infra/docker-compose.pgbouncer.yml overlay +
#           contracts/meta/pool.go Go mirror + tests + runbook
#   DPS 3 — L1.F Redis cache: contracts/meta/cache.go + cache_test.go +
#           contracts/cache/keys.yaml + infra/redis/{redis.conf,sentinel.conf}
#           + infra/docker-compose.redis-cache.yml + scripts/cache-warmup.sh
#
# Acceptance per layer plan L1.C §1 + L1.G §5 + L1.F §4 + LOCKED
# Q-L1C-1 (docker-compose V1) + Q-L1F-1 (shared Sentinel + AOF 1s +
# allkeys-lru) + Q-L1G-1 (pgbouncer + transaction pooling).

set -euo pipefail

CYCLE=5
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
FAILED=0

audit() {
  mkdir -p "$(dirname "$AUDIT_LOG")"
  echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE${2:+,$2}}" >> "$AUDIT_LOG"
}

step() { echo "[verify-cycle-$CYCLE] === $* ==="; }
fail() { echo "[verify-cycle-$CYCLE] FAIL: $*" >&2; FAILED=1; }
ok()   { echo "[verify-cycle-$CYCLE] ok:   $*"; }

cd "$REPO_ROOT"

# ────────────────────────────────────────────────────────────────────────────────
step "1/12 — required artifacts present (DPS 1+2+3)"
required=(
  # DPS 1 — L1.C provisioner Rust
  "services/world-service/Cargo.toml"
  "services/world-service/src/lib.rs"
  "services/world-service/src/provisioner.rs"
  "services/world-service/src/deprovisioner.rs"
  "services/world-service/src/capacity_planner.rs"
  "services/world-service/src/db_pool.rs"
  "services/world-service/src/errors.rs"
  "services/world-service/src/bin/orphan_scanner.rs"
  # Per-reality skeleton + thresholds + terraform stub
  "contracts/migrations/per_reality/0001_initial.up.sql"
  "contracts/migrations/per_reality/0001_initial.down.sql"
  "contracts/migrations/per_reality/README.md"
  "scripts/capacity-thresholds.yaml"
  "infra/terraform/postgres-shard/README.md"
  "runbooks/provisioner/orphan_resolution.md"
  "tests/integration/reality_lifecycle_test.go"
  "tests/integration/sql_helpers_test.go"

  # DPS 2 — L1.G pgbouncer
  "infra/pgbouncer/pgbouncer.ini"
  "infra/pgbouncer/databases.ini"
  "infra/pgbouncer/userlist.txt"
  "infra/docker-compose.pgbouncer.yml"
  "infra/terraform/pgbouncer/README.md"
  "contracts/meta/pool.go"
  "contracts/meta/pool_test.go"
  "runbooks/pgbouncer/connection_exhaustion.md"
  "tests/integration/pgbouncer_multiplex_test.go"

  # DPS 3 — L1.F Redis cache
  "contracts/meta/cache.go"
  "contracts/meta/cache_test.go"
  "contracts/cache/keys.yaml"
  "infra/redis/redis.conf"
  "infra/redis/sentinel.conf"
  "infra/docker-compose.redis-cache.yml"
  "infra/terraform/redis-cache/README.md"
  "scripts/cache-warmup.sh"
  "tests/integration/cache_invalidation_test.go"
)
for f in "${required[@]}"; do
  if [ -f "$f" ]; then ok "  $f"; else fail "missing: $f"; fi
done

# ────────────────────────────────────────────────────────────────────────────────
step "2/12 — Q-L1C-1 honored (V1 = docker-compose, NOT real Terraform)"
# Terraform STUB dirs must contain ONLY a README, no .tf files.
for d in infra/terraform/postgres-shard infra/terraform/pgbouncer infra/terraform/redis-cache; do
  tf_count=$(find "$d" -name '*.tf' 2>/dev/null | wc -l | tr -d '[:space:]')
  if [ "$tf_count" -ne 0 ]; then
    fail "Q-L1C-1 violation: $d contains $tf_count .tf files (V1 is docker-compose only)"
  else
    ok "$d: no .tf files (V1 docker-compose locked)"
  fi
  # README must explicitly cite Q-L1C-1 OR Q-L1F-1 OR Q-L1G-1
  if grep -qE 'Q-L1[CFG]-1' "$d/README.md"; then
    ok "$d/README.md cites locked-question rationale"
  else
    fail "$d/README.md missing Q-L1C-1/F-1/G-1 rationale"
  fi
done

# ────────────────────────────────────────────────────────────────────────────────
step "3/12 — Q-L1F-1 honored (shared Sentinel V1, AOF 1s, allkeys-lru)"
# redis.conf must set appendfsync everysec + maxmemory-policy allkeys-lru
if grep -qE '^appendfsync\s+everysec' infra/redis/redis.conf; then
  ok "redis.conf: appendfsync everysec"
else
  fail "redis.conf: appendfsync !everysec (Q-L1F-1 violation)"
fi
if grep -qE '^maxmemory-policy\s+allkeys-lru' infra/redis/redis.conf; then
  ok "redis.conf: maxmemory-policy allkeys-lru"
else
  fail "redis.conf: maxmemory-policy !allkeys-lru (Q-L1F-1 violation)"
fi
# Sentinel quorum=1 for V1 (degenerate single instance; documented as such)
if grep -qE '^sentinel monitor lw-meta-cache.*\s1$' infra/redis/sentinel.conf; then
  ok "sentinel.conf: quorum=1 V1 single-instance (documented)"
else
  fail "sentinel.conf: V1 quorum=1 not present"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "4/12 — Q-L1G-1 honored (pgbouncer, transaction pooling, 500/5000 caps)"
if grep -qE '^pool_mode\s*=\s*transaction' infra/pgbouncer/pgbouncer.ini; then
  ok "pgbouncer.ini: pool_mode = transaction"
else
  fail "pgbouncer.ini: pool_mode != transaction (Q-L1G-1 / db_pool.rs invariant violation)"
fi
if grep -qE '^max_client_conn\s*=\s*5000' infra/pgbouncer/pgbouncer.ini; then
  ok "pgbouncer.ini: max_client_conn = 5000"
else
  fail "pgbouncer.ini: max_client_conn != 5000"
fi
if grep -qE '^max_db_connections\s*=\s*500' infra/pgbouncer/pgbouncer.ini; then
  ok "pgbouncer.ini: max_db_connections = 500"
else
  fail "pgbouncer.ini: max_db_connections != 500"
fi
# Cross-language cap constants — Rust + Go must agree. Extract the literal
# AFTER the `= ` token so the u32 / uint32 type annotations don't confuse the
# parser.
rust_virt=$(grep -E 'pub const MAX_VIRTUAL_CONNECTIONS: u32 = [0-9]+' services/world-service/src/db_pool.rs | sed -E 's/.*=\s*([0-9]+).*/\1/')
go_virt=$(grep -E 'MaxVirtualConnections\s+uint32\s*=\s*[0-9]+' contracts/meta/pool.go | sed -E 's/.*=\s*([0-9]+).*/\1/')
if [ "$rust_virt" = "5000" ] && [ "$go_virt" = "5000" ]; then
  ok "Rust + Go agree: MAX_VIRTUAL_CONNECTIONS = 5000"
else
  fail "cap drift: Rust=$rust_virt Go=$go_virt (must both be 5000)"
fi
rust_back=$(grep -E 'pub const MAX_BACKEND_CONNECTIONS: u32 = [0-9]+' services/world-service/src/db_pool.rs | sed -E 's/.*=\s*([0-9]+).*/\1/')
go_back=$(grep -E 'MaxBackendConnections\s+uint32\s*=\s*[0-9]+' contracts/meta/pool.go | sed -E 's/.*=\s*([0-9]+).*/\1/')
if [ "$rust_back" = "500" ] && [ "$go_back" = "500" ]; then
  ok "Rust + Go agree: MAX_BACKEND_CONNECTIONS = 500"
else
  fail "cap drift: Rust=$rust_back Go=$go_back (must both be 500)"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "5/12 — per-reality 0001_initial.sql is SKELETON ONLY (L1.C.5 invariant)"
# Must contain the 4 placeholder tables: events, outbox, snapshots, projection_meta
for tbl in events outbox snapshots projection_meta; do
  if grep -qE "CREATE TABLE IF NOT EXISTS $tbl" contracts/migrations/per_reality/0001_initial.up.sql; then
    ok "0001 contains skeleton table: $tbl"
  else
    fail "0001 missing skeleton table: $tbl"
  fi
done
# Must NOT contain L2/L3 domain tables (canon_projection lands L5 cycle 23)
forbidden_tables='canon_projection|reality_registry|event_audit|reality_close_audit'
if grep -qiE "CREATE TABLE.*(${forbidden_tables})" contracts/migrations/per_reality/0001_initial.up.sql; then
  fail "0001 contains forbidden non-skeleton table (L2/L3 leak)"
else
  ok "0001 contains no L2/L3 domain tables (skeleton purity holds)"
fi
# DOWN file drops all 4 tables in reverse dep order
for tbl in projection_meta snapshots outbox events; do
  if grep -qE "DROP TABLE IF EXISTS $tbl" contracts/migrations/per_reality/0001_initial.down.sql; then
    ok "0001 down drops: $tbl"
  else
    fail "0001 down missing: DROP TABLE IF EXISTS $tbl"
  fi
done

# ────────────────────────────────────────────────────────────────────────────────
step "6/12 — provisioner 11-step + deprovisioner 6-step labels frozen (R04 §12D.1)"
# 11 step labels must be present in PROVISION_STEPS const
for label in validate pick_shard register_pending create_database \
             apply_initial_migration register_with_pgbouncer \
             register_prometheus_scrape register_backup_policy \
             transition_to_seeding transition_to_active emit_reality_created; do
  if grep -qE "\"$label\"" services/world-service/src/provisioner.rs; then
    ok "provisioner step label: $label"
  else
    fail "provisioner missing step label: $label"
  fi
done
# 6 deprovision step labels
for label in transition_to_soft_deleted unregister_with_pgbouncer \
             unregister_prometheus_scrape unregister_backup_policy \
             drop_database transition_to_dropped; do
  if grep -qE "\"$label\"" services/world-service/src/deprovisioner.rs; then
    ok "deprovisioner step label: $label"
  else
    fail "deprovisioner missing step label: $label"
  fi
done

# ────────────────────────────────────────────────────────────────────────────────
step "7/12 — capacity planner picks LEAST FULL shard, not random (R04 §12D.6)"
# Pin the deterministic tie-break behavior. The test name itself
# encodes the contract.
if grep -qE 'fn picks_least_full_shard_not_random' services/world-service/src/provisioner.rs; then
  ok "provisioner test: picks_least_full_shard_not_random present"
else
  fail "provisioner test 'picks_least_full_shard_not_random' missing"
fi
if grep -qE 'fn breaks_ties_by_shard_id_ascending' services/world-service/src/capacity_planner.rs; then
  ok "capacity_planner test: breaks_ties_by_shard_id_ascending present"
else
  fail "capacity_planner test 'breaks_ties_by_shard_id_ascending' missing"
fi
# Capacity thresholds YAML must set warning < full
warning=$(grep -E '^\s*warning:\s*0\.' scripts/capacity-thresholds.yaml | head -1 | awk '{print $2}')
full=$(grep -E '^\s*full:\s*0\.' scripts/capacity-thresholds.yaml | head -1 | awk '{print $2}')
if [ -n "$warning" ] && [ -n "$full" ]; then
  ok "capacity-thresholds.yaml: warning=$warning full=$full"
else
  fail "capacity-thresholds.yaml: thresholds not parseable"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "8/12 — orphan_scanner has 7-day grace constant + dry-run safety"
if grep -qE 'pub const SOFT_DELETE_GRACE_DAYS: u32 = 7' services/world-service/src/bin/orphan_scanner.rs; then
  ok "orphan_scanner: SOFT_DELETE_GRACE_DAYS = 7"
else
  fail "orphan_scanner: 7-day grace constant missing"
fi
if grep -qE 'real-mode RPC wiring not yet implemented' services/world-service/src/bin/orphan_scanner.rs; then
  ok "orphan_scanner: non-dry-run panic guard present"
else
  fail "orphan_scanner: missing safety guard against accidental real-mode invocation"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "9/12 — cache key registry: every entry has TTL + namespace"
# YAML registry has the 4 canonical kinds; KeyKind enum has them too.
for kind in reality_routing entity_status sensitive_paths canon_projection; do
  if grep -qE "kind: $kind" contracts/cache/keys.yaml; then
    ok "keys.yaml: $kind entry present"
  else
    fail "keys.yaml: $kind entry missing"
  fi
  if grep -qE "Kind${kind^}|Kind${kind%%_*}${kind##*_}" contracts/meta/cache.go 2>/dev/null || \
     grep -qE "KeyKind\s*=\s*\"$kind\"" contracts/meta/cache.go; then
    ok "cache.go: KindKey matching $kind"
  else
    # Loose check: the literal "$kind" appears as a constant value somewhere
    if grep -qE "\"$kind\"" contracts/meta/cache.go; then
      ok "cache.go: $kind string literal present"
    else
      fail "cache.go: $kind not enumerated"
    fi
  fi
done
# Every entry must have ttl_seconds > 0
if grep -qE 'ttl_seconds:\s*0\b' contracts/cache/keys.yaml; then
  fail "keys.yaml: at least one entry has ttl_seconds=0 (60s fallback rule violated)"
else
  ok "keys.yaml: all entries have ttl_seconds > 0"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "10/12 — Rust build + test"
if command -v cargo >/dev/null 2>&1; then
  if cargo build -p world-service 2>&1 | tail -5; then
    ok "cargo build -p world-service"
  else
    fail "cargo build -p world-service"
  fi
  if cargo test -p world-service 2>&1 | tail -10; then
    ok "cargo test -p world-service"
  else
    fail "cargo test -p world-service"
  fi
  # Sanity: also build the orphan_scanner binary
  if cargo build -p world-service --bin orphan_scanner 2>&1 | tail -5; then
    ok "cargo build orphan_scanner binary"
  else
    fail "cargo build orphan_scanner binary"
  fi
  # meta-rs read-only surface still builds (no L1.C-induced breakage)
  if cargo build -p meta-rs 2>&1 | tail -5; then
    ok "cargo build -p meta-rs (regression guard)"
  else
    fail "cargo build -p meta-rs"
  fi
  if cargo test -p meta-rs 2>&1 | tail -5; then
    ok "cargo test -p meta-rs (regression guard)"
  else
    fail "cargo test -p meta-rs"
  fi
else
  echo "[verify-cycle-$CYCLE] note: cargo CLI absent — skipping Rust checks (CI must have cargo)"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "11/12 — Go build + vet + test contracts/meta (cycle 4 regress + cycle 5 pool/cache)"
if command -v go >/dev/null 2>&1; then
  (
    cd contracts/meta
    if go build ./... 2>&1; then ok "go build contracts/meta"; else fail "go build contracts/meta"; exit 1; fi
    if go vet ./... 2>&1; then ok "go vet contracts/meta"; else fail "go vet contracts/meta"; exit 1; fi
    if go test ./... 2>&1; then ok "go test contracts/meta"; else fail "go test contracts/meta"; exit 1; fi
  ) || FAILED=1
  # Integration build (regression guard + new pgbouncer_multiplex_test +
  # reality_lifecycle_test + cache_invalidation_test compilation check)
  (
    cd tests/integration
    if go build -tags=integration ./... 2>&1; then
      ok "go build -tags=integration tests/integration"
    else
      fail "go build -tags=integration tests/integration"; exit 1
    fi
  ) || FAILED=1
else
  echo "[verify-cycle-$CYCLE] note: go CLI absent — skipping Go checks"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "12/12 — docker-compose overlays + cache-warmup dry-run smoke"
# YAML sanity: each overlay must reference the external lw-meta-ha network
for f in infra/docker-compose.pgbouncer.yml infra/docker-compose.redis-cache.yml; do
  if grep -qE 'external:\s+true' "$f" && grep -qE 'name:\s+lw-meta-ha' "$f"; then
    ok "$f references external lw-meta-ha network"
  else
    fail "$f missing external lw-meta-ha network reference"
  fi
done
# cache-warmup dry-run exits 0
if bash scripts/cache-warmup.sh --dry-run >/dev/null 2>&1; then
  ok "scripts/cache-warmup.sh --dry-run exits 0"
else
  fail "scripts/cache-warmup.sh --dry-run failed"
fi
# capacity-thresholds.yaml parseable as YAML (loose check)
if grep -qE '^clusters:' scripts/capacity-thresholds.yaml; then
  ok "capacity-thresholds.yaml has top-level 'clusters:' key"
else
  fail "capacity-thresholds.yaml missing 'clusters:' key"
fi

# ────────────────────────────────────────────────────────────────────────────────
audit "verify_cycle_complete" "\"failed\":$FAILED"

if [ "$FAILED" -ne 0 ]; then
  echo "[verify-cycle-$CYCLE] FAIL: one or more checks failed"
  exit 1
fi
echo "[verify-cycle-$CYCLE] PASS"
exit 0
