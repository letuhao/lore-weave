#!/usr/bin/env bash
# scripts/deploy-class-check.sh — L7.K.6 (RAID cycle 38)
#
# SR05 §12AH.2 deploy classification CI lint. Reads the PR's changed-file list
# + a few explicit signals and emits the deploy class (patch|minor|major|
# emergency). If a declared class (--declared) mismatches the detected class it
# fails the build (e.g. a migration file in a PR labelled `patch`).
#
# This is the shell sibling of services/canary-controller/internal/deployclass
# (one authoritative ruleset, two consumers). Classification rules:
#
#   emergency — `emergency` label AND (--incident-id OR --security-finding-id)
#   major     — >1 service touched OR any contracts/* change OR --contract-breaking
#               OR --schema-breaking
#   minor     — single service WITH a migration file OR config change
#               OR a contracts/api/* change
#   patch     — everything else
#
# Exit codes:
#   0 — class detected (printed to stdout); if --declared given, it matched
#   1 — declared/detected class mismatch (CI fail)
#   2 — usage error
#
# Flags:
#   --files <file>          newline-delimited changed-file list (default: git diff)
#   --base <ref>            base ref for `git diff --name-only <base>...HEAD`
#   --declared <class>      assert the detected class equals this (else exit 1)
#   --emergency-label       PR carries the `emergency` label
#   --incident-id <id>      emergency justification
#   --security-finding-id <id>
#   --contract-breaking     upstream contract-diff lint flagged a break
#   --schema-breaking       upstream migration lint flagged a break
#
# Environment:
#   LW_DEPLOY_FILES_FIXTURE  path to a changed-file fixture (test injection)

set -euo pipefail

FILES_SRC=""
BASE_REF=""
DECLARED=""
EMERGENCY_LABEL=0
INCIDENT_ID=""
SECURITY_FINDING_ID=""
CONTRACT_BREAKING=0
SCHEMA_BREAKING=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --files) FILES_SRC="$2"; shift 2 ;;
        --base) BASE_REF="$2"; shift 2 ;;
        --declared) DECLARED="$2"; shift 2 ;;
        --emergency-label) EMERGENCY_LABEL=1; shift ;;
        --incident-id) INCIDENT_ID="$2"; shift 2 ;;
        --security-finding-id) SECURITY_FINDING_ID="$2"; shift 2 ;;
        --contract-breaking) CONTRACT_BREAKING=1; shift ;;
        --schema-breaking) SCHEMA_BREAKING=1; shift ;;
        --help|-h) sed -n '2,38p' "$0"; exit 0 ;;
        *) echo "[deploy-class-check] unknown arg: $1" >&2; exit 2 ;;
    esac
done

# Resolve the changed-file list.
if [[ -n "${LW_DEPLOY_FILES_FIXTURE:-}" && -f "${LW_DEPLOY_FILES_FIXTURE}" ]]; then
    changed="$(cat "${LW_DEPLOY_FILES_FIXTURE}")"
elif [[ -n "$FILES_SRC" && -f "$FILES_SRC" ]]; then
    changed="$(cat "$FILES_SRC")"
elif [[ -n "$BASE_REF" ]]; then
    changed="$(git diff --name-only "${BASE_REF}...HEAD")"
else
    # Default: changes vs HEAD (staged + unstaged), best-effort.
    changed="$(git diff --name-only HEAD 2>/dev/null || true)"
fi

# Normalise: drop blank lines + Windows CR + backslashes.
changed="$(printf '%s\n' "$changed" | tr '\\' '/' | tr -d '\r' | sed '/^$/d')"

# Derived facts.
services="$(printf '%s\n' "$changed" \
    | grep -E '^services/[^/]+/' \
    | sed -E 's#^services/([^/]+)/.*#\1#' \
    | sort -u || true)"
service_count=0
[[ -n "$services" ]] && service_count="$(printf '%s\n' "$services" | sed '/^$/d' | wc -l | tr -d ' ')"

# contracts/api/* is an endpoint change (→ minor if non-breaking); any other
# contracts/* is an internal wire-shape change (→ major). Mirrors deployclass.
has_contract_api=0
printf '%s\n' "$changed" | grep -qE '^contracts/api/' && has_contract_api=1
has_contract_nonapi=0
printf '%s\n' "$changed" | grep -E '^contracts/' | grep -qvE '^contracts/api/' && has_contract_nonapi=1
has_migration=0
printf '%s\n' "$changed" | grep -qE '^migrations/.*\.sql$' && has_migration=1
has_config=0
printf '%s\n' "$changed" | grep -qE '(^config/|/config/)' && has_config=1

# Classification (mirrors deployclass.Classify decision order).
class="patch"
if [[ "$EMERGENCY_LABEL" -eq 1 && ( -n "$INCIDENT_ID" || -n "$SECURITY_FINDING_ID" ) ]]; then
    class="emergency"
elif [[ "$service_count" -gt 1 || "$CONTRACT_BREAKING" -eq 1 || "$SCHEMA_BREAKING" -eq 1 || "$has_contract_nonapi" -eq 1 ]]; then
    class="major"
elif [[ "$has_migration" -eq 1 || "$has_config" -eq 1 || "$has_contract_api" -eq 1 ]]; then
    class="minor"
else
    class="patch"
fi

echo "[deploy-class-check] services_touched=$service_count contract_api=$has_contract_api contract_internal=$has_contract_nonapi migration=$has_migration config=$has_config → class=$class"

if [[ -n "$DECLARED" ]]; then
    if [[ "$DECLARED" != "$class" ]]; then
        echo "[deploy-class-check] BLOCKED: PR declared class '$DECLARED' but detected '$class' (§12AH.2 mismatch)" >&2
        exit 1
    fi
    echo "[deploy-class-check] declared class '$DECLARED' matches detected"
fi

# Emit the bare class on the last stdout line for programmatic capture.
echo "$class"
exit 0
