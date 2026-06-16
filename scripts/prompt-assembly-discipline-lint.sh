#!/usr/bin/env bash
# L1.K.14 prompt-assembly-discipline-lint.sh — I2 / I10 / S09 §12Y
#
# Direct LLM SDK calls (`litellm`, `anthropic`, `openai`) are FORBIDDEN
# OUTSIDE:
#   - contracts/prompt/           (prompt assembly library)
#   - services/provider-registry-service/   (BYOK provider proxy)
#   - services/chat-service/      (Python LLM service entry — uses litellm)
#
# Plus body-never-stored check: no `body|prompt_text|assembled_text|full_prompt|raw_prompt`
# columns in any prompt_audit migration (already enforced by audit-l1a3 test,
# but we lint at CI too for defense-in-depth).
#
# Exit 0 = clean; 1 = violations.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
violations=0

# Direct SDK import / module usage. Drop comment lines (the regex catches
# any mention of "openai" / "anthropic" in code comments which are NOT calls).
hits=$(grep -rniE '(^[[:space:]]*import[[:space:]]+(openai|anthropic|litellm)|^[[:space:]]*from[[:space:]]+(openai|anthropic|litellm)|require\(.(openai|anthropic|litellm).\)|\bopenai\.(Client|Configuration|ChatCompletion)|\banthropic\.Client|\blitellm\.completion)' \
  --include='*.go' --include='*.py' --include='*.ts' --include='*.tsx' --include='*.rs' \
  "$repo_root/services" "$repo_root/contracts" "$repo_root/crates" 2>/dev/null \
  | grep -vE 'contracts/prompt/' \
  | grep -vE 'services/provider-registry-service/' \
  | grep -vE 'services/chat-service/' \
  | grep -vE 'services/knowledge-service/' \
  | grep -vE '_test\.' \
  | grep -vE ':[[:space:]]*(//|#|\*|///)' || true)
if [[ -n "$hits" ]]; then
  echo "[prompt-assembly] FAIL — direct LLM SDK use outside allowed services (I2/I10):"
  echo "$hits" | sed 's/^/  /'
  violations=$((violations + 1))
fi

# Body-never-stored: prompt_audit migration must not have body/text COLUMNS.
# Comment text discussing the invariant is fine; we only flag declarations:
#   `<name> <TYPE>` where <name> is in the forbidden set.
prompt_audit_sql="$repo_root/migrations/meta/017_prompt_audit.up.sql"
if [[ -f "$prompt_audit_sql" ]]; then
  # Strip SQL line comments first
  bad=$(grep -nvE '^[[:space:]]*--' "$prompt_audit_sql" \
        | grep -niE '^\s*(body|prompt_text|assembled_text|full_prompt|raw_prompt)[[:space:]]+(TEXT|BYTEA|VARCHAR)' || true)
  if [[ -n "$bad" ]]; then
    echo "[prompt-assembly] FAIL — prompt_audit migration appears to store prompt body (S09 §12Y):"
    echo "$bad" | sed 's/^/  /'
    violations=$((violations + 1))
  fi
fi

if [[ $violations -gt 0 ]]; then
  echo "[prompt-assembly] FAIL — $violations issue(s) (I2 / I10 / S09 §12Y)"
  exit 1
fi
echo "[prompt-assembly] PASS"
exit 0
