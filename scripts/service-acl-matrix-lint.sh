#!/usr/bin/env bash
# L1.K.13 service-acl-matrix-lint.sh — I11 / S11 §12AA
#
# Every service in services/<name>/ that writes to ANY meta table MUST have an
# entry in contracts/service_acl/matrix.yaml. Heuristic: if a service has
# files importing `contracts/meta` AND has a go.mod (or Cargo.toml), it must
# appear in the matrix.
#
# Exit 0 = clean; 1 = violations.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
# ── selftest — the red-ability proof (gate-teeth-gate) ──────────────────────
# Same shape as role-grant-validator.sh: a copy of this script under $tmp/scripts/
# makes `repo_root` resolve to the fixture tree, so the production path stays
# unparameterised.
#
# The two exit-0 cases carry the weight. This gate is a HEURISTIC — it skips
# services with no toolchain file and services with no meta surface — and both
# skips are silent. A future edit that dropped either condition would flag every
# stub directory in `services/`, the noise would get the gate muted or its
# condition inverted, and the real check would die by relaxation rather than by
# deletion. These cases pin the skips as intended behaviour, not accidents.
if [[ "${1:-}" == "--selftest" ]]; then
  st_fail=0
  st_run() {  # st_run <expected-exit> <name> <toolchain?> <meta-surface?> <in-matrix?>
    local want="$1" name="$2" toolchain="$3" meta="$4" listed="$5" t rc base
    base="$(basename "$0")"
    t="$(mktemp -d)"
    mkdir -p "$t/scripts" "$t/services/svc-a" "$t/contracts/service_acl"
    cp "$0" "$t/scripts/$base"
    [[ "$toolchain" == "yes" ]] && echo 'module svc-a' > "$t/services/svc-a/go.mod"
    if [[ "$meta" == "yes" ]]; then
      echo 'import "github.com/lw/contracts/meta"' > "$t/services/svc-a/main.go"
    else
      echo 'package main' > "$t/services/svc-a/main.go"
    fi
    { echo 'version: 1'; echo 'services:'; } > "$t/contracts/service_acl/matrix.yaml"
    [[ "$listed" == "yes" ]] && echo '  - name: svc-a' >> "$t/contracts/service_acl/matrix.yaml"
    rc=0
    bash "$t/scripts/$base" >/dev/null 2>&1 || rc=$?
    if [[ "$rc" != "$want" ]]; then
      echo "  FAIL — $name: exit $rc, expected $want"
      st_fail=1
    fi
    rm -rf "$t"
  }

  #      want name                                                       tool meta listed
  st_run 0 "a meta-writing service WITH an ACL entry passes"              yes  yes  yes
  st_run 1 "a meta-writing service with NO ACL entry is refused"          yes  yes  no
  st_run 0 "a stub dir (no go.mod/Cargo.toml/pyproject) is skipped"       no   yes  no
  st_run 0 "a service with no meta write surface needs no entry"          yes  no   no

  if [[ $st_fail -eq 0 ]]; then
    echo "[service-acl-matrix] SELFTEST PASS — a missing ACL entry reds, and both"\
         "documented skips (stub dir, no meta surface) stay green (non-vacuous)"
    exit 0
  fi
  echo "[service-acl-matrix] SELFTEST FAIL"
  exit 1
fi

matrix="$repo_root/contracts/service_acl/matrix.yaml"

if [[ ! -f "$matrix" ]]; then
  echo "[service-acl-matrix] FAIL — matrix.yaml missing"
  exit 1
fi

violations=0

for svc_dir in "$repo_root"/services/*/; do
  svc=$(basename "$svc_dir")
  # Skip stub dirs (no toolchain file)
  if [[ ! -f "$svc_dir/go.mod" ]] && [[ ! -f "$svc_dir/Cargo.toml" ]] && [[ ! -f "$svc_dir/pyproject.toml" ]]; then
    continue
  fi
  # Does service import contracts/meta or call MetaWrite?
  has_meta=$(grep -rE '(contracts/meta|MetaWrite\(|AttemptStateTransition\()' "$svc_dir" 2>/dev/null | head -1 || true)
  if [[ -z "$has_meta" ]]; then
    continue   # no meta write surface; matrix entry not required
  fi
  if ! grep -qE "^[[:space:]]*-[[:space:]]*name:[[:space:]]*${svc}[[:space:]]*$" "$matrix"; then
    echo "[service-acl-matrix] FAIL — service $svc imports/calls meta but no ACL matrix entry"
    violations=$((violations + 1))
  fi
done

if [[ $violations -gt 0 ]]; then
  echo "[service-acl-matrix] FAIL — $violations service(s) missing ACL entry (I11 / S11 §12AA)"
  exit 1
fi
echo "[service-acl-matrix] PASS"
exit 0
