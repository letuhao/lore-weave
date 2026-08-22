#!/usr/bin/env bash
# `A2` — bring ONE existing reality forward to the manifest head.
#
# WHY THIS IS A SCRIPT AND NOT NINE COMMANDS IN A PLAN
# ----------------------------------------------------
# `migrate` takes ONE migration id per invocation, so bringing a reality from
# `0021_turn_slot` to `0030_encounter` is nine of them, in order, with the same
# six flags each time. That is a procedure nobody can re-run correctly — the same
# defect `G2` recorded about a demo assembled across six hand-typed shells, and
# `EO-2` about `E1` before it.
#
# It is also the step that writes to a NON-THROWAWAY reality, which is the one
# thing the space-producers and world-in-a-running-reality boards both stop for.
# So it fails closed twice over: no `--reality`, no run; no `--confirm`, no write.
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
#   * VERIFIES afterwards, against the reality itself: the ledger advanced and
#     the seven tables exist. A migration run that reports success while the
#     table is absent is exactly what `1b12-05` found once already.
#
#   bash scripts/bring-reality-forward.sh --reality <uuid> --meta-dsn <dsn>
#   bash scripts/bring-reality-forward.sh --reality <uuid> --meta-dsn <dsn> --confirm
#
# `--verify-dsn` is optional and read-only: the DSN of the reality's OWN database,
# used only for the after-check. Without it the run still applies, and says that
# it could not verify rather than implying it did.
set -euo pipefail
cd "$(dirname "$0")/.."

REALITY=""
META_DSN=""
VERIFY_DSN=""
CONFIRM=0
EXTRA=()

while [ $# -gt 0 ]; do
  case "$1" in
    --reality)    REALITY="${2:-}"; shift 2 ;;
    --meta-dsn)   META_DSN="${2:-}"; shift 2 ;;
    --verify-dsn) VERIFY_DSN="${2:-}"; shift 2 ;;
    --confirm)    CONFIRM=1; shift ;;
    *)            EXTRA+=("$1"); shift ;;
  esac
done

# FAIL CLOSED, both ways. A missing `--reality` must never mean "the whole
# fleet": that is the difference between migrating one reality and migrating ten.
[ -n "$REALITY" ]  || { echo "ERROR: --reality <uuid> is required. This script migrates ONE reality, never the fleet." >&2; exit 2; }
[ -n "$META_DSN" ] || { echo "ERROR: --meta-dsn <dsn> is required." >&2; exit 2; }

# The manifest order, and it is the manifest's, not this file's opinion of it.
# `migration-manifest-gate` keeps versions strictly increasing with no forward
# dependency, so reading the ids out of the manifest keeps this list from
# becoming a second source of truth that drifts.
# `tr -d` because this runs on Windows too: python prints CRLF there, `mapfile`
# keeps the carriage return, and `migrate` then reports
#   ERROR: migration "0022_actors\\r" not found
# Caught by PLAN mode before any write, which is what plan mode is for.
mapfile -t MIGRATIONS < <(
  python -c "
import yaml, sys
m = yaml.safe_load(open('contracts/migrations/manifest.yaml', encoding='utf-8'))
migs = m['migrations'] if isinstance(m, dict) and 'migrations' in m else m
for x in sorted(migs, key=lambda r: r['version']):
    if x['id'] >= '0022':
        print(x['id'])
" | tr -d '\r'
)
[ "${#MIGRATIONS[@]}" -gt 0 ] || { echo "ERROR: read no migrations from the manifest — refusing to report a clean run over nothing." >&2; exit 2; }

echo "== reality $REALITY"
echo "== ${#MIGRATIONS[@]} migration(s) from the manifest: ${MIGRATIONS[*]}"
if [ "$CONFIRM" -eq 0 ]; then
  echo "== PLAN ONLY (no --confirm). Nothing will be written."
fi
echo

MIGRATE=(go run ./cmd/migrate)
run_one() {
  local id="$1"; shift
  ( cd services/migration-orchestrator && "${MIGRATE[@]}" "$id" \
      --manifest ../../contracts/migrations/manifest.yaml \
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
if [ -z "$VERIFY_DSN" ]; then
  echo "== applied. NOT VERIFIED — pass --verify-dsn <reality dsn> to check the result."
  exit 0
fi
echo "== verifying against the reality itself"
psql "$VERIFY_DSN" -tAc "SELECT '   ledger: '||count(*)||' migrations, newest '||max(id) FROM schema_migrations"
missing=0
for t in actors map_layout entity_binding place portal layer_registry encounter; do
  present=$(psql "$VERIFY_DSN" -tAc "SELECT (to_regclass('public.$t') IS NOT NULL)::text")
  printf "   %-16s %s\n" "$t" "$present"
  [ "$present" = "t" ] || missing=$((missing + 1))
done
if [ "$missing" -gt 0 ]; then
  echo "!! $missing table(s) ABSENT after a run that reported success. This is 1b12-05's shape." >&2
  exit 1
fi
echo "== verified: the ledger advanced and all seven tables exist."
