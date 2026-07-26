# LLM Call Logging Standard

**Status:** ACTIVE (rules) · enforcement partly built — see §Enforcement · **Date:** 2026-07-04
**Governs:** how EVERY provider call — chat (streaming **and** non-streaming), embed, rerank, image, audio/STT/TTS, web-search — records its request, response, cost, and correlation, on every sync/async path. Indexed in [`README.md`](./README.md); current-state + defects in [audit](../plans/2026-07-04-enterprise-hardening-audit.md#area-1--llm--provider-call-logging).

> **Why.** An LLM platform must be able to reconstruct any provider call's input/output for debugging, quality/eval, abuse review, and cost audit. Today three disjoint paths behave differently: async jobs are ~80% instrumented (but read back empty, B3); streaming chat + sync embed/rerank/web-search log **no I/O at all**; and the payload-encryption key is `JWT_SECRET`. This standard makes logging a property of the *shared chokepoint*, not each caller's discipline.

## Rules

- **LOG-1 · One chokepoint, every path.** Every provider call routes through the shared finalize→outbox→usage→`writeUsageLog` plumbing. A provider-invoking handler that logs its own way (or not at all — today: streaming, embed, rerank, web-search) is a defect. Payload logging must be impossible to forget per-handler.
- **LOG-2 · Mandatory fields, every terminal status.** Each call records: `request_id`, **`trace_id`/`turn_id` (required, not optional)**, `owner_user_id`, `operation`, `purpose`, `model_source`+`model_ref`, `provider_kind`, `request_status ∈ {success, provider_error, billing_rejected, cancelled, aborted}`, `input_tokens`, `output_tokens`, `cost_usd`, latency, timestamps, and `campaign_id`/`mcp_key_id` when present — **including on failed/aborted/no-usage-chunk paths** (fixes B2).
- **LOG-3 · Request AND response payloads, every call.** Store the **assembled provider payload** (post-injection system+context prompt, not just the user message) and the completion — for streaming and sync alike (fixes B1, B4). Never a placeholder like `{"stream":true}`.
- **LOG-4 · One storage type-contract, read==write symmetric.** A payload stored as an object is read back as an object. The B3 defect (stored as a JSON *string*, read back as a `map`) is banned; a round-trip decrypt test guards it.
- **LOG-5 · Encrypted at rest on EVERY path, dedicated key.** Payloads are AES-256-GCM (envelope) encrypted everywhere — no plaintext `llm_jobs` row, no plaintext-on-Redis-wire. The KEK is a **dedicated `LLM_PAYLOAD_ENCRYPTION_KEY`** (fail-to-start if missing), **never `JWT_SECRET`**; `payload_encryption_key_ref` names a real, rotatable key version.
- **LOG-6 · Redact before persist.** BYOK secrets/api-keys and configurable PII are scrubbed before storage on all paths.
- **LOG-7 · Retention decoupled + auditable.** Payload retention is an explicit configurable window, independent of the 7-day `llm_jobs` TTL; purge is auditable. A call must not become unrecoverable because an operational row expired (fixes B5).
- **LOG-8 · Correlation end-to-end.** A single `trace_id` is minted at the edge (chat turn / gateway request) and propagated through the SDK to every downstream provider call and every usage row, so one turn → its N LLM calls → their usage rows is a single joinable chain.
- **LOG-9 · Truncation is lossless-referenceable.** If capping, store a content hash + original byte length and keep the stored content valid (round-trippable); truncation must never produce invalid/unparseable stored data.

## Enforcement

| Rule | Status | Gate |
|---|---|---|
| LOG-4 read==write | **to build (P1)** | round-trip decrypt test (write payload → `getUsageLogDetail` → assert equality) — would have caught B3 |
| LOG-1 chokepoint | **to build (P1)** | extend `scripts/ai-provider-gate.py`: a provider-invoking handler not routing through the logging chokepoint fails CI (DEFERRED allowlist for tracked exceptions) — same shape as the provider-gateway gate |
| LOG-2/3 per path | **to build (P1)** | effect-asserting integration test per path (streaming chat, failed job, embed each produce a readable decryptable I/O row) — B1–B4 all pass isolated unit tests today |
| LOG-5 dedicated key | **to build (P1)** | `LLM_PAYLOAD_ENCRYPTION_KEY` required-config (fail-to-start) + a lint asserting the payload cipher key ≠ `JWT_SECRET` |

See [audit P0-1..P0-3 + P1](../plans/2026-07-04-enterprise-hardening-audit.md#consolidated-prioritized-backlog) for the fix-now defects and build order.

## Checklist — a new/changed provider call site
- [ ] Routes through the shared logging chokepoint (LOG-1)
- [ ] Emits all LOG-2 fields on every terminal status, including failures
- [ ] Persists assembled request + response payload (LOG-3), object-typed both ways (LOG-4)
- [ ] Encrypted with the dedicated KEK, redacted (LOG-5/6)
- [ ] Threads the edge `trace_id` (LOG-8)
- [ ] Proven by a round-trip + per-path effect test
