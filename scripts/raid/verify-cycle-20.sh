#!/usr/bin/env bash
# verify-cycle-20 — C20 world container (book-service) acceptance gate.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). BE-only Go cycle: worlds table +
# nullable world_id FK on books (ON DELETE SET NULL) + auto-provisioned hidden
# sort_order-0 bible chapter. Grep-asserts the migration shape + handlers, then
# runs go test + go vet + the provider-gate. Migration round-trip (up→down→re-up
# on real PG) + cross-service live-smoke are recorded separately at VERIFY.
set -euo pipefail
CYCLE=20
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BS="$REPO_ROOT/services/book-service"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-20] FAIL: $1" >&2; audit "verify_cycle_20_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-20] running CI gate"

MIG="$BS/internal/migrate/migrate.go"
WLD="$BS/internal/api/worlds.go"
SRV="$BS/internal/api/server.go"

# ── 1. Migration: worlds table + nullable world_id FK (SET NULL) + is_bible ──
have "$MIG" "CREATE TABLE IF NOT EXISTS worlds"                  "migrate.go missing worlds table"
have "$MIG" "owner_user_id UUID NOT NULL"                        "worlds missing owner_user_id"
have "$MIG" "ALTER TABLE books ADD COLUMN IF NOT EXISTS world_id UUID" "books missing world_id column"
have "$MIG" "REFERENCES worlds(id) ON DELETE SET NULL"           "world_id FK must be ON DELETE SET NULL (not cascade)"
have "$MIG" "ALTER TABLE chapters ADD COLUMN IF NOT EXISTS is_bible BOOLEAN NOT NULL DEFAULT false" "chapters missing is_bible flag"
# world_id must be NULLABLE — a NOT NULL declaration is a G1 LOCK breach.
grep -Fq "world_id UUID NOT NULL" "$MIG" && fail "world_id must be NULLABLE (default NULL = standalone)" || true
# down-migration drops column BEFORE table (FK ordering), reversible round-trip.
have "$MIG" "ALTER TABLE books DROP COLUMN IF EXISTS world_id"   "WorldsDownSQL missing world_id column drop"
have "$MIG" "DROP TABLE IF EXISTS worlds"                        "WorldsDownSQL missing worlds table drop"

# ── 2. Handlers: world CRUD + move-book + list-books + bible provisioning ────
have "$WLD" "func (s *Server) createWorld"        "worlds.go missing createWorld"
have "$WLD" "func (s *Server) listWorlds"         "worlds.go missing listWorlds"
have "$WLD" "func (s *Server) patchWorld"         "worlds.go missing patchWorld"
have "$WLD" "func (s *Server) deleteWorld"        "worlds.go missing deleteWorld"
have "$WLD" "func (s *Server) moveBookIntoWorld"  "worlds.go missing moveBookIntoWorld"
have "$WLD" "func (s *Server) removeBookFromWorld" "worlds.go missing removeBookFromWorld"
have "$WLD" "func (s *Server) listWorldBooks"     "worlds.go missing listWorldBooks"
have "$WLD" "func provisionBibleChapter"          "worlds.go missing provisionBibleChapter"
# bible chapter is hidden (is_bible=true) at sort_order 0, idempotency guard.
grep -Fq "is_bible=true" "$WLD"   || fail "bible chapter must be marked is_bible=true (hidden)"
grep -Fq "WHERE NOT EXISTS" "$WLD" || fail "bible provisioning must be idempotent (WHERE NOT EXISTS guard)"
# owner-scoping: world CRUD keyed by owner_user_id (no cross-user bleed).
grep -Fq "owner_user_id=\$2" "$WLD" || fail "world CRUD must be owner-scoped (owner_user_id filter)"

# ── 3. Routes registered ─────────────────────────────────────────────────────
have "$SRV" 'r.Route("/v1/worlds"'        "server.go missing /v1/worlds route group"
have "$SRV" "s.moveBookIntoWorld"         "server.go missing move-book route"
have "$SRV" "s.listWorldBooks"            "server.go missing list-world-books route"

# ── 4. Out-of-scope guard: ZERO edits to lore/sharing service code ───────────
# C20 is book-service-only — lore stays book_id/chapter_id-keyed. A world_id
# column in any lore DB is a LOCK breach.
if grep -rEn 'ADD COLUMN[^;]*world_id|world_id (UUID|uuid)' \
     "$REPO_ROOT/services/glossary-service" \
     "$REPO_ROOT/services/knowledge-service" \
     "$REPO_ROOT/services/composition-service" 2>/dev/null | grep -v '_test' >/dev/null 2>&1; then
  fail "world_id reference found in a lore service — additivity breach (G1 LOCK)"
fi

# ── 5. Go test + vet + provider-gate ─────────────────────────────────────────
echo "[verify-cycle-20] go test ./..."
go test -C "$BS" ./... -count=1 2>&1 | tail -8
echo "[verify-cycle-20] go vet ./..."
go vet -C "$BS" ./... 2>&1 | tail -4
echo "[verify-cycle-20] provider-gate"
python "$REPO_ROOT/scripts/ai-provider-gate.py" 2>&1 | tail -2

audit "verify_cycle_20_passed"
echo "[verify-cycle-20] PASS"
exit 0
