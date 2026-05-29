#!/usr/bin/env bash
# verify-cycle-3.sh — L1.A-2 PII + Identity + Consent tables
# Per RAID_WORKFLOW.md §13 (CI gate exit 0 = pass).
#
# Cycle 3 ships:
#   DPS 1 — migrations/meta/{009,010}_*.up.sql/.down.sql (pii_registry + pii_kek)
#           + contracts/meta/kms.go + contracts/meta/kms_test.go
#           (KMSClient interface + OpenPII crypto-shred path + DeterministicTestKMS)
#   DPS 2 — migrations/meta/{011,012}_*.up.sql/.down.sql (user_consent_ledger + player_character_index)
#           + contracts/meta/events_allowlist.yaml extension (4 new tables)
#           + contracts/meta/pii_l1a2_test.go (pkColumnFor + allowlist regression)
#   Shared — pkColumnFor extension for all 4 tables (lifecycle.go)
#
# Acceptance per layer plans L1A §2 + Q-L1A-1/2/3 + Q-L5H-1 (consent shape).
#
# Notes:
#   - SQL migration UP/DOWN dry-run against docker-compose.meta-ha.yml (C1) is
#     attempted IF docker is available; structural check fallback otherwise.
#   - meta_write_audit table doesn't exist yet (cycle 10); production MetaWrite()
#     would fail on audit insert. Test fakes bypass — same pattern as cycle 2.

set -euo pipefail

CYCLE=3
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
step "1/9 — required artifacts present (DPS 1 + DPS 2 + shared extensions)"
required=(
  # DPS 1 — PII crypto-shred
  "migrations/meta/009_pii_registry.up.sql"
  "migrations/meta/009_pii_registry.down.sql"
  "migrations/meta/010_pii_kek.up.sql"
  "migrations/meta/010_pii_kek.down.sql"
  "contracts/meta/kms.go"
  "contracts/meta/kms_test.go"

  # DPS 2 — Consent + PC index
  "migrations/meta/011_user_consent_ledger.up.sql"
  "migrations/meta/011_user_consent_ledger.down.sql"
  "migrations/meta/012_player_character_index.up.sql"
  "migrations/meta/012_player_character_index.down.sql"
  "contracts/meta/pii_l1a2_test.go"

  # Shared (cycle 2 carryforward)
  "contracts/meta/events_allowlist.yaml"
  "contracts/meta/meta-sensitive-read-paths.yml"
  "contracts/meta/lifecycle.go"
)
for f in "${required[@]}"; do
  if [ -f "$f" ]; then ok "  $f"; else fail "missing: $f"; fi
done

# ────────────────────────────────────────────────────────────────────────────────
step "2/9 — Q-L1A-2 scope-guard: NONE of the cycle-3 migrations touch canon"
canon_pattern='canon_entries\|canonization_audit\|book_authorship\|canon_change_log'
if grep -lE "$canon_pattern" migrations/meta/00[9]_*.sql migrations/meta/01[012]_*.sql 2>/dev/null | grep -v '^$'; then
  fail "cycle-3 migrations reference canon tables (Q-L1A-2 violation)"
else
  ok "no canon-table references in cycle-3 migrations (Q-L1A-2 honored)"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "3/9 — Cycle-10 scope-guard: NO meta_*_audit tables shipped this cycle"
audit_pattern='CREATE TABLE.*meta_write_audit\|CREATE TABLE.*meta_read_audit\|CREATE TABLE.*admin_action_audit\|CREATE TABLE.*service_to_service_audit\|CREATE TABLE.*prompt_audit'
for f in migrations/meta/009_*.up.sql migrations/meta/010_*.up.sql migrations/meta/011_*.up.sql migrations/meta/012_*.up.sql; do
  if grep -qE "$audit_pattern" "$f" 2>/dev/null; then
    fail "$f creates a meta_*_audit table (cycle 10 scope violation)"
  fi
done
ok "no meta_*_audit tables in cycle-3 migrations (cycle 10 scope respected)"

# ────────────────────────────────────────────────────────────────────────────────
step "4/9 — Cycle-2 scope-guard: routing+lifecycle tables NOT modified by cycle 3"
# Migrations 001..008 are cycle 2's. We only added 009..012; modifying 001..008
# would be a backward-incompatible change.
for f in migrations/meta/001_*.up.sql migrations/meta/002_*.up.sql \
         migrations/meta/003_*.up.sql migrations/meta/004_*.up.sql \
         migrations/meta/005_*.up.sql migrations/meta/006_*.up.sql \
         migrations/meta/007_*.up.sql migrations/meta/008_*.up.sql; do
  # git diff against cycle-2 head (63ef3965) — if any 001..008 file changed, fail
  if git diff --quiet 63ef3965 -- "$f" 2>/dev/null; then
    : # unchanged — good
  else
    if git rev-parse 63ef3965 >/dev/null 2>&1; then
      fail "$f modified — cycle 3 must not touch cycle-2 migrations"
    fi
  fi
done
ok "cycle-2 routing+lifecycle migrations untouched"

# ────────────────────────────────────────────────────────────────────────────────
step "5/9 — Crypto-shred: NO real KEK bytes in any cycle-3 file"
# Defense against accidentally committing real key material. All test ciphertext
# must be obvious placeholder strings.
banned_pattern='AKIA[0-9A-Z]\{16,\}\|AIza[0-9A-Za-z_-]\{35,\}\|-----BEGIN [A-Z ]*PRIVATE KEY-----'
for f in migrations/meta/009_*.up.sql migrations/meta/010_*.up.sql \
         contracts/meta/kms.go contracts/meta/kms_test.go \
         contracts/meta/pii_l1a2_test.go; do
  if grep -qE "$banned_pattern" "$f" 2>/dev/null; then
    fail "$f contains what looks like real key material"
  fi
done
# Also assert kms_test.go uses the "test-ciphertext-not-real" prefix convention
if ! grep -q 'test-ciphertext-not-real' contracts/meta/kms_test.go; then
  fail "kms_test.go should use 'test-ciphertext-not-real' placeholder pattern"
fi
# DeterministicTestKMS may be DECLARED in kms.go (so the type is exported
# for cross-package test fixtures) but must NEVER be CONSTRUCTED (`&DeterministicTestKMS{`)
# outside *_test.go. Foundation L1.K lint cycle will harden this; proof-of-concept here.
illegal_uses=$(grep -lE '&?DeterministicTestKMS\{' contracts/meta/*.go 2>/dev/null | grep -v '_test\.go' || true)
if [ -n "$illegal_uses" ]; then
  fail "DeterministicTestKMS instantiated outside *_test.go (production-isolation violation): $illegal_uses"
else
  ok "DeterministicTestKMS test-only instantiation verified"
fi
ok "no real key material in cycle-3 files"

# ────────────────────────────────────────────────────────────────────────────────
step "6/9 — append-only-ish enforcement on PII + consent tables"
# pii_kek: app roles may UPDATE (mark destroyed) but never DELETE (audit trail)
if grep -q 'REVOKE DELETE ON TABLE pii_kek' migrations/meta/010_pii_kek.up.sql; then
  ok "pii_kek REVOKE DELETE present"
else
  fail "pii_kek missing REVOKE DELETE (audit-trail violation)"
fi
# user_consent_ledger: same
if grep -q 'REVOKE DELETE ON TABLE user_consent_ledger' migrations/meta/011_user_consent_ledger.up.sql; then
  ok "user_consent_ledger REVOKE DELETE present"
else
  fail "user_consent_ledger missing REVOKE DELETE (audit-trail violation)"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "7/9 — Go: build + vet + test contracts/meta (with new crypto-shred + pkColumnFor tests)"
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
      ok "go test contracts/meta (incl. TestOpenPII_CryptoShred_KEKDestroyed + TestPkColumnFor_L1A2Tables)"
    else
      fail "go test contracts/meta"
      exit 1
    fi
  ) || FAILED=1

  # Carryforward: tests/integration must still build
  (
    cd tests/integration
    if go build -tags=integration ./... 2>&1; then
      ok "go build -tags=integration tests/integration (regression guard)"
    else
      fail "go build -tags=integration tests/integration"
      exit 1
    fi
  ) || FAILED=1
else
  echo "[verify-cycle-$CYCLE] note: go CLI absent — skipping Go checks (CI must have go installed)"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "8/9 — SQL migrations: structural check (CREATE TABLE / DROP TABLE per file)"
# Live UP/DOWN dry-run via docker-compose.meta-ha.yml is attempted only when
# the stack is up; otherwise fall back to structural check.
docker_used=0
if command -v docker >/dev/null 2>&1; then
  if [ -n "$(docker compose -f infra/docker-compose.meta-ha.yml ps --status=running -q primary 2>/dev/null || true)" ]; then
    docker_used=1
    export PGPASSWORD=${PATRONI_SUPERUSER_PASSWORD:-postgres}
    docker exec lw-meta-pg-primary psql -U postgres -d postgres \
      -c "CREATE DATABASE loreweave_meta_verify_c3;" 2>/dev/null && \
      ok "created loreweave_meta_verify_c3 DB"
    # Apply ALL cycle-2 + cycle-3 migrations in order (FK depends on cycle-2 not really; pii_kek FK is intra-cycle-3)
    for up in migrations/meta/0*.up.sql; do
      if docker exec -i lw-meta-pg-primary psql -U postgres -d loreweave_meta_verify_c3 < "$up" >/dev/null 2>&1; then
        ok "UP: $up"
      else
        fail "UP: $up"
      fi
    done
    for down in $(ls migrations/meta/0*.down.sql | sort -r); do
      if docker exec -i lw-meta-pg-primary psql -U postgres -d loreweave_meta_verify_c3 < "$down" >/dev/null 2>&1; then
        ok "DOWN: $down"
      else
        fail "DOWN: $down"
      fi
    done
    docker exec lw-meta-pg-primary psql -U postgres -d postgres \
      -c "DROP DATABASE loreweave_meta_verify_c3;" >/dev/null 2>&1 || true
  fi
fi
if [ "$docker_used" -eq 0 ]; then
  echo "[verify-cycle-$CYCLE] note: docker / meta-ha stack absent — structural SQL check fallback"
  for up in migrations/meta/009_*.up.sql migrations/meta/010_*.up.sql \
            migrations/meta/011_*.up.sql migrations/meta/012_*.up.sql; do
    if grep -q 'CREATE TABLE' "$up"; then ok "structural: $up"; else fail "$up missing CREATE TABLE"; fi
  done
  for down in migrations/meta/009_*.down.sql migrations/meta/010_*.down.sql \
              migrations/meta/011_*.down.sql migrations/meta/012_*.down.sql; do
    if grep -q 'DROP TABLE' "$down"; then ok "structural: $down"; else fail "$down missing DROP TABLE"; fi
  done
fi

# ────────────────────────────────────────────────────────────────────────────────
step "9/9 — LOCKED resolution markers present (Q-L1A-2 + Q-L5H-1 + 4 PII tables in allowlist)"
# Q-L1A-2 honored — no canon tables in events_allowlist (regression guard for whole cycle history)
if grep -qE 'canon_entries|canonization_audit|book_authorship|canon_change_log' contracts/meta/events_allowlist.yaml; then
  fail "events_allowlist.yaml references canon tables (Q-L1A-2 violation)"
else
  ok "Q-L1A-2: no canon tables in events_allowlist.yaml"
fi
# Q-L5H-1 — consent ledger has revoke_reason column + revoke_order CHECK (default-to-consent shape)
if grep -q 'revoke_reason' migrations/meta/011_user_consent_ledger.up.sql && \
   grep -q 'user_consent_ledger_revoke_order' migrations/meta/011_user_consent_ledger.up.sql; then
  ok "Q-L5H-1: user_consent_ledger has revoke_reason + revoke_order CHECK"
else
  fail "Q-L5H-1: user_consent_ledger missing revoke_reason or revoke_order CHECK"
fi
# All 4 L1.A-2 tables in allowlist
for tbl in pii_registry pii_kek user_consent_ledger player_character_index; do
  if grep -qE "table: $tbl(\s|\$)" contracts/meta/events_allowlist.yaml; then
    ok "allowlist: $tbl present"
  else
    fail "allowlist: $tbl missing"
  fi
done
# player_character_index sensitive-path id (cycle 2's stable list, now backed by real table)
if grep -q 'id: player_index_cross_user' contracts/meta/meta-sensitive-read-paths.yml && \
   grep -q '\- player_character_index' contracts/meta/meta-sensitive-read-paths.yml; then
  ok "sensitive-paths: player_index_cross_user still references player_character_index"
else
  fail "sensitive-paths: player_index_cross_user binding lost"
fi
# pkColumnFor extended (string match — actual logic verified by go test)
for entry in '"pii_registry"' '"pii_kek"' '"user_consent_ledger"' '"player_character_index"'; do
  if grep -q "case $entry:" contracts/meta/lifecycle.go; then
    ok "pkColumnFor handles $entry"
  else
    fail "pkColumnFor missing case $entry"
  fi
done

# ────────────────────────────────────────────────────────────────────────────────
audit "verify_cycle_complete" "\"failed\":$FAILED"

if [ "$FAILED" -ne 0 ]; then
  echo "[verify-cycle-$CYCLE] FAIL: one or more checks failed"
  exit 1
fi
echo "[verify-cycle-$CYCLE] PASS"
exit 0
