#!/usr/bin/env bash
# emit-migration-0013-lint.sh — drift guard for the W3.4 content checksum.
#
# The Go emit path (tests/workload-gen `-emit`, emit.go insertEventsSQL) and the
# dp-kernel append BOTH stamp events.content_sha256 with the migration-0013
# column. A drill that builds its OWN per-reality events DB and then runs `wg
# -emit` MUST therefore apply 0013_events_content_sha256, or the INSERT fails on
# the missing column. This guard flags any script that:
#
#   (a) sets up its own events baseline  (mentions `0002_events_table`), AND
#   (b) invokes the wg emit path         (a ` -emit` flag — leading space so the
#                                         pgbench file `scale-emit.sql` etc. do
#                                         NOT false-match), BUT
#   (c) does NOT apply `0013_events_content_sha256`.
#
# Scripts that rely on `scale-rig.sh migrate` (no own 0002) are NOT flagged — the
# rig's migrate path already applies 0013. Scripts that emit via raw pgbench (no
# ` -emit` wg flag) are NOT flagged — they don't reference content_sha256.
#
# Exit 0 = clean; 1 = an emit script missing 0013; 2 = misuse / selftest failure.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

# violates TEXT — echoes "MISSING-0013" when the text is an own-baseline emit
# script that omits 0013, else nothing. Returns 0 always.
violates() {
  local text="$1"
  if printf '%s' "$text" | grep -q '0002_events_table' \
     && printf '%s' "$text" | grep -q ' -emit' \
     && ! printf '%s' "$text" | grep -q '0013_events_content_sha256'; then
    echo MISSING-0013
  fi
  return 0
}

run_lint() {
  local violations=0 f
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    if [ -n "$(violates "$(cat "$f")")" ]; then
      echo "[emit-0013] FAIL — $f sets up its own events baseline + runs 'wg -emit' but does NOT apply 0013_events_content_sha256"
      echo "  → add 0013_events_content_sha256 to its migration list (the emit path stamps events.content_sha256)."
      violations=$((violations + 1))
    fi
  done < <(find "$repo_root/scripts" -name '*.sh' -type f)
  if [ "$violations" -gt 0 ]; then exit 1; fi
  echo "[emit-0013] PASS — every own-baseline emit script applies 0013"
}

# --selftest is the non-vacuity BITE: a synthetic bad script (own baseline + emit,
# no 0013) MUST flag; a good one (with 0013) MUST pass.
selftest() {
  local bad good
  bad='for m in 0001_initial 0002_events_table 0005_events_outbox_table; do :; done
"$WG" -seed 1 -profile x -emit -dsn "$DSN"'
  good='for m in 0001_initial 0002_events_table 0013_events_content_sha256; do :; done
"$WG" -emit -dsn "$DSN"'
  if [ -z "$(violates "$bad")" ]; then
    echo "[emit-0013] SELFTEST FAIL — did NOT flag an own-baseline emit script missing 0013 (vacuous)"; exit 2
  fi
  if [ -n "$(violates "$good")" ]; then
    echo "[emit-0013] SELFTEST FAIL — flagged a script that DOES apply 0013"; exit 2
  fi
  echo "[emit-0013] SELFTEST PASS — flags a missing-0013 emit script, passes one with 0013 (non-vacuous)"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint ;;
  "")         selftest; run_lint ;;
  *)          echo "usage: $0 [--selftest | --lint]"; exit 2 ;;
esac
