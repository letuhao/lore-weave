#!/usr/bin/env bash
# L1.K.10 language-rule-lint.sh — I3 (amended; LOCKED 2026-05-29)
#
# Reads contracts/language-rule.yaml → expected language per services/<name>/.
# Detects actual language by toolchain marker:
#   Cargo.toml → rust ; go.mod → go ; pyproject.toml → python ; package.json → typescript
# FAILS if detected != expected. Special value `missing` = directory empty
# (allowed, NOTE only).
#
# Q-L1K-2 LOCKED: this lint MUST ship in the SAME commit as
# I3_INVARIANT_AMENDMENT.md. Cycle 7 is the commit per the doc §6.
#
# Exit 0 = clean; 1 = violations; 2 = misuse / missing config.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
config="${1:-$repo_root/contracts/language-rule.yaml}"

if [[ ! -f "$config" ]]; then
  echo "[language-rule] FAIL — contracts/language-rule.yaml missing at $config (Q-L1K-2)"
  exit 2
fi

violations=0

# Detect actual language for a service directory.
detect_lang() {
  local dir="$1"
  # Order matters: a service can technically have multiple, but the primary
  # is the OUTERMOST manifest. Check by glob existence.
  if [[ -f "$dir/Cargo.toml" ]]; then echo "rust"; return; fi
  if [[ -f "$dir/go.mod" ]]; then echo "go"; return; fi
  if [[ -f "$dir/pyproject.toml" || -f "$dir/requirements.txt" ]]; then echo "python"; return; fi
  if [[ -f "$dir/package.json" ]]; then echo "typescript"; return; fi
  # Recurse one level — some services nest under cmd/ or src/
  local nested
  for nested in "$dir"/*/; do
    if [[ -d "$nested" ]]; then
      if [[ -f "$nested/Cargo.toml" ]]; then echo "rust"; return; fi
      if [[ -f "$nested/go.mod" ]]; then echo "go"; return; fi
      if [[ -f "$nested/pyproject.toml" || -f "$nested/requirements.txt" ]]; then echo "python"; return; fi
      if [[ -f "$nested/package.json" ]]; then echo "typescript"; return; fi
    fi
  done
  echo "missing"
}

# Parse the YAML — minimal `services:` block, key:value lines under it.
in_services=0
declare -A expected
while IFS= read -r line; do
  if [[ "$line" =~ ^services: ]]; then in_services=1; continue; fi
  if [[ $in_services -eq 0 ]]; then continue; fi
  # End of services block: a non-indented top-level line
  if [[ "$line" =~ ^[A-Za-z] ]]; then in_services=0; continue; fi
  # match  "  svc: lang  # comment"
  if [[ "$line" =~ ^[[:space:]]+([a-z0-9][a-z0-9-]*[a-z0-9]):[[:space:]]*([a-z]+) ]]; then
    expected["${BASH_REMATCH[1]}"]="${BASH_REMATCH[2]}"
  fi
done < "$config"

if [[ ${#expected[@]} -eq 0 ]]; then
  echo "[language-rule] FAIL — no service mapping parsed from $config"
  exit 2
fi

for svc in "${!expected[@]}"; do
  exp="${expected[$svc]}"
  dir="$repo_root/services/$svc"
  if [[ ! -d "$dir" ]]; then
    if [[ "$exp" == "missing" ]]; then
      continue   # OK; declared as missing and is missing
    fi
    echo "[language-rule] NOTE — service $svc expected $exp but directory missing"
    continue
  fi
  actual=$(detect_lang "$dir")
  if [[ "$exp" == "missing" ]]; then
    if [[ "$actual" != "missing" ]]; then
      echo "[language-rule] FAIL — service $svc declared 'missing' but present on disk as $actual; set its language in contracts/language-rule.yaml (PRR-16)"
      violations=$((violations + 1))
    fi
    continue
  fi
  if [[ "$actual" != "$exp" ]]; then
    echo "[language-rule] FAIL — service $svc: expected $exp, detected $actual"
    violations=$((violations + 1))
  fi
done

# Completeness (PRR-21): every present service dir with a detected toolchain
# MUST have a row in the config. Without this, a service added in the wrong
# language with NO row would slip past I3 enforcement entirely.
for dir in "$repo_root"/services/*/; do
  [[ -d "$dir" ]] || continue
  svc="$(basename "$dir")"
  actual=$(detect_lang "$dir")
  [[ "$actual" == "missing" ]] && continue   # empty/unscaffolded dir — not yet a service
  if [[ -z "${expected[$svc]+set}" ]]; then
    echo "[language-rule] FAIL — service $svc present on disk as $actual but has NO row in contracts/language-rule.yaml (PRR-21 completeness)"
    violations=$((violations + 1))
  fi
done

if [[ $violations -gt 0 ]]; then
  echo "[language-rule] FAIL — $violations service(s) violate I3 (amended; Q-L1K-2 LOCKED)"
  exit 1
fi
echo "[language-rule] PASS"
exit 0
