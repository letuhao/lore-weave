# Cycle 1: Rerank registration (FE)

## 🎯 TL;DR (30 seconds — TOP critical info)
Add **rerank** as a first-class capability in the model **register** form so a user can hand-register a rerank model and have it show up everywhere a rerank model is selectable. Extend `CapabilityFlags` to offer rerank, ensure `RerankModelPicker` matches the canonical flag from C0, and add **per-capability "0 found"** feedback so an empty picker explains itself instead of silently showing nothing.
- **Scope:** FE-only. No provider-registry inventory parsing (that's C2) — this is the manual-registration + picker-match + empty-state slice.
- **Acceptance gate:** `scripts/raid/verify-cycle-1.sh` exits 0 (this cycle's runner creates that script).
- **Top 3 LOCKED decisions consumed:** Scope-LOCKED (rerank = optional grounding-quality, not a write-block), G4 (Playwright screenshot smoke), provider-registry rail (no hardcoded model names; rerank is a BYOK provider-registry credential).
- **DPS count:** 2
- **Estimated wall time:** ~2 hours

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C0
- Files expected to exist: `frontend/src/features/settings/CapabilityFlags.tsx` (rerank token reconciled in C0), the `RerankModelPicker` component.

## Scope (IN)
- Add **rerank** to the register form (`CapabilityFlags`) so a model can be registered with the rerank capability flag set.
- `RerankModelPicker` matches the canonical `rerank` flag (the C0 reconcile) — a registered rerank model appears in the picker and in the campaign-role selector.
- **Per-capability "0 found" feedback** — when no model carries the selected capability, the picker shows an explanatory empty state (with an `AddModelCta` hook from C0), not a blank dropdown. (BL-1)
- `scripts/raid/verify-cycle-1.sh` (acceptance gate) + a Playwright screenshot of: hand-register a rerank model → it appears in the picker + campaign role.

## Scope (OUT — explicitly)
- NO provider-registry inventory sync / Cohere-shape `/v1/models` parsing — that is C2.
- NO rerank connection-test / `/v1/rerank` round-trip — that is C3.
- NO hardcoded model names or per-service rerank URL/token env — rerank resolves via provider-registry BYOK credentials (CLAUDE.md provider invariant).
- NO BE changes.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `frontend` unit tests for the rerank capability option + the picker match + the "0 found" empty state.
- Lints pass: `frontend` eslint/tsc clean on touched files.
- Integration smoke (FE-only, Playwright screenshot per G4): hand-register a rerank model → it shows in `RerankModelPicker` and in the campaign role selector; an empty capability shows the "0 found" feedback. Screenshot filed with this brief.

## DPS parallelism plan
- DPS 1: `CapabilityFlags` rerank option + `RerankModelPicker` match against the canonical flag (return budget: 1500 tokens summary).
- DPS 2: per-capability "0 found" empty-state component + `AddModelCta` wire-in.
- Serial tail: `verify-cycle-1.sh` + Playwright screenshot once both DPS land.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- A literal model name baked into the register form or picker → provider-registry-rail violation (rerank model identity must come from the user's BYOK credential, never a hardcoded string).
- "0 found" feedback that triggers on loading (false empty) vs genuine zero-results — check the loading/empty distinction.
- Picker that matches `reranker` while the flag stores `rerank` (or vice-versa) — the C0 reconcile must hold; assert one canonical token end-to-end.
- Conditional-unmount of the picker on capability switch (CLAUDE.md FE rule) — use internal branching.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (rerank in register form, picker match, "0 found" feedback).
- No OUT items touched (no inventory sync, no connection test, no BE, no hardcoded models).
- All acceptance criteria met; `verify-cycle-1.sh` exits 0 with a filed Playwright screenshot.
- Cross-cycle invariant: rerank token stays canonical (C0); picker is ready for C2's discovered models.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle row: [CYCLE_DECOMPOSITION.md](../../plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md) C1.
- LOCKED: [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-06-13-creation-unblock/OPEN_QUESTIONS_LOCKED.md) §Scope (rerank optional), §G4, §Architecture-review (rerank via provider-registry BYOK).
- Source spec: [knowledge-service-standalone-ux-review](../../specs/2026-06-13-knowledge-service-standalone-ux-review.md). BL-1 origin per the decomposition Sources list (knowledge-fe-ux-qol-gaps).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Provider rail LOCKED:** rerank is a BYOK provider-registry credential — resolve via provider-registry; NO hardcoded model names, NO per-service rerank URL/token env.
- 🔴 **Scope LOCKED:** rerank is optional grounding-quality; this cycle is registration + picker + empty-state only — discovery (C2) and connection-test (C3) are separate.
- 🔴 **G4 LOCKED:** FE VERIFY = a real Playwright screenshot (test account `claude-test@loreweave.dev`).
- 🔴 **Acceptance MUST include:** the "0 found" per-capability feedback — easiest item to forget; the picker must explain an empty result, not show a blank.
- 🔴 **Do NOT touch:** provider-registry inventory parsing, `/v1/rerank` verify, or any BE — C2/C3 own those.
- 🔴 **Fresh session reminder:** new `/raid 1` invocation; no carry-over. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
