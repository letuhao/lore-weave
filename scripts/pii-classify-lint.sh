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
# Exit 0 = clean; 1 = violations; 2 = misuse.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
violations=0

required_tags=(
  '@pii_sensitivity'
  '@retention_class'
  '@retention_hot'
  '@erasure_method'
  '@legal_basis'
)

# All migrations except those PRE-cycle-7 (1-17 — they pre-date the lint;
# we grandfather them in for now and cycle 8+ commits MUST conform).
for f in "$repo_root"/migrations/meta/*.up.sql; do
  base=$(basename "$f")
  # Skip pre-cycle-7 grandfathered files (numbered 001..017).
  num=$(echo "$base" | grep -oE '^[0-9]+' || echo "")
  if [[ -n "$num" ]] && [[ $((10#$num)) -lt 18 ]]; then
    continue
  fi
  for tag in "${required_tags[@]}"; do
    if ! grep -q -- "$tag" "$f"; then
      echo "[pii-classify] FAIL — $base missing required tag: $tag"
      violations=$((violations + 1))
    fi
  done
done

if [[ $violations -gt 0 ]]; then
  echo "[pii-classify] FAIL — $violations missing tag(s) (S08 §12X.3)"
  exit 1
fi
echo "[pii-classify] PASS"
exit 0
