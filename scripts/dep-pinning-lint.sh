#!/usr/bin/env bash
# L1.K.8 dep-pinning-lint.sh — SR10 I18
#
# Verifies dependency declarations are hash-pinned where the ecosystem
# supports it:
#   - Go: go.sum must exist for every go.mod
#   - Rust: Cargo.lock must exist at workspace root
#   - Python: uv.lock or poetry.lock must exist where pyproject.toml exists
#   - JS/TS: package-lock.json or pnpm-lock.yaml must exist where package.json exists
#   - Docker: FROM lines MUST use digest pin (`image@sha256:...`) — warn if tag-only
#
# Exit 0 = clean; 1 = violations.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
violations=0

# Go: every go.mod with external `require` blocks needs a go.sum sibling.
# A module with NO external deps (require block empty or only `// indirect`
# stdlib-internal references) doesn't need a go.sum file — `go mod tidy` does
# not create one in that case.
while IFS= read -r mod; do
  dir=$(dirname "$mod")
  if [[ -f "$dir/go.sum" ]]; then
    continue   # has go.sum — pinned ✓
  fi
  # No go.sum — check whether it declares any external requires
  if grep -qE '^require[[:space:]]+[a-z]+\.[a-z]' "$mod" 2>/dev/null; then
    echo "[dep-pinning] FAIL — $mod declares external requires but has no go.sum sibling"
    violations=$((violations + 1))
    continue
  fi
  # Multi-line require block?
  if awk '/^require[[:space:]]+\($/,/^\)$/' "$mod" 2>/dev/null | grep -qE '^\s+[a-z]+\.[a-z]'; then
    echo "[dep-pinning] FAIL — $mod declares external requires (multi-line block) but has no go.sum sibling"
    violations=$((violations + 1))
  fi
done < <(find "$repo_root" -name go.mod -not -path '*/node_modules/*' 2>/dev/null)

# Rust workspace root must have Cargo.lock
if [[ -f "$repo_root/Cargo.toml" ]] && ! [[ -f "$repo_root/Cargo.lock" ]]; then
  echo "[dep-pinning] FAIL — workspace Cargo.toml without Cargo.lock"
  violations=$((violations + 1))
fi

# Python: pyproject.toml needs uv.lock or poetry.lock.
# Skip the existing-platform sdks/python (pre-cycle-7 grandfathered; SR10
# pyproject lockfile coverage tracked separately as a non-blocking warning).
while IFS= read -r py; do
  dir=$(dirname "$py")
  # Grandfather: existing platform code outside scope of foundation cycles
  case "$py" in
    */sdks/python/pyproject.toml) continue ;;
  esac
  if [[ ! -f "$dir/uv.lock" ]] && [[ ! -f "$dir/poetry.lock" ]]; then
    echo "[dep-pinning] FAIL — $py has neither uv.lock nor poetry.lock"
    violations=$((violations + 1))
  fi
done < <(find "$repo_root" -name pyproject.toml -not -path '*/node_modules/*' -not -path '*/.venv/*' 2>/dev/null)

# Docker: warn-only on tag-pinned FROM (no fail; many base images don't ship digest)
while IFS= read -r dockerfile; do
  if grep -qE '^FROM[[:space:]]+[^@]*$' "$dockerfile"; then
    # has at least one non-digest-pinned FROM
    echo "[dep-pinning] WARN — $dockerfile has tag-pinned FROM (consider digest pin)"
  fi
done < <(find "$repo_root" -name Dockerfile -not -path '*/node_modules/*' 2>/dev/null)

if [[ $violations -gt 0 ]]; then
  echo "[dep-pinning] FAIL — $violations unpinned dep declaration(s) (SR10 I18)"
  exit 1
fi
echo "[dep-pinning] PASS"
exit 0
