#!/usr/bin/env bash
# verify-cycle-4.sh — L1.A-3 Audit Infrastructure (5 tables)
# Per RAID_WORKFLOW.md §13 (CI gate exit 0 = pass).
#
# Cycle 4 ships:
#   DPS 1 — migrations/meta/{013,014}_*.up.sql/.down.sql
#           (meta_write_audit + meta_read_audit) + doc.go correction
#   DPS 2 — migrations/meta/{015,016}_*.up.sql/.down.sql
#           (admin_action_audit + service_to_service_audit) + scrubber.go stub
#   DPS 3 — migrations/meta/017_*.up.sql/.down.sql
#           (prompt_audit) + prompt_audit.go body-never-stored interface
#   Shared — pkColumnFor extension for all 5 audit tables
#           + events_allowlist.yaml extension (5 new tables, NO outbox events)
#           + audit_l1a3_test.go regression coverage
#           + MetaWrite() audit-wiring tests (every-path + audit-failure rollback)
#
# Acceptance per layer plan L1A §3 + Q-L1A-3 (full audit, no sampling) +
# S04 §12T.4 (append-only REVOKE) + S08 §12X.5 (scrubber) + S09 §12Y (no body).

set -euo pipefail

CYCLE=4
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
step "1/10 — required artifacts present (3 DPS + shared extensions)"
required=(
  # DPS 1 — meta_write_audit + meta_read_audit
  "migrations/meta/013_meta_write_audit.up.sql"
  "migrations/meta/013_meta_write_audit.down.sql"
  "migrations/meta/014_meta_read_audit.up.sql"
  "migrations/meta/014_meta_read_audit.down.sql"

  # DPS 2 — admin_action_audit + service_to_service_audit + scrubber
  "migrations/meta/015_admin_action_audit.up.sql"
  "migrations/meta/015_admin_action_audit.down.sql"
  "migrations/meta/016_service_to_service_audit.up.sql"
  "migrations/meta/016_service_to_service_audit.down.sql"
  "contracts/meta/scrubber.go"

  # DPS 3 — prompt_audit + body-never-stored interface
  "migrations/meta/017_prompt_audit.up.sql"
  "migrations/meta/017_prompt_audit.down.sql"
  "contracts/meta/prompt_audit.go"

  # Shared
  "contracts/meta/events_allowlist.yaml"
  "contracts/meta/lifecycle.go"
  "contracts/meta/doc.go"
  "contracts/meta/audit_l1a3_test.go"
)
for f in "${required[@]}"; do
  if [ -f "$f" ]; then ok "  $f"; else fail "missing: $f"; fi
done

# ────────────────────────────────────────────────────────────────────────────────
step "2/10 — Q-L1A-3 honored (full audit, no sampling) in service_to_service_audit"
# Look for any sampling / sample_rate / fraction column or comment that would
# contradict the LOCKED decision. There should be NONE.
banned='sample_rate\|sampling\|sample_pct\|sample_fraction'
if grep -qiE "$banned" migrations/meta/016_service_to_service_audit.up.sql; then
  fail "service_to_service_audit references sampling — Q-L1A-3 violation"
else
  ok "service_to_service_audit: no sampling references (Q-L1A-3 honored)"
fi
# Comment hints "full audit" should appear
if grep -q 'FULL audit\|Full audit\|full audit' migrations/meta/016_service_to_service_audit.up.sql; then
  ok "service_to_service_audit comments document Q-L1A-3 full-audit posture"
else
  fail "service_to_service_audit missing Q-L1A-3 full-audit comment"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "3/10 — append-only enforcement on all 5 audit tables"
for tbl in meta_write_audit meta_read_audit admin_action_audit service_to_service_audit prompt_audit; do
  case $tbl in
    meta_write_audit)        mig="migrations/meta/013_meta_write_audit.up.sql" ;;
    meta_read_audit)         mig="migrations/meta/014_meta_read_audit.up.sql" ;;
    admin_action_audit)      mig="migrations/meta/015_admin_action_audit.up.sql" ;;
    service_to_service_audit) mig="migrations/meta/016_service_to_service_audit.up.sql" ;;
    prompt_audit)            mig="migrations/meta/017_prompt_audit.up.sql" ;;
  esac
  if grep -q "REVOKE UPDATE, DELETE ON TABLE $tbl FROM app_service_role" "$mig" && \
     grep -q "REVOKE UPDATE, DELETE ON TABLE $tbl FROM app_admin_role" "$mig"; then
    ok "$tbl REVOKE UPDATE/DELETE present on both roles"
  else
    fail "$tbl missing append-only REVOKE on app_service_role or app_admin_role"
  fi
done

# ────────────────────────────────────────────────────────────────────────────────
step "4/10 — prompt_audit body-never-stored invariant (DDL + interface)"
# DDL: no body / prompt_text / assembled_text column
forbidden_cols='body\|prompt_text\|assembled_text\|full_prompt\|raw_prompt'
if grep -qiE "^[[:space:]]+($forbidden_cols)[[:space:]]" migrations/meta/017_prompt_audit.up.sql; then
  fail "prompt_audit migration contains forbidden body column"
else
  ok "prompt_audit DDL has no body column"
fi
# Interface: PromptAuditEntry struct has PromptContextHash (BYTEA), NOT a body field
if grep -q 'PromptContextHash \[\]byte' contracts/meta/prompt_audit.go; then
  ok "PromptAuditEntry.PromptContextHash []byte present (hash-only path)"
else
  fail "PromptAuditEntry missing PromptContextHash []byte"
fi
# Defense-in-depth: NO field named Body* in the Go struct
if grep -qE '^[[:space:]]+(Body|PromptText|AssembledText|FullPrompt|Raw)[[:space:]]' contracts/meta/prompt_audit.go; then
  fail "PromptAuditEntry has forbidden body field"
else
  ok "PromptAuditEntry has no body-shaped field"
fi
# Interface signature: RecordAssembly takes ONE arg (PromptAuditEntry), not multiple
if grep -q 'RecordAssembly(entry PromptAuditEntry) error' contracts/meta/prompt_audit.go; then
  ok "PromptAudit.RecordAssembly signature is hash-only (entry parameter)"
else
  fail "PromptAudit.RecordAssembly signature drift — must take PromptAuditEntry only"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "5/10 — admin_action_audit scrubber-quad column + CHECK present"
# Look for column-declaration lines: "<colname> <TYPE> ..." (column name leads
# the declaration with leading whitespace, followed by ≥2 spaces then a type).
missing_cols=""
for col in error_detail_raw_hash error_detail_scrubbed scrub_version scrubbed_at; do
  if ! grep -qE "^[[:space:]]+${col}[[:space:]]+(BYTEA|TEXT|TIMESTAMPTZ)" \
        migrations/meta/015_admin_action_audit.up.sql; then
    missing_cols="$missing_cols $col"
  fi
done
if [ -z "$missing_cols" ]; then
  ok "admin_action_audit has all 4 scrubber columns"
else
  fail "admin_action_audit scrubber-quad incomplete (missing:$missing_cols)"
fi
if grep -q 'admin_action_audit_scrubber_quad_consistent' migrations/meta/015_admin_action_audit.up.sql; then
  ok "admin_action_audit scrubber-quad CHECK present"
else
  fail "admin_action_audit scrubber-quad CHECK missing"
fi
# Scrubber interface stub: no Unscrub / Reverse / GetRaw method
if grep -qiE 'func.*\bUnscrub\b\|func.*\bReverse\b\|func.*GetRaw\b' contracts/meta/scrubber.go; then
  fail "scrubber.go has a reverse/raw-accessor — invariant violation"
else
  ok "scrubber.go has no reverse/raw-accessor (one-way property holds)"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "6/10 — pkColumnFor extended for all 5 audit tables (cycle 4)"
# The cycle 4 entries are written as a single multi-line case clause sharing
# one `return "audit_id"`. Look for each string literal in lifecycle.go,
# scoped after the "Cycle 4" marker comment.
pkfile=contracts/meta/lifecycle.go
for entry in '"meta_write_audit"' '"meta_read_audit"' '"admin_action_audit"' '"service_to_service_audit"' '"prompt_audit"'; do
  if grep -q "$entry" "$pkfile"; then
    ok "pkColumnFor handles $entry"
  else
    fail "pkColumnFor missing $entry"
  fi
done
# Cycle-4 marker comment present
if grep -q 'Cycle 4 — L1.A-3 audit tables' "$pkfile"; then
  ok "pkColumnFor cycle-4 marker comment present"
else
  fail "pkColumnFor missing cycle-4 marker comment"
fi
# All 5 audit tables share one `return "audit_id"` per the case clause
if grep -qE '^\s*"prompt_audit":\s*$' "$pkfile" && \
   grep -A1 '"prompt_audit":' "$pkfile" | grep -q 'return "audit_id"'; then
  ok "pkColumnFor cycle-4 case returns audit_id"
else
  fail "pkColumnFor cycle-4 case does not appear to return audit_id"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "7/10 — events_allowlist.yaml extended (5 tables, NO outbox events)"
for tbl in meta_write_audit meta_read_audit admin_action_audit service_to_service_audit prompt_audit; do
  if grep -qE "table: $tbl(\\s|\$)" contracts/meta/events_allowlist.yaml; then
    ok "allowlist: $tbl present"
  else
    fail "allowlist: $tbl missing"
  fi
done

# ────────────────────────────────────────────────────────────────────────────────
step "8/10 — doc.go cycle-4 reference present (stale 'cycle 10' note removed)"
if grep -q 'Cycle 4 (L1.A-3) ships' contracts/meta/doc.go; then
  ok "doc.go documents cycle 4 audit infrastructure"
else
  fail "doc.go missing cycle 4 audit-infrastructure block"
fi
# Old "ship in a later cycle (L1.A-3 audit infrastructure)" phrasing must be gone
if grep -q 'ship in a later cycle (L1.A-3' contracts/meta/doc.go; then
  fail "doc.go still contains stale 'ship in a later cycle (L1.A-3)' wording"
else
  ok "doc.go: stale 'later cycle' wording removed"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "9/10 — Go: build + vet + test contracts/meta (incl. audit_l1a3_test.go + audit-wiring tests)"
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
      ok "go test contracts/meta (incl. TestPkColumnFor_L1A3Tables + audit-wiring + prompt body shape)"
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

# Rust: meta-rs is read-only per Q-L1B-4 — no audit-write surface added. Still
# build it to catch any incidental break (e.g., yaml parser regression).
if command -v cargo >/dev/null 2>&1; then
  if cargo build -p meta-rs 2>&1; then
    ok "cargo build -p meta-rs (read-only surface; no L1.A-3 changes expected)"
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
step "10/10 — SQL migrations: structural / dry-run + append-only smoke (where docker)"
docker_used=0
if command -v docker >/dev/null 2>&1; then
  if [ -n "$(docker compose -f infra/docker-compose.meta-ha.yml ps --status=running -q primary 2>/dev/null || true)" ]; then
    docker_used=1
    export PGPASSWORD=${PATRONI_SUPERUSER_PASSWORD:-postgres}
    docker exec lw-meta-pg-primary psql -U postgres -d postgres \
      -c "CREATE DATABASE loreweave_meta_verify_c4;" 2>/dev/null && \
      ok "created loreweave_meta_verify_c4 DB"
    # Apply ALL migrations (cycle 2+3+4) in order
    for up in migrations/meta/0*.up.sql; do
      if docker exec -i lw-meta-pg-primary psql -U postgres -d loreweave_meta_verify_c4 < "$up" >/dev/null 2>&1; then
        ok "UP: $up"
      else
        fail "UP: $up"
      fi
    done
    # Append-only smoke: create app_service_role, attempt UPDATE on meta_write_audit, expect denial.
    docker exec lw-meta-pg-primary psql -U postgres -d loreweave_meta_verify_c4 -c \
      "CREATE ROLE app_service_role; GRANT INSERT ON meta_write_audit TO app_service_role;" >/dev/null 2>&1 || true
    update_result=$(docker exec lw-meta-pg-primary psql -U postgres -d loreweave_meta_verify_c4 -c \
      "SET ROLE app_service_role; UPDATE meta_write_audit SET reason='tamper' WHERE 1=1;" 2>&1 || true)
    if echo "$update_result" | grep -qi 'permission denied'; then
      ok "append-only: UPDATE on meta_write_audit denied for app_service_role"
    else
      fail "append-only: UPDATE on meta_write_audit was NOT denied (got: $update_result)"
    fi
    # Reverse: down migrations succeed in reverse order
    for down in $(ls migrations/meta/0*.down.sql | sort -r); do
      if docker exec -i lw-meta-pg-primary psql -U postgres -d loreweave_meta_verify_c4 < "$down" >/dev/null 2>&1; then
        ok "DOWN: $down"
      else
        fail "DOWN: $down"
      fi
    done
    docker exec lw-meta-pg-primary psql -U postgres -d postgres \
      -c "DROP DATABASE loreweave_meta_verify_c4;" >/dev/null 2>&1 || true
  fi
fi
if [ "$docker_used" -eq 0 ]; then
  echo "[verify-cycle-$CYCLE] note: docker / meta-ha stack absent — structural SQL check fallback"
  for up in migrations/meta/013_*.up.sql migrations/meta/014_*.up.sql \
            migrations/meta/015_*.up.sql migrations/meta/016_*.up.sql \
            migrations/meta/017_*.up.sql; do
    if grep -q 'CREATE TABLE' "$up"; then ok "structural: $up"; else fail "$up missing CREATE TABLE"; fi
  done
  for down in migrations/meta/013_*.down.sql migrations/meta/014_*.down.sql \
              migrations/meta/015_*.down.sql migrations/meta/016_*.down.sql \
              migrations/meta/017_*.down.sql; do
    if grep -q 'DROP TABLE' "$down"; then ok "structural: $down"; else fail "$down missing DROP TABLE"; fi
  done
fi

# ────────────────────────────────────────────────────────────────────────────────
audit "verify_cycle_complete" "\"failed\":$FAILED"

if [ "$FAILED" -ne 0 ]; then
  echo "[verify-cycle-$CYCLE] FAIL: one or more checks failed"
  exit 1
fi
echo "[verify-cycle-$CYCLE] PASS"
exit 0
