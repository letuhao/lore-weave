#!/usr/bin/env bash
# `A2` — bring ONE existing reality forward to the manifest head.
#
# WHY THIS IS A SCRIPT AND NOT ELEVEN COMMANDS IN A PLAN
# ------------------------------------------------------
# `migrate` takes ONE migration id per invocation, so bringing a reality from
# `0019_channels` to `0030_encounter` is eleven of them, in order, with the same
# six flags each time. That is a procedure nobody can re-run correctly — the same
# defect `G2` recorded about a demo assembled across six hand-typed shells, and
# `EO-2` about `E1` before it.
#
# It is also the step that writes to a NON-THROWAWAY reality, which is the one
# thing the space-producers and world-in-a-running-reality boards both stop for.
# So it fails closed twice over: no `--reality`, no run; no `--confirm`, no write.
#
# THE LIST IS ASKED OF THE REALITY, NEVER ASSUMED
# -----------------------------------------------
# The first version of this file hardcoded `id >= '0022'`, because the one
# reality it was written against sits at `0021_turn_slot`. **Seven of the ten sit
# at `0019_channels`.** Run as written, those seven would have been brought to
# `0030_encounter` with `0020` and `0021` MISSING and nothing saying so — a
# reality that reads current and has a hole in it. That is `1b12-05`'s shape
# ("reports success while the thing is absent") and `1b5-H1`'s ("the fix reached
# one site of N") in a single line of code.
#
# So the list is now **the manifest minus the reality's own `schema_migrations`
# ledger**, computed per reality. `--reality-dsn` is REQUIRED for that reason: a
# script that cannot ask what is missing can only guess, and guessing is the
# defect above.
#
# WHAT IT DOES, AND WHAT IT REFUSES
# ---------------------------------
#   * PLANS by default. Without `--confirm` it dry-runs every migration and
#     writes nothing — that output is what an authorisation request should carry.
#   * ONE reality. `--reality` is required and is passed straight through, where
#     an id outside the drainable fleet is REFUSED rather than narrowing to
#     nothing (see `selectFleet`).
#   * THROUGH THE ORCHESTRATOR, never hand-run SQL. That is `I-3`, and it is why
#     this shells out to `migrate` rather than to `psql`.
#   * VERIFIES afterwards against the reality itself, and the verify ASSERTS
#     rather than prints: every id it applied must now be in the reality's own
#     ledger, and the seven tables must exist.
#
#   bash scripts/bring-reality-forward.sh --reality <uuid> --meta-dsn <dsn> --reality-dsn <dsn>
#   bash scripts/bring-reality-forward.sh --reality <uuid> --meta-dsn <dsn> --reality-dsn <dsn> --confirm
#
# Unrecognised flags (`--host-override`, `--pg-user`, …) pass through to `migrate`.
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."

REALITY=""
META_DSN=""
REALITY_DSN=""
CONFIRM=0
EXTRA=()

while [ $# -gt 0 ]; do
  case "$1" in
    --reality)     REALITY="${2:-}"; shift 2 ;;
    --meta-dsn)    META_DSN="${2:-}"; shift 2 ;;
    --reality-dsn) REALITY_DSN="${2:-}"; shift 2 ;;
    --confirm)     CONFIRM=1; shift ;;
    *)             EXTRA+=("$1"); shift ;;
  esac
done

# FAIL CLOSED, three ways. A missing `--reality` must never mean "the whole
# fleet": that is the difference between migrating one reality and migrating ten.
# A missing `--reality-dsn` must never mean "assume it starts at 0022".
[ -n "$REALITY" ]     || { echo "ERROR: --reality <uuid> is required. This script migrates ONE reality, never the fleet." >&2; exit 2; }
[ -n "$META_DSN" ]    || { echo "ERROR: --meta-dsn <dsn> is required." >&2; exit 2; }
[ -n "$REALITY_DSN" ] || { echo "ERROR: --reality-dsn <dsn> is required -- the pending list is READ FROM THE REALITY, never assumed. See the header." >&2; exit 2; }

# What the reality already has. An empty answer is a REFUSAL, not "nothing
# applied yet": a database with no ledger is not one this script should be the
# first thing to touch.
APPLIED=$(psql "$REALITY_DSN" -tAc "SELECT id FROM schema_migrations ORDER BY id" | tr -d '\r')
[ -n "$APPLIED" ] || { echo "ERROR: the reality's schema_migrations ledger is EMPTY or unreadable -- refusing." >&2; exit 2; }

# The manifest order, and it is the manifest's, not this file's opinion of it.
# `migration-manifest-gate` keeps versions strictly increasing with no forward
# dependency, so reading the ids out of the manifest keeps this list from
# becoming a second source of truth that drifts.
# `tr -d` because this runs on Windows too: python prints CRLF there, `mapfile`
# keeps the carriage return, and `migrate` then reports
#   ERROR: migration "0022_actors\r" not found
# Caught by PLAN mode before any write, which is what plan mode is for.
mapfile -t MIGRATIONS < <(
  LW_APPLIED="$APPLIED" python -c "
import os, yaml
have = set(os.environ['LW_APPLIED'].split())
m = yaml.safe_load(open('contracts/migrations/manifest.yaml', encoding='utf-8'))
migs = m['migrations'] if isinstance(m, dict) and 'migrations' in m else m
for x in sorted(migs, key=lambda r: r['version']):
    if x['id'] not in have:
        print(x['id'])
" | tr -d '\r'
)

NAPPLIED=$(printf '%s\n' "$APPLIED" | grep -c .)
NEWEST=$(printf '%s\n' "$APPLIED" | tail -1)
echo "== reality $REALITY"
echo "== ledger says $NAPPLIED applied, newest $NEWEST"
if [ "${#MIGRATIONS[@]}" -eq 0 ]; then
  echo "== nothing pending: this reality is already at the manifest head."
  exit 0
fi
echo "== ${#MIGRATIONS[@]} pending: ${MIGRATIONS[*]}"
if [ "$CONFIRM" -eq 0 ]; then
  echo "== PLAN ONLY (no --confirm). Nothing will be written."
fi
echo

MIGRATE=(go run ./cmd/migrate)
# EVERY contracts path is passed explicitly, and that is not belt-and-braces.
# `migrate` has its own go.mod, so `go run` must happen INSIDE the module, so the
# CLI's relative defaults (`contracts/meta/…`, `contracts/migrations/…`) resolve
# against the wrong directory. Only `--manifest` was overridden at first, and
# DRY RUN NEVER NOTICED: a plan resolves the manifest and touches nothing else,
# so the allowlist path stayed broken until the first --confirm run said
#   ERROR: load allowlist contracts/meta/events_allowlist.yaml: ... cannot find
# Plan mode is a check on the PLAN, not on the flags the apply will need.
run_one() {
  local id="$1"; shift
  ( cd services/migration-orchestrator && "${MIGRATE[@]}" "$id" \
      --manifest ../../contracts/migrations/manifest.yaml \
      --allowlist ../../contracts/meta/events_allowlist.yaml \
      --sql-dir ../../contracts/migrations/per_reality \
      --meta-dsn "$META_DSN" --reality "$REALITY" "$@" "${EXTRA[@]+"${EXTRA[@]}"}" )
}

for id in "${MIGRATIONS[@]}"; do
  if [ "$CONFIRM" -eq 1 ]; then
    echo "-- applying $id"
    run_one "$id"
  else
    echo "-- plan $id"
    run_one "$id" --dry-run
  fi
  echo
done

if [ "$CONFIRM" -eq 0 ]; then
  echo "== planned only. Re-run with --confirm to apply."
  exit 0
fi

# ── AFTER-CHECK. A run that reports success while the table is absent is not a
#    hypothetical: `1b12-05` found `apply_migrations` doing exactly that.
#
#    BOTH halves assert. The ledger half is not decoration: until `SQLApplier`
#    wrote the reality's own `schema_migrations`, a migration applied through the
#    orchestrator left that ledger unmoved, and the next resume would re-apply
#    everything it had already done.
echo "== verifying against the reality itself"
missing=0
NOW=$(psql "$REALITY_DSN" -tAc "SELECT id FROM schema_migrations ORDER BY id" | tr -d '\r')
for id in "${MIGRATIONS[@]}"; do
  if ! printf '%s\n' "$NOW" | grep -qx -- "$id"; then
    echo "   !! $id applied but ABSENT from the reality's ledger" >&2
    missing=$((missing + 1))
  fi
done
echo "   ledger: $(printf '%s\n' "$NOW" | grep -c .) migrations, newest $(printf '%s\n' "$NOW" | tail -1)"
# `::text` on a boolean renders `true`/`false`, NOT psql's display form `t`/`f`.
# This compared against `t` and so reported all seven tables ABSENT in a run
# where all seven were present — a check that could only ever fail. It survived
# review because the after-check had never once run: the script shipped, was
# planned repeatedly, and was never `--confirm`ed until now. **Plan mode does not
# execute the verify**, which is the same blind spot that hid the allowlist path.
for t in actors map_layout entity_binding place portal layer_registry encounter; do
  present=$(psql "$REALITY_DSN" -tAc "SELECT (to_regclass('public.$t') IS NOT NULL)::text" | tr -d '\r')
  printf "   %-16s %s\n" "$t" "$present"
  [ "$present" = "true" ] || missing=$((missing + 1))
done
if [ "$missing" -gt 0 ]; then
  echo "!! $missing check(s) FAILED after a run that reported success. This is 1b12-05's shape." >&2
  exit 1
fi
echo "== verified: the ledger advanced and all seven tables exist."
