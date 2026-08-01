#!/usr/bin/env bash
# reality-binding-migration-smoke.sh — Q1 B2a
#
# Migration 033 makes three claims that only a real Postgres can settle:
#
#   1. the table is APPEND-ONLY for every role, superuser included
#   2. epochs are gapless and start at 1
#   3. a malformed digest never lands
#
# All three are enforced by triggers and CHECK constraints, which means the
# usual unit-test surface cannot reach them: there is no Rust or Go code path
# between the caller and the refusal. Reviewing the SQL is not evidence that it
# runs — this script is.
#
# The append-only claim in particular would be VACUOUS if it rested on the
# repo's usual `REVOKE UPDATE, DELETE FROM app_service_role` alone: the dev
# stack has no such role, the REVOKE is skipped with a NOTICE, and every dev
# connection keeps both privileges. This script connects as the superuser
# precisely because that is the connection the REVOKE cannot restrain.
#
#   bash scripts/reality-binding-migration-smoke.sh
#   PG_CONTAINER=infra-postgres-1 PG_USER=loreweave bash scripts/…
#
# Exit 0 = every claim held; 1 = a claim failed; 2 = setup could not run.
#
# db-safety-gate: file-ok — the DB name is overridable (BINDING_SMOKE_DB), which
# is exactly the shape that needs a guard rather than a promise, so there is one:
# the marker check below runs BEFORE the first destructive statement and exits 2
# on any name that does not announce itself as disposable. Default target is
# loreweave_test_meta_binding_smoke.

set -uo pipefail

PG_CONTAINER="${PG_CONTAINER:-infra-postgres-1}"
PG_USER="${PG_USER:-loreweave}"
DB="${BINDING_SMOKE_DB:-loreweave_test_meta_binding_smoke}"
MIGRATION="migrations/meta/033_reality_ruleset_binding.up.sql"

fails=0
log() { printf '[binding-smoke] %s\n' "$*"; }

# ── throwaway-DB guard (CLAUDE.md "Destructive DB ops"): refuse ANY database
# name that does not announce itself as disposable, BEFORE the first DROP.
case "$DB" in
  *test*|*smoke*) ;;
  *)
    log "FAIL(setup): refusing to DROP/CREATE '$DB' — a destructive fixture may"
    log "             only target a database whose name carries a throwaway"
    log "             marker (test/smoke). This guard runs before the first"
    log "             destructive statement, not after."
    exit 2 ;;
esac

docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 || {
  log "FAIL(setup): postgres container '$PG_CONTAINER' is not accepting connections."
  log "             Bring the dev stack up, or pass PG_CONTAINER=<name>."
  exit 2
}
[ -f "$MIGRATION" ] || { log "FAIL(setup): $MIGRATION not found (run from the repo root)"; exit 2; }

psql_q()  { docker exec -i "$PG_CONTAINER" psql -qtAX -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$1" -c "$2"; }
psql_raw(){ docker exec -i "$PG_CONTAINER" psql -qtAX -U "$PG_USER" -d "$DB" -c "$1" 2>&1; }

log "(re)creating throwaway DB $DB ..."
psql_q postgres "DROP DATABASE IF EXISTS ${DB}" >/dev/null 2>&1
psql_q postgres "CREATE DATABASE ${DB}"        >/dev/null 2>&1 || { log "FAIL(setup): CREATE DATABASE"; exit 2; }

log "applying $MIGRATION ..."
if ! docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" < "$MIGRATION" >/dev/null 2>&1; then
  log "FAIL: the migration itself did not apply"
  docker exec -i "$PG_CONTAINER" psql -q -U "$PG_USER" -d "$DB" < "$MIGRATION" 2>&1 | sed 's/^/  /'
  exit 1
fi

R1="11111111-1111-4111-8111-111111111111"
R2="22222222-2222-4222-8222-222222222222"
D1="$(printf 'a%.0s' $(seq 1 64))"
D2="$(printf 'b%.0s' $(seq 1 64))"

# expect_ok <label> <sql>
expect_ok() {
  local label="$1" sql="$2" out
  out="$(psql_raw "$sql")"
  if [ $? -ne 0 ] || printf '%s' "$out" | grep -qi 'ERROR'; then
    log "FAIL: $label — expected to SUCCEED but it was refused:"
    printf '%s\n' "$out" | sed 's/^/       /'
    fails=$((fails + 1))
  else
    log "  ok  $label"
  fi
}

# expect_refused <label> <sql> <substring the diagnostic must contain>
#
# The substring is not decoration. A test that only asserts "some error" passes
# when the statement fails for an unrelated reason — a typo'd column, a missing
# table — and then reports the guard as working when the guard was never
# reached. Naming the reason is what makes the refusal evidence.
expect_refused() {
  local label="$1" sql="$2" want="$3" out
  out="$(psql_raw "$sql")"
  if ! printf '%s' "$out" | grep -qi 'ERROR'; then
    log "FAIL: $label — the statement SUCCEEDED; the guard did not fire"
    fails=$((fails + 1))
  elif ! printf '%s' "$out" | grep -qi -- "$want"; then
    log "FAIL: $label — refused, but for the WRONG reason (want /$want/):"
    printf '%s\n' "$out" | sed 's/^/       /'
    fails=$((fails + 1))
  else
    log "  ok  $label (refused: $(printf '%s' "$out" | grep -i ERROR | head -1 | cut -c1-90))"
  fi
}

ins() { printf "INSERT INTO reality_ruleset_binding (reality_id, epoch, ruleset_digest, reason) VALUES ('%s', %s, '%s', '%s')" "$1" "$2" "$3" "$4"; }

log "── claim 1: a binding can be created, and only at epoch 1 ──"
expect_ok       "epoch 1 for a new reality"        "$(ins "$R1" 1 "$D1" 'reality created')"
expect_refused  "a second reality may not start at epoch 2" \
                "$(ins "$R2" 2 "$D1" 'wrong start')" "must be 1"
expect_ok       "…and the same reality at epoch 1 is fine (negative control)" \
                "$(ins "$R2" 1 "$D1" 'reality created')"

log "── claim 2: epochs are gapless and monotonic ──"
expect_refused  "epoch 3 with no epoch 2"          "$(ins "$R1" 3 "$D2" 'skipped one')" "must be epoch 2"
expect_ok       "epoch 2 lands"                    "$(ins "$R1" 2 "$D2" 'rules changed')"
# Re-INSERTing an epoch that already exists is caught by the GAPLESS trigger,
# not the primary key — a BEFORE INSERT trigger runs ahead of the index. The
# first draft of this line expected 'duplicate key' and this script reported it
# as refused-for-the-wrong-reason, which is the whole reason the expected
# substring is required rather than "some error".
#
# So the PK is not this statement's guard. Its job is the one case the trigger
# cannot cover: two concurrent inserts both reading max(epoch)=1 and both
# passing the trigger. That is a race, and a single-threaded script cannot
# produce it — said out loud here rather than left as an untested clause.
expect_refused  "epoch 2 again"                    "$(ins "$R1" 2 "$D1" 'replay')" "must be epoch 3"

log "── claim 3: APPEND-ONLY, against the superuser the REVOKE cannot restrain ──"
expect_refused  "UPDATE a binding's digest" \
                "UPDATE reality_ruleset_binding SET ruleset_digest='$D2' WHERE reality_id='$R1' AND epoch=1" \
                "append-only"
expect_refused  "DELETE a binding" \
                "DELETE FROM reality_ruleset_binding WHERE reality_id='$R1' AND epoch=1" \
                "append-only"

log "── claim 4: a malformed digest never lands ──"
expect_refused  "uppercase hex"    "$(ins "$R2" 2 "$(printf 'A%.0s' $(seq 1 64))" 'x')" "digest_format"
expect_refused  "63 hex digits"    "$(ins "$R2" 2 "$(printf 'a%.0s' $(seq 1 63))" 'x')" "digest_format"
expect_refused  "empty reason"     "$(ins "$R2" 2 "$D2" '')"                            "reason_nonempty"

log "── claim 5: the guards survive the mode that switches triggers OFF ──"
#
# `SET session_replication_role = replica` is what `pg_restore --disable-triggers`
# and logical-replication apply use, and it stops ORIGIN triggers firing. This
# arm exists because the first draft of migration 033 FAILED it: the UPDATE
# rewrote a bound digest and the DELETE removed the epoch, both silently. The
# fix was ENABLE ALWAYS on the append-only trigger.
#
# The same probe is what proves `epoch_positive` is not dead SQL. The gapless
# trigger shadows that CHECK for every input a client can send, so it looks
# unreachable — and it IS unreachable, except here, where the trigger is off and
# the CHECK is the only thing left. A constraint nobody has watched fail is a
# claim; this is the input that makes it a guard.
replica() { printf "SET session_replication_role = replica; %s" "$1"; }

expect_refused  "epoch 0 with triggers bypassed (the CHECK is the last line)" \
                "$(replica "$(ins "$R2" 0 "$D2" 'probe')")" "epoch_positive"
expect_refused  "UPDATE with triggers bypassed" \
                "$(replica "UPDATE reality_ruleset_binding SET ruleset_digest='$D2' WHERE reality_id='$R1' AND epoch=1")" \
                "append-only"
expect_refused  "DELETE with triggers bypassed" \
                "$(replica "DELETE FROM reality_ruleset_binding WHERE reality_id='$R1' AND epoch=1")" \
                "append-only"

log "── the history the never-reuse rule (QTY-A5) is recomputed from ──"
rows="$(psql_q "$DB" "SELECT count(*) FROM reality_ruleset_binding WHERE reality_id='$R1'")"
if [ "$rows" != "2" ]; then
  log "FAIL: reality $R1 should have 2 surviving epochs, has '$rows'"
  fails=$((fails + 1))
else
  log "  ok  both epochs survive as rows — the prior epoch's ruleset is still"
  log "      reachable, which is what makes 'never reused on removal' checkable"
fi

log "── claim 6: the DOWN migration reverses the UP one ──"
#
# A down migration nobody has ever run is a claim. This one has to drop two
# triggers and two FUNCTIONS as well as the table — the easiest thing to forget,
# and the failure is silent: the next `up` hits CREATE OR REPLACE and inherits a
# stale function body.
if docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" \
     < "migrations/meta/033_reality_ruleset_binding.down.sql" >/dev/null 2>&1; then
  leftovers="$(psql_q "$DB" "SELECT count(*) FROM pg_proc WHERE proname LIKE 'reality_ruleset_binding%'")"
  tbl="$(psql_q "$DB" "SELECT count(*) FROM pg_tables WHERE tablename = 'reality_ruleset_binding'")"
  if [ "$leftovers" != "0" ] || [ "$tbl" != "0" ]; then
    log "FAIL: down left $tbl table(s) and $leftovers function(s) behind"
    fails=$((fails + 1))
  else
    log "  ok  table, triggers and both functions all gone"
  fi
  # …and up applies again on the cleaned schema, which is what a rollback is FOR.
  if docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" \
       < "$MIGRATION" >/dev/null 2>&1; then
    log "  ok  up re-applies after down"
  else
    log "FAIL: up did not re-apply after down"
    fails=$((fails + 1))
  fi
else
  log "FAIL: the down migration did not apply"
  fails=$((fails + 1))
fi

log "cleaning up $DB ..."
psql_q postgres "DROP DATABASE IF EXISTS ${DB}" >/dev/null 2>&1

if [ "$fails" -gt 0 ]; then
  log "FAIL — $fails claim(s) did not hold"
  exit 1
fi
log "PASS — migration 033 applies, and every guard in it fired on a real Postgres"
exit 0
