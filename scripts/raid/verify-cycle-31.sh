#!/usr/bin/env bash
# verify-cycle-31.sh — L6.H + L6.I + L6.J + L6.K + L6.L Prompt stack (5 DPS).
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 31 scope (5 DPS — XL, L6 layer finalizer):
#
#   DPS 1 (L6.H — 8-section composer template wiring, Q-L6H-1 FAIL):
#     * contracts/prompt/section_renderer.go     — SectionRenderer +
#                                                  SectionValidator +
#                                                  TemplateContract +
#                                                  IntentContracts() +
#                                                  ValidateAgainstContract
#     * contracts/prompt/section_renderer_test.go
#     * contracts/prompt/composer.go            — wires the new validators
#
#   DPS 2 (L6.I — input wrap + canary token):
#     * contracts/prompt/input_wrapper.go        — WrapUserInput + 6-pattern escape
#     * contracts/prompt/canary_token.go         — CanaryToken (128-bit) + detector
#     * contracts/prompt/input_wrapper_test.go
#     * contracts/prompt/canary_token_test.go
#     * contracts/observability/inventory.yaml   — lw_prompt_canary_leak_count
#
#   DPS 3 (L6.J — provider adapter routing, CLAUDE.md gateway invariant):
#     * contracts/prompt/provider_resolver.go    — ProviderResolver + cache
#     * contracts/prompt/provider_router.go      — ProviderAdapter + Router
#     * contracts/prompt/provider_routing_test.go
#     * contracts/service_acl/matrix.yaml        — provider-registry-service-rpcs
#
#   DPS 4 (L6.K — empty templates per intent, Q-L6K-1):
#     * contracts/prompt/templates/<intent>/v1.tmpl + v1.meta.yaml + v1.fixtures/.gitkeep
#       (7 intents: session_turn, npc_reply, canon_check, canon_extraction,
#        admin_triggered, world_seed, summary)
#     * contracts/prompt/templates/registry.yaml
#     * contracts/prompt/template_loader.go
#     * contracts/prompt/template_loader_test.go
#     * scripts/template-fixture-validator.sh
#
#   DPS 5 (L6.L — LLM safety stubs, Q-L6L-1):
#     * contracts/prompt/intent_classifier.go     — IntentClassifier + Noop
#     * contracts/prompt/world_oracle.go          — WorldOracle + Noop
#     * contracts/prompt/injection_defense.go     — InjectionDefense + Noop
#     * contracts/prompt/llm_safety_stubs_test.go
#     * docs/foundation/llm_safety_handoff.md
#
# LOCKED decisions enforced:
#   Q-L6H-1 — Composer FAILS not best-effort (never emit malformed prompt)
#   Q-L6K-1 — Foundation ships EMPTY templates (feature team owns copy)
#   Q-L6L-1 — LLM safety stubs are no-op V1 (fail-closed in safety sub-program)
#   Q-L4D-1 — ProviderPayload opaque (no direct SDK use)
#   CLAUDE.md provider gateway invariant — no direct provider SDK imports

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-31] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-31] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-31] note: $1"; }

# ─────────────────────────────────────────────────────────────────────────
# 1. File presence — DPS 1 (L6.H)
# ─────────────────────────────────────────────────────────────────────────
for f in \
    contracts/prompt/section_renderer.go \
    contracts/prompt/section_renderer_test.go ; do
    [[ -f "$f" ]] || fail "cycle-31 DPS 1 (L6.H) file missing: $f"
done
pass "L6.H files present (section_renderer + tests)"

# ─────────────────────────────────────────────────────────────────────────
# 2. File presence — DPS 2 (L6.I)
# ─────────────────────────────────────────────────────────────────────────
for f in \
    contracts/prompt/input_wrapper.go \
    contracts/prompt/canary_token.go \
    contracts/prompt/input_wrapper_test.go \
    contracts/prompt/canary_token_test.go ; do
    [[ -f "$f" ]] || fail "cycle-31 DPS 2 (L6.I) file missing: $f"
done
pass "L6.I files present (input_wrapper + canary_token + tests)"

# ─────────────────────────────────────────────────────────────────────────
# 3. File presence — DPS 3 (L6.J)
# ─────────────────────────────────────────────────────────────────────────
for f in \
    contracts/prompt/provider_resolver.go \
    contracts/prompt/provider_router.go \
    contracts/prompt/provider_routing_test.go ; do
    [[ -f "$f" ]] || fail "cycle-31 DPS 3 (L6.J) file missing: $f"
done
pass "L6.J files present (provider_resolver + provider_router + tests)"

# ─────────────────────────────────────────────────────────────────────────
# 4. File presence — DPS 4 (L6.K) — 7 intents
# ─────────────────────────────────────────────────────────────────────────
for intent in session_turn npc_reply canon_check canon_extraction admin_triggered world_seed summary ; do
    for f in v1.tmpl v1.meta.yaml ; do
        [[ -f "contracts/prompt/templates/${intent}/${f}" ]] \
            || fail "cycle-31 DPS 4 (L6.K) template missing: contracts/prompt/templates/${intent}/${f}"
    done
    [[ -d "contracts/prompt/templates/${intent}/v1.fixtures" ]] \
        || fail "cycle-31 DPS 4 (L6.K) fixtures dir missing: contracts/prompt/templates/${intent}/v1.fixtures"
done
[[ -f "contracts/prompt/templates/registry.yaml" ]] \
    || fail "cycle-31 DPS 4 (L6.K) registry.yaml missing"
[[ -f "contracts/prompt/template_loader.go" ]] \
    || fail "cycle-31 DPS 4 (L6.K) template_loader.go missing"
[[ -f "scripts/template-fixture-validator.sh" ]] \
    || fail "cycle-31 DPS 4 (L6.K) template-fixture-validator.sh missing"
pass "L6.K files present (7 intent skeletons + registry + loader + lint)"

# ─────────────────────────────────────────────────────────────────────────
# 5. File presence — DPS 5 (L6.L)
# ─────────────────────────────────────────────────────────────────────────
for f in \
    contracts/prompt/intent_classifier.go \
    contracts/prompt/world_oracle.go \
    contracts/prompt/injection_defense.go \
    contracts/prompt/llm_safety_stubs_test.go \
    docs/foundation/llm_safety_handoff.md ; do
    [[ -f "$f" ]] || fail "cycle-31 DPS 5 (L6.L) file missing: $f"
done
pass "L6.L files present (3 stubs + interface-shape test + handoff doc)"

# ─────────────────────────────────────────────────────────────────────────
# 6. Q-L6H-1: Composer FAILS not best-effort
# ─────────────────────────────────────────────────────────────────────────
grep -q 'Q-L6H-1' contracts/prompt/section_renderer.go \
    || fail "Q-L6H-1: section_renderer.go must cite the LOCKED Q-ID"
grep -q 'ValidateAgainstContract' contracts/prompt/composer.go \
    || fail "Q-L6H-1: composer.go must wire ValidateAgainstContract"
grep -q 'SectionValidator' contracts/prompt/composer.go \
    || fail "Q-L6H-1: composer.go must wire SectionValidator"
pass "Q-L6H-1: composer wires per-intent contract + per-section validator (FAIL not best-effort)"

# ─────────────────────────────────────────────────────────────────────────
# 7. Q-L6K-1: empty templates (feature teams own copy)
# ─────────────────────────────────────────────────────────────────────────
for intent in session_turn npc_reply canon_check canon_extraction admin_triggered world_seed summary ; do
    meta="contracts/prompt/templates/${intent}/v1.meta.yaml"
    if ! grep -qE '^status: skeleton([[:space:]]|$|#)' "$meta"; then
        fail "Q-L6K-1: $meta must declare status: skeleton (foundation ships EMPTY)"
    fi
    if ! grep -qE '^owner: llm-logic-subprogram([[:space:]]|$|#)' "$meta"; then
        fail "Q-L6K-1: $meta must declare owner: llm-logic-subprogram"
    fi
done
grep -q 'Q-L6K-1' contracts/prompt/templates/registry.yaml \
    || fail "Q-L6K-1: registry.yaml must cite the LOCKED Q-ID"
pass "Q-L6K-1: all 7 templates marked skeleton + owner: llm-logic-subprogram"

# ─────────────────────────────────────────────────────────────────────────
# 8. Q-L6L-1: no-op stubs (not fail-closed at foundation)
# ─────────────────────────────────────────────────────────────────────────
grep -q 'Q-L6L-1' contracts/prompt/intent_classifier.go \
    || fail "Q-L6L-1: intent_classifier.go must cite the LOCKED Q-ID"
grep -q 'Q-L6L-1' contracts/prompt/world_oracle.go \
    || fail "Q-L6L-1: world_oracle.go must cite the LOCKED Q-ID"
grep -q 'Q-L6L-1' contracts/prompt/injection_defense.go \
    || fail "Q-L6L-1: injection_defense.go must cite the LOCKED Q-ID"
# Ensure no foundation code attempts fail-closed semantics in the stubs
# (the foundation invariant: no-op V1 — fail-closed is downstream).
if grep -qE 'return.*fmt\.Errorf|return.*errors\.New' contracts/prompt/intent_classifier.go ; then
    fail "Q-L6L-1: intent_classifier stub must NOT return errors (no-op V1)"
fi
pass "Q-L6L-1: 3 stubs cited + no-op semantics enforced"

# ─────────────────────────────────────────────────────────────────────────
# 9. CLAUDE.md provider gateway invariant — no direct provider SDK imports
# ─────────────────────────────────────────────────────────────────────────
# Match Go import lines for the banned SDKs only — string literals
# like "openai" in test fixtures are not imports.
if grep -rE '"github.com/(anthropics/anthropic-sdk|sashabaranov/go-openai|openai/openai-go)"' contracts/prompt/ 2>/dev/null; then
    fail "CLAUDE.md gateway invariant: direct provider SDK import detected in contracts/prompt/"
fi
grep -q 'Q-L4D-1' contracts/prompt/provider_router.go \
    || fail "Q-L4D-1: provider_router.go must cite the LOCKED Q-ID (opaque payload)"
grep -q 'CLAUDE.md' contracts/prompt/provider_resolver.go \
    || fail "CLAUDE.md gateway invariant: provider_resolver.go must cite the rule"
pass "CLAUDE.md provider gateway invariant: no direct SDK imports + Q-L4D-1 honored"

# ─────────────────────────────────────────────────────────────────────────
# 10. Canary token entropy ≥ 64 bits (design review criterion)
# ─────────────────────────────────────────────────────────────────────────
# Constant lives in canary_token.go — verify >= 8 bytes (64 bits).
if ! grep -qE 'canaryTokenByteLen = (1[6-9]|[2-9][0-9])' contracts/prompt/canary_token.go ; then
    if ! grep -qE 'canaryTokenByteLen = (8|9|1[0-5])' contracts/prompt/canary_token.go ; then
        fail "canary entropy: canaryTokenByteLen must be >= 8 (64 bits)"
    fi
fi
pass "canary entropy: ≥ 64 bits (canaryTokenByteLen >= 8)"

# ─────────────────────────────────────────────────────────────────────────
# 11. Body-never-stored — canary NOT persisted in PromptAuditEntry
# ─────────────────────────────────────────────────────────────────────────
# CanaryToken / Canary as a field on PromptAuditEntry is a replay-attack
# handle — forbidden per design review.
if grep -qE 'Canary[A-Z]*' contracts/prompt/audit_writer.go ; then
    fail "body-never-stored: PromptAuditEntry must NOT carry a Canary field (replay-attack handle)"
fi
pass "body-never-stored: PromptAuditEntry carries no canary field"

# ─────────────────────────────────────────────────────────────────────────
# 12. Provider cache TTL = 5 minutes (acceptance criterion)
# ─────────────────────────────────────────────────────────────────────────
grep -q 'DefaultProviderTTL = 5 \* time.Minute' contracts/prompt/provider_resolver.go \
    || fail "provider cache: DefaultProviderTTL must equal 5min (matches cycle 1 L1.B consent.go)"
pass "provider cache TTL: 5min (matches cycle 1 L1.B consent.go discipline)"

# ─────────────────────────────────────────────────────────────────────────
# 13. ACL matrix: roleplay-service → provider-registry-service GetProviderConfig
# ─────────────────────────────────────────────────────────────────────────
grep -q 'provider-registry-service-rpcs' contracts/service_acl/matrix.yaml \
    || fail "ACL: provider-registry-service-rpcs entry missing"
# Extract the lines from this entry to the NEXT service entry. Use
# awk skip-first-match pattern to include the trailing rpcs block.
acl_block=$(awk '
    /name: provider-registry-service-rpcs/ {in_block=1; print; next}
    in_block && /^  - name:/ {in_block=0}
    in_block {print}
' contracts/service_acl/matrix.yaml)
echo "$acl_block" | grep -q 'GetProviderConfig:' \
    || fail "ACL: GetProviderConfig RPC must be declared on provider-registry-service-rpcs"
echo "$acl_block" | grep -q 'roleplay-service' \
    || fail "ACL: roleplay-service must be allowed_callers for GetProviderConfig"
echo "$acl_block" | grep -q 'principal_mode: requires_user' \
    || fail "ACL: GetProviderConfig must use principal_mode: requires_user (BYOK user-scoped)"
pass "ACL: roleplay-service → provider-registry-service GetProviderConfig (requires_user)"

# ─────────────────────────────────────────────────────────────────────────
# 14. Inventory: lw_prompt_canary_leak_count declared with shipped_cycle: 31
# ─────────────────────────────────────────────────────────────────────────
grep -qE '^  - name: lw_prompt_canary_leak_count$' contracts/observability/inventory.yaml \
    || fail "inventory.yaml missing lw_prompt_canary_leak_count"
if ! awk '/^  - name: lw_prompt_canary_leak_count$/{p=1} p && /shipped_cycle:/{print; exit}' \
    contracts/observability/inventory.yaml | grep -q 'shipped_cycle: 31'; then
    fail "inventory.yaml: lw_prompt_canary_leak_count must have shipped_cycle: 31"
fi
pass "inventory.yaml: lw_prompt_canary_leak_count declared with shipped_cycle: 31"

# ─────────────────────────────────────────────────────────────────────────
# 15. Go build + test — contracts/prompt (all 5 DPS)
# ─────────────────────────────────────────────────────────────────────────
if command -v go >/dev/null 2>&1; then
    (cd contracts/prompt && go vet ./... && go test ./... > /tmp/c31-prompt.log 2>&1) \
        || { cat /tmp/c31-prompt.log; fail "contracts/prompt vet/test failed"; }
    pass "contracts/prompt go vet + test (all 5 DPS)"
else
    note "go absent — skipping prompt test"
fi

# ─────────────────────────────────────────────────────────────────────────
# 16. template-fixture-validator.sh — must PASS
# ─────────────────────────────────────────────────────────────────────────
if bash scripts/template-fixture-validator.sh > /tmp/c31-tfv.log 2>&1; then
    pass "scripts/template-fixture-validator.sh"
else
    cat /tmp/c31-tfv.log
    fail "scripts/template-fixture-validator.sh"
fi

# ─────────────────────────────────────────────────────────────────────────
# 17. Cycle-21 invariants — contracts/prompt SDK signatures preserved
# ─────────────────────────────────────────────────────────────────────────
grep -q 'AssemblePrompt(ctx context.Context, pc PromptContext, sections SectionMap) (PromptBundle, error)' \
    contracts/prompt/composer.go \
    || fail "cycle-21 invariant: AssemblePrompt signature changed"
grep -q 'type Section string' contracts/prompt/section.go \
    || fail "cycle-21 invariant: Section type changed"
grep -q 'IntentSessionTurn Intent = "session_turn"' contracts/prompt/intent.go \
    || fail "cycle-21 invariant: 7-intent enum changed"
pass "cycle-21 invariants preserved (AssemblePrompt signature + Section + Intent enum)"

# ─────────────────────────────────────────────────────────────────────────
# 18. B5 prod-isolation-lint — no edits to infra/existing-prod/
# ─────────────────────────────────────────────────────────────────────────
if [ -d infra/existing-prod ]; then
    if ! git diff --quiet HEAD -- infra/existing-prod/ 2>/dev/null; then
        fail "B5 prod-isolation: infra/existing-prod/ touched"
    fi
fi
pass "B5 prod-isolation-lint (no existing-prod/ edits)"

# ─────────────────────────────────────────────────────────────────────────
# 19. B6 secret-scan — defense against committed credentials
# ─────────────────────────────────────────────────────────────────────────
banned='AKIA[0-9A-Z]\{16,\}\|AIza[0-9A-Za-z_-]\{35,\}\|-----BEGIN [A-Z ]*PRIVATE KEY-----\|api_key=\|password=.\{8,\}'
for f in \
    contracts/prompt/section_renderer.go \
    contracts/prompt/input_wrapper.go \
    contracts/prompt/canary_token.go \
    contracts/prompt/provider_resolver.go \
    contracts/prompt/provider_router.go \
    contracts/prompt/template_loader.go \
    contracts/prompt/intent_classifier.go \
    contracts/prompt/world_oracle.go \
    contracts/prompt/injection_defense.go \
    docs/foundation/llm_safety_handoff.md ; do
    [[ -f "$f" ]] || continue
    if grep -qE "$banned" "$f"; then
        fail "B6 secret-scan: $f contains banned pattern"
    fi
done
pass "B6 secret-scan: no banned patterns in cycle-31 files"

# ─────────────────────────────────────────────────────────────────────────
# 20. cycle-7 observability-inventory-lint regression
# ─────────────────────────────────────────────────────────────────────────
if [ -x scripts/observability-inventory-lint.sh ]; then
    if scripts/observability-inventory-lint.sh > /tmp/c31-inv-lint.log 2>&1; then
        pass "scripts/observability-inventory-lint.sh"
    else
        cat /tmp/c31-inv-lint.log
        fail "scripts/observability-inventory-lint.sh"
    fi
else
    note "observability-inventory-lint.sh not executable — skipping"
fi

# ─────────────────────────────────────────────────────────────────────────
echo
echo "[verify-cycle-31] all $step checks PASS"
exit 0
