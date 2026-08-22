#!/usr/bin/env bash
# L1.K.13 service-acl-matrix-lint.sh — I11 / S11 §12AA
#
# Every service in services/<name>/ that writes to ANY meta table MUST have an
# entry in contracts/service_acl/matrix.yaml. Heuristic: if a service has
# files importing `contracts/meta` AND has a go.mod (or Cargo.toml), it must
# appear in the matrix.
#
# Exit 0 = clean; 1 = violations; 2 = misuse / selftest failure.
#
# RED-ABILITY PROOF (`GATE-TEETH`). Added 2026-08-12; this gate was one of 43
# CI-invoked gates with no demonstration that it could fail. TWO predicates are
# extracted, because this gate has two and only proving one would be half a
# proof: `has_entry` (is the service in the matrix) and `writes_meta` (does the
# service have a meta-write surface at all). The second is the dangerous one —
# if it stops matching, every service is silently exempt and the gate passes
# over an empty subject, which is `NV-3` and looks exactly like a clean tree.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
matrix="$repo_root/contracts/service_acl/matrix.yaml"

# PREDICATE 1 — membership. $1 = service, $2 = matrix file.
has_entry() {
  grep -qE "^[[:space:]]*-[[:space:]]*name:[[:space:]]*$1[[:space:]]*\$" "$2"
}

# PREDICATE 2 — does this text carry a meta-write surface?
writes_meta() {
  printf '%s' "$1" | grep -qE '(contracts/meta|MetaWrite\(|AttemptStateTransition\()'
}

run_lint() {
  if [[ ! -f "$matrix" ]]; then
    echo "[service-acl-matrix] FAIL — matrix.yaml missing"
    exit 1
  fi

  local violations=0 considered=0 with_meta=0 svc surface
  for svc_dir in "$repo_root"/services/*/; do
    svc=$(basename "$svc_dir")
    # Skip stub dirs (no toolchain file)
    if [[ ! -f "$svc_dir/go.mod" ]] && [[ ! -f "$svc_dir/Cargo.toml" ]] && [[ ! -f "$svc_dir/pyproject.toml" ]]; then
      continue
    fi
    considered=$((considered + 1))
    surface=$(grep -rE '(contracts/meta|MetaWrite\(|AttemptStateTransition\()' "$svc_dir" 2>/dev/null | head -1 || true)
    if [[ -z "$surface" ]]; then
      continue   # no meta write surface; matrix entry not required
    fi
    with_meta=$((with_meta + 1))
    if ! has_entry "$svc" "$matrix"; then
      echo "[service-acl-matrix] FAIL — service $svc imports/calls meta but no ACL matrix entry"
      violations=$((violations + 1))
    fi
  done

  # REACH FLOORS, both of them. `considered` guards the service walk; `with_meta`
  # guards the surface detector. A tree where the detector silently stopped
  # matching produces zero findings and exit 0 — identical to compliance.
  if [[ $considered -lt 1 ]]; then
    echo "[service-acl-matrix] FAIL — ZERO services had a toolchain file; the walk reached nothing"
    exit 2
  fi
  if [[ $with_meta -lt 1 ]]; then
    echo "[service-acl-matrix] FAIL — ZERO of $considered services matched the meta-write"
    echo "                     surface. Either the detector broke or the invariant moved;"
    echo "                     both make every service vacuously exempt"
    exit 2
  fi

  if [[ $violations -gt 0 ]]; then
    echo "[service-acl-matrix] FAIL — $violations service(s) missing ACL entry (I11 / S11 §12AA)"
    exit 1
  fi
  echo "[service-acl-matrix] PASS — $with_meta of $considered service(s) write meta, all in the matrix"
  exit 0
}

selftest() {
  local tmp
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' RETURN

  printf 'services:\n  - name: alpha\n    reads: [x]\n  - name: beta\n' > "$tmp"
  if ! has_entry alpha "$tmp"; then
    echo "[service-acl-matrix] SELFTEST FAIL — did NOT match a service that IS in the matrix (cry-wolf)"; exit 2
  fi
  if has_entry gamma "$tmp"; then
    echo "[service-acl-matrix] SELFTEST FAIL — matched a service NOT in the matrix (vacuous)"; exit 2
  fi
  printf 'services:\n  - name: alpha-extra\n' > "$tmp"
  if has_entry alpha "$tmp"; then
    echo "[service-acl-matrix] SELFTEST FAIL — \`alpha\` matched \`alpha-extra\`; membership is a PREFIX test"; exit 2
  fi

  # PREDICATE 2, all three spellings it claims to recognise plus the negative.
  if ! writes_meta 'import "github.com/x/contracts/meta"'; then
    echo "[service-acl-matrix] SELFTEST FAIL — missed a \`contracts/meta\` import"; exit 2
  fi
  if ! writes_meta 'err := MetaWrite(ctx, row)'; then
    echo "[service-acl-matrix] SELFTEST FAIL — missed a \`MetaWrite(\` call"; exit 2
  fi
  if ! writes_meta 'AttemptStateTransition(ctx, id)'; then
    echo "[service-acl-matrix] SELFTEST FAIL — missed an \`AttemptStateTransition(\` call"; exit 2
  fi
  if writes_meta 'package main
func main() { fmt.Println("no meta here") }'; then
    echo "[service-acl-matrix] SELFTEST FAIL — flagged a file with no meta surface (cry-wolf)"; exit 2
  fi

  echo "[service-acl-matrix] SELFTEST PASS — membership matches a listed service, refuses an"
  echo "                     unlisted one and a prefix; the meta-write detector catches all"
  echo "                     three surfaces and passes a file with none (non-vacuous both ways)"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint ;;
  "")         selftest; run_lint ;;
  *)          echo "usage: $0 [--selftest | --lint]"; exit 2 ;;
esac
