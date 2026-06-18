# Plan — 089 D-EMBEDDING-PROVIDER-WIRING: real BYOK-gateway embedding provider

**Scope (L):** replace the fail-closed `NotWiredProvider` with a real `reqwest`
`EmbeddingProvider` that calls provider-registry's `POST /internal/embed` (the route +
X-Internal-Token s2s auth already exist), using a **platform embedding credential**
(env `user_id` + `model_ref`). Completes the 059 embedding rail's provider path.
**Cadence:** human-in-loop + /review-impl. DB: none.

## Key decision (CLARIFY, user-confirmed)
NPC-memory embedding is **system background work** (audit is already `system_only`;
a reality is a shared world via `book_reality_subscription` with no single owner). So a
**platform-owned BYOK credential** pays — env-configured `user_id` + `model_ref` — NOT
per-end-user attribution. This means the user/model are constant **provider config**, so
**NO trait change** (`embed(&self, text)` unchanged), no reality→user resolver, no Worker
ripple. Per-reality/per-user attribution is deferred (only if a product reason needs it).

## Contract (verified)
- `POST {gateway}/internal/embed?user_id={platform_user}` · header `X-Internal-Token: {secret}`
- body `{"model_source":"user_model","model_ref":"{platform_model_uuid}","texts":[text]}`
- 200 → `{"embeddings":[[f64,...]],"dimension":int,"model":string}` (NO token count → audit tokens=0)
- non-200 → JSON error; mapped to `EmbedResult::ProviderError`.
- Calls OUR gateway (provider-registry), not a vendor SDK → provider-gateway-invariant COMPLIANT.

## Design
- `EmbedProviderConfig { gateway_url, internal_token, user_id, model_ref }` +
  `from_env() -> Option<Self>` (Some iff all of `EMBEDDING_GATEWAY_URL` /
  `EMBEDDING_INTERNAL_TOKEN` / `EMBEDDING_PLATFORM_USER_ID` / `EMBEDDING_MODEL_REF`
  present; None ⇒ keep `NotWiredProvider` — no break for current deploys).
- `HttpEmbeddingProvider` { reqwest::Client, config } impl `EmbeddingProvider`:
  `embed(text)` → POST → `parse_embed_response`. `provider_name()` = "byok-gateway".
- `parse_embed_response(status, body, model_ref) -> (String, EmbedResult)` — **pure**,
  unit-tested without a server: 200+embeddings → `Ok{vector: f64→f32, tokens:0}` (model
  from response); 200 empty/bad-json → `ProviderError`; non-200 → `ProviderError(status+snippet)`.
  Dim is left to the `Worker` guard (it already rejects ≠1536 as `dim_mismatch`).
- Wire in `embedding_worker.rs`: `EmbedProviderConfig::from_env()` → Http vs NotWired; log which.
- `world-service/Cargo.toml`: `reqwest = { workspace = true }` (first reqwest in world-service).

## Files
- `services/world-service/src/embedding_queue/live/http_provider.rs` (NEW — config + provider + pure parse + unit tests)
- `services/world-service/src/embedding_queue/live/mod.rs` (export HttpEmbeddingProvider + EmbedProviderConfig)
- `services/world-service/src/bin/embedding_worker.rs` (provider selection)
- `services/world-service/Cargo.toml` (+ reqwest)
- `docs/deferred/DEFERRED.md` (059 PARTIAL→provider DONE; 089 ADDRESSED; open per-reality-attribution + token-accounting + live-smoke rows) + `docs/sessions/SESSION_PATCH.md`

## Verification
- `cargo build -p world-service` (lib + embedding-worker bin); `cargo test -p world-service embedding`; `cargo fmt`/`clippy`.
- Unit: `parse_embed_response` (ok / empty / non-200 / bad-json / f64→f32); `EmbedProviderConfig::from_env` (all-present → Some; any-missing → None); the worker selection logic.
- **Live smoke deferred** (`D-EMBEDDING-PROVIDER-LIVE-SMOKE`): a real round-trip needs provider-registry up + a seeded platform `user_models` embedding row + an embeddings upstream — not bootable at dev time here. Use the `live infra unavailable` VERIFY token.
- Full 15-lint matrix (new Rust dep + the gateway call — confirm language-rule / lint-no-direct-llm-imports / dep-pinning still green).

## Deferred (opened)
- `D-EMBEDDING-PER-REALITY-ATTRIBUTION` — per-reality/per-user BYOK payer (needs the domain owner model); platform-credential is the V1 model.
- `D-EMBEDDING-TOKEN-ACCOUNTING` — `/internal/embed` returns no token usage; audit `tokens=0`. Surface embedding tokens from the gateway for cost accounting.
- `D-EMBEDDING-PROVIDER-LIVE-SMOKE` — real end-to-end round-trip when the stack + a seeded platform embedding model exist.
