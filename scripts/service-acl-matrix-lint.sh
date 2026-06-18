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
