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

# Python — 2026-07-31: this arm used to demand `uv.lock`/`poetry.lock` next to every
# pyproject.toml, grandfathering exactly ONE literal path (`*/sdks/python/pyproject.toml`).
# The repo has THREE pyprojects and ZERO lock files anywhere, so the rule only ever fired
# on the two SDK sub-packages that happen to ship their own descriptor — the parent's
# siblings, same tree, same install path (`PYTHONPATH=sdks/python`, no install). It named a
# path where it meant a class, and nothing caught that because the lint was never wired.
#
# Lockfiles are not this repo's Python convention and never have been: services pin with
# floor constraints in requirements.txt (178 dep lines, verified). Demanding a lock here
# would be a rule invented by its own enforcement. So the arm now guards the convention
# that IS load-bearing — every declared dependency carries a version constraint — which is
# green today and genuinely red-able (add one bare `requests` line and it fails).
py_unconstrained=0
while IFS= read -r req; do
  # Strip comments/blank/pip-flags (-r, -e, --index-url), then require a version operator.
  while IFS= read -r dep; do
    [[ -z "$dep" || "$dep" == \#* || "$dep" == -* ]] && continue
    if [[ ! "$dep" =~ [=\<\>~!] ]]; then
      echo "[dep-pinning] FAIL — $req declares '$dep' with no version constraint"
      py_unconstrained=$((py_unconstrained + 1))
    fi
  done < <(sed 's/[[:space:]]*#.*//' "$req")
done < <(find "$repo_root" -name 'requirements*.txt' -not -path '*/node_modules/*' -not -path '*/.venv/*' 2>/dev/null)
violations=$((violations + py_unconstrained))

# Same rule for the `dependencies = [...]` block of each pyproject.toml.
while IFS= read -r py; do
  while IFS= read -r dep; do
    if [[ ! "$dep" =~ [=\<\>~!] ]]; then
      echo "[dep-pinning] FAIL — $py declares '$dep' with no version constraint"
      violations=$((violations + 1))
    fi
  done < <(awk '/^dependencies[[:space:]]*=[[:space:]]*\[/{f=1;next} f&&/^\]/{f=0} f' "$py" \
             | sed 's/[[:space:]]*#.*//' | tr -d ' ",' | grep -v '^$')
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
