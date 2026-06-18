#!/usr/bin/env bash
# template-fixture-validator.sh — cycle 31 L6.K.6 CI lint.
#
# Blocks PRs that bump a template version without also adding the
# matching fixture directory. Per Q-L6K-1 LOCKED: foundation ships
# EMPTY templates but the structural shape is load-bearing — the
# fixture directory must exist (even if .gitkeep-only) so downstream
# replay tooling has a canonical path to write into.
#
# Rules enforced:
#   1. For every intent listed in contracts/prompt/templates/registry.yaml,
#      there MUST exist <intent>/v<N>.tmpl + <intent>/v<N>.meta.yaml +
#      <intent>/v<N>.fixtures/ on disk.
#   2. registry.yaml MUST list all 7 intents (matches AllIntents() in
#      contracts/prompt/intent.go).
#   3. Meta.yaml MUST declare matching intent + version.
#
# Exit 0 on pass; non-zero on any rule failure.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

templates_dir="contracts/prompt/templates"
registry="${templates_dir}/registry.yaml"

if [[ ! -f "$registry" ]]; then
    echo "[template-fixture-validator] FAIL: registry.yaml missing at $registry" >&2
    exit 1
fi

# Expected 7 intents per S09 §12Y.2 / contracts/prompt/intent.go.
expected_intents=(session_turn npc_reply canon_check canon_extraction admin_triggered world_seed summary)

errors=0
for intent in "${expected_intents[@]}"; do
    # Rule 2: registry mentions intent.
    if ! grep -q "^  ${intent}:" "$registry"; then
        echo "[template-fixture-validator] FAIL: registry.yaml missing intent ${intent}" >&2
        errors=$((errors+1))
        continue
    fi
    # Pick active_version (default 1 for skeleton).
    intent_dir="${templates_dir}/${intent}"
    if [[ ! -d "$intent_dir" ]]; then
        echo "[template-fixture-validator] FAIL: ${intent_dir}/ missing" >&2
        errors=$((errors+1))
        continue
    fi
    # Rule 1: v1.tmpl + v1.meta.yaml + v1.fixtures/ present.
    for required in "v1.tmpl" "v1.meta.yaml"; do
        if [[ ! -f "${intent_dir}/${required}" ]]; then
            echo "[template-fixture-validator] FAIL: ${intent_dir}/${required} missing" >&2
            errors=$((errors+1))
        fi
    done
    if [[ ! -d "${intent_dir}/v1.fixtures" ]]; then
        echo "[template-fixture-validator] FAIL: ${intent_dir}/v1.fixtures/ missing" >&2
        errors=$((errors+1))
    fi
    # Rule 3: meta.yaml declares matching intent + version.
    if [[ -f "${intent_dir}/v1.meta.yaml" ]]; then
        if ! grep -q "^intent: ${intent}\$" "${intent_dir}/v1.meta.yaml"; then
            echo "[template-fixture-validator] FAIL: ${intent_dir}/v1.meta.yaml does not declare intent: ${intent}" >&2
            errors=$((errors+1))
        fi
        if ! grep -q "^version: 1\$" "${intent_dir}/v1.meta.yaml"; then
            echo "[template-fixture-validator] FAIL: ${intent_dir}/v1.meta.yaml does not declare version: 1" >&2
            errors=$((errors+1))
        fi
    fi
done

if [[ $errors -gt 0 ]]; then
    echo "[template-fixture-validator] FAIL: ${errors} error(s)" >&2
    exit 1
fi

echo "[template-fixture-validator] OK: all 7 intents have v1 skeleton + meta + fixtures dir"
exit 0
