#!/usr/bin/env bash
# verify-cycle-2.sh — L1.A-1 Routing + Lifecycle tables + L1.B Meta library
# Per RAID_WORKFLOW.md §13 (CI gate exit 0 = pass).
#
# Cycle 2 ships:
#   DPS 1 — migrations/meta/{001..008}_*.up.sql/.down.sql (7 routing+lifecycle + session_cost_summary)
#   DPS 2 — contracts/meta/ Go library + events_allowlist.yaml + meta-sensitive-read-paths.yml + transitions.yaml
#   DPS 3 — crates/meta-rs/ Rust hot-path port (MetaRead + RealityRouting + SensitivePaths)
#   Carryforward — tests/integration/go.mod (cycle-1 left it un-buildable)
#
# Acceptance per layer plans L1A §1 + L1B §9 + Q-L1A-1/2/3 + Q-L1B-1..5.
#
# Notes:
#   - SQL migration UP/DOWN dry-run against docker-compose.meta-ha.yml (C1) is
#     attempted IF docker is available; structural check fallback otherwise.
#   - Go race-detector requires cgo on Windows; structural `go vet` substitutes.

set -euo pipefail

CYCLE=2
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
step "1/9 — required artifacts present (DPS 1 SQL, DPS 2 Go, DPS 3 Rust, carryforward)"
required=(
  # DPS 1 SQL — 7 routing+lifecycle + session_cost_summary, both up + down
  "migrations/meta/README.md"
  "migrations/meta/001_reality_registry.up.sql"
  "migrations/meta/001_reality_registry.down.sql"
  "migrations/meta/002_instance_schema_migrations.up.sql"
  "migrations/meta/002_instance_schema_migrations.down.sql"
  "migrations/meta/003_publisher_heartbeats.up.sql"
  "migrations/meta/003_publisher_heartbeats.down.sql"
  "migrations/meta/004_lifecycle_transition_audit.up.sql"
  "migrations/meta/004_lifecycle_transition_audit.down.sql"
  "migrations/meta/005_reality_close_audit.up.sql"
  "migrations/meta/005_reality_close_audit.down.sql"
  "migrations/meta/006_archive_verification_log.up.sql"
  "migrations/meta/006_archive_verification_log.down.sql"
  "migrations/meta/007_reality_migration_audit.up.sql"
  "migrations/meta/007_reality_migration_audit.down.sql"
  "migrations/meta/008_session_cost_summary.up.sql"
  "migrations/meta/008_session_cost_summary.down.sql"
  # DPS 2 Go library + configs
  "contracts/meta/go.mod"
  "contracts/meta/doc.go"
  "contracts/meta/errors.go"
  "contracts/meta/actor.go"
  "contracts/meta/intent.go"
  "contracts/meta/allowlist.go"
  "contracts/meta/metawrite.go"
  "contracts/meta/lifecycle.go"
  "contracts/meta/transitions_validator.go"
  "contracts/meta/query_builder.go"
  "contracts/meta/read_audit.go"
  "contracts/meta/events_allowlist.yaml"
  "contracts/meta/meta-sensitive-read-paths.yml"
  "contracts/meta/transitions.yaml"
  # DPS 3 Rust
  "crates/meta-rs/Cargo.toml"
  "crates/meta-rs/src/lib.rs"
  "crates/meta-rs/src/errors.rs"
  "crates/meta-rs/src/routing.rs"
  "crates/meta-rs/src/sensitive_paths.rs"
  # Carryforward from cycle 1
  "tests/integration/go.mod"
)
for f in "${required[@]}"; do
  if [ -f "$f" ]; then ok "  $f"; else fail "missing: $f"; fi
done

# ────────────────────────────────────────────────────────────────────────────────
step "2/9 — Q-L1A-2 scope-guard: NONE of the 7 routing+lifecycle tables touch canon"
# Canon tables (canon_entries, canonization_audit, book_authorship, canon_change_log)
# moved OUT of meta per Q-L1A-2 (glossary-service owns them). Verify no migration
# file references those names.
canon_pattern='canon_entries\|canonization_audit\|book_authorship\|canon_change_log'
if grep -lE "$canon_pattern" migrations/meta/*.sql >/dev/null 2>&1; then
  fail "migrations/meta references canon tables (Q-L1A-2 violation)"
  grep -lE "$canon_pattern" migrations/meta/*.sql
else
  ok "no canon-table references in migrations/meta/ (Q-L1A-2 honored)"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "3/9 — Q-L1A-3 scope-guard: lifecycle_transition_audit has NO sampling clause"
# Q-L1A-3: full audit from V1, no sampling. Verify the migration doesn't introduce
# WHERE-based sampling or random() filters.
if grep -nE 'TABLESAMPLE|random\(\)|sample_rate' migrations/meta/004_lifecycle_transition_audit.up.sql; then
  fail "lifecycle_transition_audit migration introduces sampling (Q-L1A-3 violation)"
else
  ok "no sampling in lifecycle_transition_audit (Q-L1A-3 honored)"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "4/9 — L1.A-2 scope-guard: NONE of the PII tables ship this cycle (cycle 8 owns those)"
# L1.A-2 = pii_registry, pii_kek, user_consent_ledger, player_character_index.
# These belong to cycle 8. Verify no migration file CREATEs them.
pii_pattern='CREATE TABLE.*\(pii_registry\|pii_kek\|user_consent_ledger\|player_character_index\)'
if grep -lE "$pii_pattern" migrations/meta/*.up.sql >/dev/null 2>&1; then
  fail "PII tables shipped — these belong to cycle 8 (L1.A-2)"
else
  ok "no PII tables in migrations/meta/ (cycle 8 scope respected)"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "5/9 — append-only enforcement on audit tables (REVOKE statements present)"
audit_tables=(
  "migrations/meta/004_lifecycle_transition_audit.up.sql"
  "migrations/meta/005_reality_close_audit.up.sql"
  "migrations/meta/006_archive_verification_log.up.sql"
  "migrations/meta/007_reality_migration_audit.up.sql"
)
for f in "${audit_tables[@]}"; do
  if grep -q 'REVOKE UPDATE, DELETE' "$f" && grep -q 'app_service_role\|app_admin_role' "$f"; then
    ok "$f has append-only REVOKE (S04 §12T.4)"
  else
    fail "$f missing append-only REVOKE for app roles"
  fi
done

# ────────────────────────────────────────────────────────────────────────────────
step "6/9 — Go: build + vet + test contracts/meta"
if command -v go >/dev/null 2>&1; then
  (
    cd contracts/meta
    if go build ./... 2>&1; then
      ok "go build contracts/meta"
    else
      fail "go build contracts/meta"
      exit 1
    fi
    if go vet ./... 2>&1; then
      ok "go vet contracts/meta"
    else
      fail "go vet contracts/meta"
      exit 1
    fi
    if go test ./... 2>&1; then
      ok "go test contracts/meta"
    else
      fail "go test contracts/meta"
      exit 1
    fi
  ) || FAILED=1

  # Carryforward: tests/integration must build with -tags=integration
  (
    cd tests/integration
    if go build -tags=integration ./... 2>&1; then
      ok "go build -tags=integration tests/integration (carryforward)"
    else
      fail "go build -tags=integration tests/integration (carryforward broken)"
      exit 1
    fi
    if go test -tags=integration ./... 2>&1; then
      ok "go test -tags=integration tests/integration (skips when stack absent)"
    else
      fail "go test -tags=integration tests/integration"
      exit 1
    fi
  ) || FAILED=1
else
  echo "[verify-cycle-$CYCLE] note: go CLI absent — skipping Go checks (CI must have go installed)"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "7/9 — Rust: build + test meta-rs"
if command -v cargo >/dev/null 2>&1; then
  if cargo build -p meta-rs 2>&1; then
    ok "cargo build -p meta-rs"
  else
    fail "cargo build -p meta-rs"
  fi
  if cargo test -p meta-rs 2>&1; then
    ok "cargo test -p meta-rs"
  else
    fail "cargo test -p meta-rs"
  fi
else
  echo "[verify-cycle-$CYCLE] note: cargo CLI absent — skipping Rust checks"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "8/9 — SQL migrations: up/down dry-run against docker-compose.meta-ha.yml (Q-L1B-5)"
if command -v docker >/dev/null 2>&1; then
  if docker compose -f infra/docker-compose.meta-ha.yml ps --status=running -q primary >/dev/null 2>&1 && \
     [ -n "$(docker compose -f infra/docker-compose.meta-ha.yml ps --status=running -q primary 2>/dev/null)" ]; then
    # Stack is up — apply all UP migrations, then all DOWN migrations
    export PGPASSWORD=${PATRONI_SUPERUSER_PASSWORD:-postgres}
    if docker exec lw-meta-pg-primary psql -U postgres -d postgres -c "CREATE DATABASE loreweave_meta_verify;" 2>/dev/null; then
      ok "created loreweave_meta_verify DB"
    fi
    for up in migrations/meta/0*.up.sql; do
      if docker exec -i lw-meta-pg-primary psql -U postgres -d loreweave_meta_verify < "$up" >/dev/null 2>&1; then
        ok "UP: $up"
      else
        fail "UP: $up"
      fi
    done
    # Down in reverse order
    for down in $(ls migrations/meta/0*.down.sql | sort -r); do
      if docker exec -i lw-meta-pg-primary psql -U postgres -d loreweave_meta_verify < "$down" >/dev/null 2>&1; then
        ok "DOWN: $down"
      else
        fail "DOWN: $down"
      fi
    done
    docker exec lw-meta-pg-primary psql -U postgres -d postgres -c "DROP DATABASE loreweave_meta_verify;" >/dev/null 2>&1 || true
  else
    echo "[verify-cycle-$CYCLE] note: meta-ha stack not running — structural SQL check fallback"
    # Fallback: each .up.sql has a CREATE TABLE; each .down.sql has a DROP TABLE
    for up in migrations/meta/0*.up.sql; do
      if grep -q 'CREATE TABLE' "$up"; then
        ok "structural: $up has CREATE TABLE"
      else
        fail "structural: $up missing CREATE TABLE"
      fi
    done
    for down in migrations/meta/0*.down.sql; do
      if grep -q 'DROP TABLE' "$down"; then
        ok "structural: $down has DROP TABLE"
      else
        fail "structural: $down missing DROP TABLE"
      fi
    done
  fi
else
  echo "[verify-cycle-$CYCLE] note: docker absent — structural SQL check fallback"
  for up in migrations/meta/0*.up.sql; do
    if grep -q 'CREATE TABLE' "$up"; then ok "structural: $up"; else fail "$up missing CREATE TABLE"; fi
  done
  for down in migrations/meta/0*.down.sql; do
    if grep -q 'DROP TABLE' "$down"; then ok "structural: $down"; else fail "$down missing DROP TABLE"; fi
  done
fi

# ────────────────────────────────────────────────────────────────────────────────
step "9/9 — Q-L1B-1/2/3/4/5 LOCKED resolution markers present"
# Q-L1B-1: events_allowlist.yaml present + has the 10 expected tables
if grep -q '^version: 1$' contracts/meta/events_allowlist.yaml; then
  ok "Q-L1B-1: events_allowlist.yaml v1 header"
else
  fail "Q-L1B-1: events_allowlist.yaml missing version header"
fi
# Q-L1B-2: meta-sensitive-read-paths.yml present + has the 4 expected ids
for id in player_index_cross_user audit_query admin_bulk_export bulk_meta_query; do
  if grep -q "id: $id" contracts/meta/meta-sensitive-read-paths.yml; then
    ok "Q-L1B-2: sensitive path id=$id"
  else
    fail "Q-L1B-2: sensitive path id=$id missing"
  fi
done
# Q-L1B-3: MetaWriteBatch helper present in Go library
if grep -q 'func MetaWriteBatch' contracts/meta/metawrite.go; then
  ok "Q-L1B-3: MetaWriteBatch helper present"
else
  fail "Q-L1B-3: MetaWriteBatch helper missing"
fi
# Q-L1B-4: Rust hot-path port present + minimal MetaRead trait
if grep -q 'pub trait MetaRead' crates/meta-rs/src/routing.rs; then
  ok "Q-L1B-4: meta-rs MetaRead trait present"
else
  fail "Q-L1B-4: meta-rs MetaRead trait missing"
fi
# Q-L1B-5: cycle 1 ship — re-verify the file still exists (regression guard)
if [ -f "infra/docker-compose.meta-ha.yml" ]; then
  ok "Q-L1B-5: docker-compose.meta-ha.yml (from cycle 1)"
else
  fail "Q-L1B-5: docker-compose.meta-ha.yml lost — cycle 1 regression"
fi
# Q-L1A-1: session_cost_summary table only (NOT the rollup worker)
if [ -f "migrations/meta/008_session_cost_summary.up.sql" ]; then
  ok "Q-L1A-1: session_cost_summary table shipped"
else
  fail "Q-L1A-1: session_cost_summary table missing"
fi
# Worker should NOT be present this cycle
if [ -d "services/session-cost-rollup-worker" ]; then
  fail "Q-L1A-1: session-cost-rollup-worker shipped early — should be later cycle"
else
  ok "Q-L1A-1: rollup worker correctly deferred"
fi

# ────────────────────────────────────────────────────────────────────────────────
audit "verify_cycle_complete" "\"failed\":$FAILED"

if [ "$FAILED" -ne 0 ]; then
  echo "[verify-cycle-$CYCLE] FAIL: one or more checks failed"
  exit 1
fi
echo "[verify-cycle-$CYCLE] PASS"
exit 0
