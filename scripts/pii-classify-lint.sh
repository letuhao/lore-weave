#!/usr/bin/env bash
# L1.K.2 pii-classify-lint.sh — S08 §12X.3
#
# Every migrations/meta/*.up.sql MUST carry these annotations in a header comment:
#   @pii_sensitivity: <none|low|medium|high|sensitive>
#   @retention_class: <one of S08 §12X.4 classes>
#   @retention_hot:   <duration> (e.g., 7y, 90d, indefinite)
#   @erasure_method:  <crypto_shred|hard_delete|pseudonymize_*|retain_legal|...>
#   @legal_basis:     <contract|legitimate_interest|legal_obligation|consent|...>
#
# ── THE REACH PROBLEM, and why this gate grew a floor (GATE-TEETH, 2026-08-11) ──
#
# Every migration numbered below 018 is grandfathered — `continue`, no checks.
# That is a legitimate exemption and it is also this gate's silent-nothing path:
# if the directory moved, if the glob stopped matching, or if a renumbering
# pushed the corpus back under 018, the loop would check ZERO files and print
# `PASS`. **A walk that reaches nothing and a clean tree produce byte-identical
# output, including exit 0.** So the count of files actually inspected is now
# asserted against a floor, and the scan is a function taking a directory so its
# arms can be proven on synthetic input rather than on whatever this repo holds.
#
# Exit 0 = clean; 1 = violations; 2 = misuse / the gate cannot see its corpus.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

required_tags=(
  '@pii_sensitivity'
  '@retention_class'
  '@retention_hot'
  '@erasure_method'
  '@legal_basis'
)

# Migrations 001..017 pre-date the lint and are grandfathered; 018+ MUST conform.
GRANDFATHER_BELOW=18

# The reach floor. Measured 2026-08-11: 39 meta migrations exist, 22 of them are
# numbered >= 018 and therefore inspected. The floor is 10 — deliberately well
# BELOW the real count and well above zero, because a floor set AT the measured
# value turns every arm above it into a floor test (`BDR-82`).
MIN_CHECKED=10

# Set by scan_dir.
checked=0
violations=0

# Inspect every *.up.sql in $1 that is not grandfathered.
scan_dir() {
  local dir="$1" f base num tag
  checked=0
  violations=0
  for f in "$dir"/*.up.sql; do
    # An unmatched glob expands to the literal pattern; skip it rather than
    # reporting five phantom violations against a filename that does not exist.
    [ -e "$f" ] || continue
    base=$(basename "$f")
    num=$(echo "$base" | grep -oE '^[0-9]+' || echo "")
    if [ -n "$num" ] && [ $((10#$num)) -lt "$GRANDFATHER_BELOW" ]; then
      continue
    fi
    checked=$((checked + 1))
    for tag in "${required_tags[@]}"; do
      if ! grep -q -- "$tag" "$f"; then
        echo "[pii-classify] FAIL — $base missing required tag: $tag"
        violations=$((violations + 1))
      fi
    done
  done
}

run_lint() {
  local dir="$repo_root/migrations/meta"
  if [ ! -d "$dir" ]; then
    echo "[pii-classify] FAIL — corpus directory $dir does not exist." >&2
    echo "  This gate's entire subject is the meta migrations. With the directory" >&2
    echo "  gone it would inspect nothing and report PASS." >&2
    exit 2
  fi

  scan_dir "$dir"

  if [ "$checked" -lt "$MIN_CHECKED" ]; then
    echo "[pii-classify] FAIL — inspected only $checked migration(s) (floor $MIN_CHECKED, measured 22)." >&2
    echo "  Every file numbered below $GRANDFATHER_BELOW is grandfathered, so a" >&2
    echo "  renumbering, a move or a glob that stopped matching leaves this gate" >&2
    echo "  scanning nothing and printing PASS. Raise the corpus or lower the" >&2
    echo "  grandfather line deliberately — do not let the number drift here." >&2
    exit 2
  fi

  if [ "$violations" -gt 0 ]; then
    echo "[pii-classify] FAIL — $violations missing tag(s) across $checked migration(s) (S08 §12X.3)"
    exit 1
  fi
  echo "[pii-classify] PASS — $checked migration(s) inspected, all 5 annotations present"
  exit 0
}

selftest() {
  local tmp fails=0
  tmp="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" RETURN

  local full_header=""
  local t
  for t in "${required_tags[@]}"; do
    full_header="${full_header}-- ${t}: x
"
  done

  # ARM 1 — a conforming file passes.
  printf '%s' "$full_header" > "$tmp/018_ok.up.sql"
  scan_dir "$tmp" >/dev/null
  if [ "$violations" -ne 0 ]; then
    echo "[pii-classify] SELFTEST FAIL — flagged a file carrying all 5 annotations"; fails=1
  fi
  if [ "$checked" -ne 1 ]; then
    echo "[pii-classify] SELFTEST FAIL — inspected $checked file(s), expected 1"; fails=1
  fi

  # ARM 2 — one missing annotation is caught, and ONLY one is reported.
  printf -- '-- @pii_sensitivity: x\n-- @retention_class: x\n-- @retention_hot: x\n-- @erasure_method: x\n' \
    > "$tmp/019_missing_basis.up.sql"
  scan_dir "$tmp" >/dev/null
  if [ "$violations" -ne 1 ]; then
    echo "[pii-classify] SELFTEST FAIL — one missing tag produced $violations violation(s), expected 1"; fails=1
  fi

  # ARM 3 — a file with NO annotations reports all five, not just the first.
  rm -f "$tmp/019_missing_basis.up.sql"
  echo "-- nothing here" > "$tmp/020_bare.up.sql"
  scan_dir "$tmp" >/dev/null
  if [ "$violations" -ne 5 ]; then
    echo "[pii-classify] SELFTEST FAIL — a bare file produced $violations violation(s), expected 5"; fails=1
  fi
  rm -f "$tmp/020_bare.up.sql"

  # ARM 4 — the grandfather line still exempts, and the exemption is what makes
  # the reach floor necessary: an un-inspected file is invisible, not clean.
  echo "-- nothing here" > "$tmp/017_old.up.sql"
  scan_dir "$tmp" >/dev/null
  if [ "$violations" -ne 0 ]; then
    echo "[pii-classify] SELFTEST FAIL — a pre-$GRANDFATHER_BELOW migration was inspected"; fails=1
  fi
  if [ "$checked" -ne 1 ]; then
    echo "[pii-classify] SELFTEST FAIL — grandfathered file changed the inspected count to $checked"; fails=1
  fi

  # ARM 5 — REACH. An empty corpus inspects zero and must not read as clean.
  rm -f "$tmp"/*.up.sql
  scan_dir "$tmp" >/dev/null
  if [ "$checked" -ne 0 ] || [ "$violations" -ne 0 ]; then
    echo "[pii-classify] SELFTEST FAIL — empty corpus gave checked=$checked violations=$violations"; fails=1
  fi
  # ...which is byte-identical to a clean tree, and is exactly why the floor
  # exists. Prove the floor would reject it.
  if [ "$checked" -ge "$MIN_CHECKED" ]; then
    echo "[pii-classify] SELFTEST FAIL — the floor would accept an empty corpus"; fails=1
  fi

  # ARM 6 — the floor is CALIBRATED: live (>0) and not already saturated
  # (< the real corpus), so it can fire without firing today.
  local real
  real=$(scan_dir "$repo_root/migrations/meta" >/dev/null; echo "$checked")
  if [ "$MIN_CHECKED" -le 0 ]; then
    echo "[pii-classify] SELFTEST FAIL — a floor of $MIN_CHECKED can never fire"; fails=1
  fi
  if [ "$MIN_CHECKED" -ge "$real" ]; then
    echo "[pii-classify] SELFTEST FAIL — floor $MIN_CHECKED >= the real corpus ($real): the floor"
    echo "  would pre-empt every arm above it, which is BDR-82"; fails=1
  fi

  if [ "$fails" -ne 0 ]; then
    exit 2
  fi
  echo "[pii-classify] SELFTEST PASS — 6 arm(s): flags one missing tag and all five, passes a"
  echo "  conforming file, still grandfathers pre-$GRANDFATHER_BELOW, reads zero on an empty"
  echo "  corpus, and the reach floor is calibrated live-but-unsaturated against $real real file(s)"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint ;;
  "")         selftest; run_lint ;;
  *)          echo "usage: $0 [--selftest | --lint]"; exit 2 ;;
esac
