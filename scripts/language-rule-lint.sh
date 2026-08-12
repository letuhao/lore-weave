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
# Exit 0 = clean; 1 = violations; 2 = misuse / missing config / selftest failure.
#
# RED-ABILITY PROOF (`GATE-TEETH`, 2026-08-12). `run_lint` takes its config AND
# its services root as parameters, so `--selftest` drives the WHOLE gate against
# a synthetic tree rather than unit-testing the pieces and hoping the wiring
# holds. That choice is deliberate: this gate's two rules (declared-vs-detected,
# and PRR-21 completeness) live in loops, not in functions, and a proof of
# `detect_lang` alone would have said nothing about either.
#
# The floors are the part that did not exist. `${#expected[@]} -eq 0` was
# already guarded — but nothing checked that any service was actually COMPARED.
# A config listing every service as `missing`, or a services root that matched
# nothing, produced zero findings and exit 0: identical to compliance.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

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
# Prints "<svc> <lang>" per row. Extracted so a case can drive it.
parse_config() {
  local in_services=0 line
  while IFS= read -r line; do
    if [[ "$line" =~ ^services: ]]; then in_services=1; continue; fi
    if [[ $in_services -eq 0 ]]; then continue; fi
    # End of services block: a non-indented top-level line
    if [[ "$line" =~ ^[A-Za-z] ]]; then in_services=0; continue; fi
    # match  "  svc: lang  # comment"
    if [[ "$line" =~ ^[[:space:]]+([a-z0-9][a-z0-9-]*[a-z0-9]):[[:space:]]*([a-z]+) ]]; then
      printf '%s %s\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    fi
  done < "$1"
}

run_lint() {
  local config="$1" svc_root="$2"
  local violations=0 compared=0 scanned=0 svc exp dir actual

  if [[ ! -f "$config" ]]; then
    echo "[language-rule] FAIL — contracts/language-rule.yaml missing at $config (Q-L1K-2)"
    exit 2
  fi

  declare -A expected=()
  while read -r svc exp; do
    [[ -n "$svc" ]] && expected["$svc"]="$exp"
  done < <(parse_config "$config")

  if [[ ${#expected[@]} -eq 0 ]]; then
    echo "[language-rule] FAIL — no service mapping parsed from $config"
    exit 2
  fi

  for svc in "${!expected[@]}"; do
    exp="${expected[$svc]}"
    dir="$svc_root/$svc"
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
    # A REAL comparison: a declared language against a detected one.
    compared=$((compared + 1))
    if [[ "$actual" != "$exp" ]]; then
      echo "[language-rule] FAIL — service $svc: expected $exp, detected $actual"
      violations=$((violations + 1))
    fi
  done

  # Completeness (PRR-21): every present service dir with a detected toolchain
  # MUST have a row in the config. Without this, a service added in the wrong
  # language with NO row would slip past I3 enforcement entirely.
  for dir in "$svc_root"/*/; do
    [[ -d "$dir" ]] || continue
    scanned=$((scanned + 1))
    svc="$(basename "$dir")"
    actual=$(detect_lang "$dir")
    [[ "$actual" == "missing" ]] && continue   # empty/unscaffolded dir — not yet a service
    if [[ -z "${expected[$svc]+set}" ]]; then
      echo "[language-rule] FAIL — service $svc present on disk as $actual but has NO row in contracts/language-rule.yaml (PRR-21 completeness)"
      violations=$((violations + 1))
    fi
  done

  # **Violations OUTRANK the floors, and the ordering is the finding.** Written
  # the other way round, a real PRR-16 violation (`missing` declared, present on
  # disk) returned 2 instead of 1: the "zero comparisons" floor fired first and
  # reported a genuine finding as a MISUSE code. A floor exists for the SILENT
  # case — if the gate found something, it demonstrably had a subject.
  if [[ $violations -gt 0 ]]; then
    echo "[language-rule] FAIL — $violations service(s) violate I3 (amended; Q-L1K-2 LOCKED)"
    exit 1
  fi

  # REACH FLOOR — ONE, not two. `${#expected[@]}` above proves the CONFIG was
  # read; this proves the RULE had a subject. A config whose every row says
  # `missing`, or a services root that matches no directory, makes zero real
  # comparisons and prints "PASS" with exit 0 — indistinguishable from a clean
  # tree (`BDR-82`).
  #
  # **There were two here for ten minutes, and the second could never fire.** A
  # `scanned < 1` floor was written alongside this one — but a comparison
  # requires a directory to EXIST under the root, so `scanned == 0` implies
  # `compared == 0` and the walk floor was strictly shadowed by this one. A rule
  # that cannot produce a finding its sibling does not is deletable with the
  # suite green, which is the exact defect this gate is being hardened against.
  # Removed rather than kept as decoration; the count it carried is folded into
  # the message below, where it is still useful diagnostically.
  if [[ $compared -lt 1 ]]; then
    echo "[language-rule] FAIL — made ZERO declared-vs-detected comparisons across"
    echo "                ${#expected[@]} config row(s) and $scanned walked directory(ies);"
    echo "                the I3 rule had no subject, which reads exactly like compliance"
    exit 2
  fi

  echo "[language-rule] PASS — $compared service(s) compared, $scanned directory(ies) walked"
  exit 0
}

# Drive the REAL `run_lint` over a synthetic tree and report its exit code.
_probe() {  # $1 = config text, $2 = tree spec ("svc:marker,svc:marker"), prints rc
  local cfg tree spec svc marker rc=0
  cfg="$(mktemp)"; tree="$(mktemp -d)"
  printf '%s\n' "$1" > "$cfg"
  IFS=',' read -ra spec <<< "$2"
  for entry in "${spec[@]}"; do
    [[ -z "$entry" ]] && continue
    svc="${entry%%:*}"; marker="${entry##*:}"
    mkdir -p "$tree/$svc"
    [[ "$marker" != "none" ]] && : > "$tree/$svc/$marker"
  done
  ( run_lint "$cfg" "$tree" ) > /dev/null 2>&1 || rc=$?
  rm -rf "$cfg" "$tree"
  printf '%s' "$rc"
}

selftest() {
  local rc

  # detect_lang, one case per marker plus the negative and the nested form.
  local d; d="$(mktemp -d)"; trap 'rm -rf "$d"' RETURN
  mkdir -p "$d/a" "$d/b" "$d/c" "$d/e" "$d/f/inner"
  : > "$d/a/Cargo.toml"; : > "$d/b/go.mod"; : > "$d/c/pyproject.toml"
  : > "$d/e/package.json"; : > "$d/f/inner/go.mod"
  for pair in "a rust" "b go" "c python" "e typescript" "f go"; do
    set -- $pair
    if [[ "$(detect_lang "$d/$1")" != "$2" ]]; then
      echo "[language-rule] SELFTEST FAIL — detect_lang($1) gave '$(detect_lang "$d/$1")', want $2"; exit 2
    fi
  done
  mkdir -p "$d/empty"
  if [[ "$(detect_lang "$d/empty")" != "missing" ]]; then
    echo "[language-rule] SELFTEST FAIL — an empty dir is not reported 'missing'"; exit 2
  fi

  # parse_config, including the end-of-block rule.
  local cfg; cfg="$(mktemp)"
  printf 'version: 1\nservices:\n  alpha: rust\n  beta: go   # comment\nother:\n  gamma: python\n' > "$cfg"
  if [[ "$(parse_config "$cfg" | tr '\n' ';')" != "alpha rust;beta go;" ]]; then
    echo "[language-rule] SELFTEST FAIL — parse_config gave '$(parse_config "$cfg" | tr '\n' ';')'"
    echo "                want 'alpha rust;beta go;' — the services block must END at a top-level key"
    exit 2
  fi
  rm -f "$cfg"

  # END TO END, through the real run_lint. Each case is one rule.
  rc=$(_probe $'services:\n  alpha: rust\n' "alpha:Cargo.toml")
  [[ "$rc" == "0" ]] || { echo "[language-rule] SELFTEST FAIL — a matching service did not pass (rc=$rc, cry-wolf)"; exit 2; }

  rc=$(_probe $'services:\n  alpha: rust\n' "alpha:go.mod")
  [[ "$rc" == "1" ]] || { echo "[language-rule] SELFTEST FAIL — a MISMATCHED language did not fail (rc=$rc, vacuous)"; exit 2; }

  rc=$(_probe $'services:\n  alpha: rust\n' "alpha:Cargo.toml,rogue:go.mod")
  [[ "$rc" == "1" ]] || { echo "[language-rule] SELFTEST FAIL — a service with NO config row did not fail (rc=$rc, PRR-21 vacuous)"; exit 2; }

  rc=$(_probe $'services:\n  alpha: missing\n' "alpha:go.mod")
  [[ "$rc" == "1" ]] || { echo "[language-rule] SELFTEST FAIL — a 'missing'-declared service present on disk did not fail (rc=$rc, PRR-16 vacuous)"; exit 2; }

  # THE FLOOR, driven both ways in: an empty root, and a root whose only service
  # is declared `missing` so no comparison is ever made.
  rc=$(_probe $'services:\n  alpha: missing\n' "")
  [[ "$rc" == "2" ]] || { echo "[language-rule] SELFTEST FAIL — an EMPTY services root did not trip the reach floor (rc=$rc)"; exit 2; }

  rc=$(_probe $'services:\n  alpha: missing\n' "alpha:none")
  [[ "$rc" == "2" ]] || { echo "[language-rule] SELFTEST FAIL — a config of only 'missing' rows made zero comparisons and still passed (rc=$rc)"; exit 2; }

  echo "[language-rule] SELFTEST PASS — detect_lang covers 4 markers + nested + empty;"
  echo "                parse_config ends its block at a top-level key; and end-to-end a"
  echo "                mismatch, an unlisted service and a present-but-'missing' service"
  echo "                each FAIL while a matching one passes, with the reach floor tripped"
  echo "                from both an empty root and an all-'missing' config"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint "${2:-$repo_root/contracts/language-rule.yaml}" "$repo_root/services" ;;
  "")         selftest; run_lint "$repo_root/contracts/language-rule.yaml" "$repo_root/services" ;;
  # Back-compat: a bare first argument is the config path.
  *)          run_lint "$1" "$repo_root/services" ;;
esac
