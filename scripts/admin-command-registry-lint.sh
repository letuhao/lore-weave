#!/usr/bin/env bash
# admin-command-registry-lint.sh — R13 §12L.5 CI gate.
#
# Blocks ad-hoc SQL or HTTP admin endpoints that sit OUTSIDE the
# contracts/admin/registry framework. Every admin-class action MUST be
# declared in a registry/*.yaml so it gets:
#   * audited via admin_action_audit (framework hook)
#   * tier-classified for dry-run + double-approval gating
#   * surfaced in `admin --help` for SRE discoverability
#
# Heuristic (V1):
#   * grep services/ for `// ADMIN-SQL:` or `// ADMIN-RPC:` markers — these
#     MUST appear in contracts/admin/registry/*.yaml as command handlers.
#   * grep services/ for `func (h *AdminHandler) ` style admin route
#     handlers — every such handler name MUST be referenced as a `handler:`
#     in some registry yaml file.
#
# Soft heuristic — false positives are possible. Add `// admin-registry-lint:exempt`
# next to the offending line to suppress.
#
# Exit codes:
#   0  pass
#   1  one or more admin-class entry points outside the registry
#   2  CLI usage error

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

REG_DIR="contracts/admin/registry"

if [[ ! -d "$REG_DIR" ]]; then
    echo "[admin-registry-lint] FAIL: $REG_DIR not found — run from repo root" >&2
    exit 2
fi

# Collect handler names from registry YAMLs.
mapfile -t handlers < <(grep -hE '^\s*handler:\s*' "$REG_DIR"/*.yaml 2>/dev/null \
    | sed -E 's/^\s*handler:\s*//' \
    | tr -d '"' \
    | sort -u)

if [[ ${#handlers[@]} -eq 0 ]]; then
    echo "[admin-registry-lint] FAIL: no handler: keys found in $REG_DIR" >&2
    exit 1
fi

echo "[admin-registry-lint] info: registry declares ${#handlers[@]} handlers"

# Build/vendor trees are excluded from BOTH scans below. An admin marker is a thing an author
# wrote in this repo's source; it is never inside a dependency or a compiler output, so this
# narrows nothing real. It is a LATENCY fix, and the latency was not cosmetic: the two bare
# `grep -R services/` calls walked every `services/*/node_modules` and every Rust
# `services/*/target`, which on a developer machine took this gate from 5s to 134s after the
# 2026-08-02 merge added four Rust services — and once to a 900s TIMEOUT under
# `gate-wiring-gate --run-all`, i.e. a red gate for a reason that has nothing to do with what
# it checks. CI never saw it because a fresh checkout has neither directory.
SKIP=(--exclude-dir=node_modules --exclude-dir=target --exclude-dir=dist
      --exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=.pytest_cache)

# Scan for ADMIN-SQL / ADMIN-RPC markers.
marker_hits=$(grep -RnE "${SKIP[@]}" '//\s*ADMIN-(SQL|RPC):' services/ 2>/dev/null \
    | grep -vE '//\s*admin-registry-lint:exempt' \
    || true)
if [[ -n "$marker_hits" ]]; then
    # For each marker, the named handler MUST appear in the registry handler set.
    fail=0
    while IFS= read -r line; do
        ref=$(echo "$line" | sed -nE 's|.*//\s*ADMIN-(SQL\|RPC):\s*([A-Za-z0-9_]+).*|\2|p')
        if [[ -z "$ref" ]]; then continue; fi
        found=0
        for h in "${handlers[@]}"; do
            if [[ "$h" == "$ref" ]]; then found=1; break; fi
        done
        if [[ $found -eq 0 ]]; then
            echo "[admin-registry-lint] FAIL: $line"
            echo "    handler $ref not in $REG_DIR — register it or add // admin-registry-lint:exempt"
            fail=1
        fi
    done <<< "$marker_hits"
    if [[ $fail -ne 0 ]]; then
        exit 1
    fi
fi

# Scan for AdminHandler-style methods.
admin_handlers=$(grep -RnE "${SKIP[@]}" 'func\s+\(\w+\s+\*AdminHandler\)\s+\w+' services/ 2>/dev/null \
    | grep -vE '//\s*admin-registry-lint:exempt' \
    || true)
if [[ -n "$admin_handlers" ]]; then
    fail=0
    while IFS= read -r line; do
        method=$(echo "$line" | sed -nE 's|.*func\s+\(\w+\s+\*AdminHandler\)\s+([A-Za-z0-9_]+).*|\1|p')
        if [[ -z "$method" ]]; then continue; fi
        # Convert exported method name to lower-camel for handler comparison.
        lc=$(echo "${method:0:1}" | tr 'A-Z' 'a-z')${method:1}
        found=0
        for h in "${handlers[@]}"; do
            if [[ "$h" == "$method" || "$h" == "$lc" ]]; then found=1; break; fi
        done
        if [[ $found -eq 0 ]]; then
            echo "[admin-registry-lint] WARN: AdminHandler method $method not in registry"
            echo "    location: $line"
            # WARN, not fail — false positives common for shared HTTP plumbing.
        fi
    done <<< "$admin_handlers"
fi

echo "[admin-registry-lint] PASS: ${#handlers[@]} registry handlers; no orphan ADMIN-SQL/RPC markers"
exit 0
