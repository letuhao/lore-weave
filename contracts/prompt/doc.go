// Package prompt — L4.D shared-kernel SDK skeleton for LLM prompt assembly.
//
// # Why a shared SDK
//
// Every service that talks to an LLM (chat-service, knowledge-service,
// translation-service, future roleplay-service) needs the SAME prompt
// assembly contract: same 7 intents, same 8-section template structure,
// same audit trail, same body-never-stored discipline. Re-implementing
// these per service drifts; we ship ONE library and every caller routes
// through it.
//
// This package extends CLAUDE.md's "Provider gateway invariant": no
// service code constructs LLM provider payloads directly. All prompt
// assembly flows through AssemblePrompt / ResolveContext below; the
// returned PromptBundle.ProviderPayload is the only path to a provider
// adapter.
//
// # What this package ships in cycle 21 (L4.D SKELETON)
//
//   - Intent enum (7 variants — session_turn, npc_reply, canon_check,
//     canon_extraction, admin_triggered, world_seed, summary) per S09 §12Y.2
//   - Section enum (8 variants — SYSTEM, WORLD_CANON, SESSION_STATE,
//     ACTOR_CONTEXT, MEMORY, HISTORY, INSTRUCTION, INPUT) per S09 §12Y.4
//   - PromptContext (input) + PromptBundle (output) types
//   - Composer interface — FAIL-not-best-effort (Q-L6H-1)
//   - LLM safety hook interfaces — no-op V1 (Q-L6L-1)
//   - PromptAuditWriter interface bridging to contracts/meta.PromptAudit (cycle 4)
//
// # What is NOT in cycle 21 (deferred to LLM-logic sub-program)
//
//   - Actual template strings (templates/ is EMPTY per Q-L6K-1; feature
//     teams / DF3 own template authoring).
//   - Fail-closed safety policy (Q-L6L-1: hook interfaces present; no-op
//     impls returned by Default*; real injection scanner / canary token
//     / consent gate land in the LLM-safety sub-program).
//   - Provider adapter wiring (cycle 23+ service code consumes
//     PromptBundle.ProviderPayload and calls its registered adapter).
//   - Capability + privacy filter chain (S09 §12Y.5) — interface present
//     via Composer.ResolveContext but no policy logic.
//
// # Q-IDs honored (LOCKED 2026-05-29)
//
//   - Q-L4D-1: ProviderPayload is OPAQUE json.RawMessage in Go,
//     serde_json::Value in Rust. V2+ may introduce typed enum per provider.
//   - Q-L6H-1: Composer FAILS on malformed template / missing required
//     section. Never emits a partial / best-effort prompt (per S09 §12Y).
//   - Q-L6K-1: Foundation ships EMPTY template dir; feature team / DF3 /
//     future LLM-logic sub-program owns template copy.
//   - Q-L6L-1: Safety hooks ship as interfaces with NO-OP default impls.
//     Real fail-closed behavior lands in LLM-safety sub-program.
//   - Q-L4-1: Rust mirror lives at crates/dp-kernel/src/prompt.rs.
//
// # Body-never-stored invariant (S09 §12Y + L1.A §3.5)
//
// The PromptBundle does NOT carry the raw rendered prompt string after
// AssemblePrompt returns. The bundle carries ProviderPayload (opaque
// bytes destined for the provider adapter) + ContextHash (SHA-256 of
// the rendered text, for incident replay). No accessor reveals the
// pre-payload rendered text. This is enforced by struct shape — there
// is no Body / Rendered / PromptText field. The audit writer (cycle 4
// PromptAuditEntry) likewise rejects body bytes at type-level.
package prompt
