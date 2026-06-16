# Plan — Embedding-queue live-wiring (DEFERRED 059 core)

**Task:** P1 spine — live-wire `services/world-service/src/embedding_queue` against real infra.
**Size:** XL (cross-service substrate, new deps, async conversion, CI, live-smoke).
**Mode:** full human-in-loop (v2.2) + `/review-impl` before commit (spine work).
**Date:** 2026-05-30 · **Branch:** `mmo-rpg/foundation-mega-task`

---

## Scope decision (recorded — user approved "build properly, you decide")

The DEFERRED-059 row framed the provider binding as "a Rust HTTP client". Investigation
showed it is actually a **security-surfaced cross-service feature**: provider-registry-service
has **no embeddings HTTP route and no s2s-auth path** (only user-JWT), and a background worker
has no user token; BYOK billing needs `reality_id → reality_registry.created_by → user_id`
(no existing accessor); and it would be the first `reqwest` usage in the Rust workspace.
Shipping a reqwest client with no real endpoint = mock-only cross-service coverage (the exact
failure mode the project's own lessons warn against).

**THIS TASK (059-core) — fully REAL, live-smokeable, no cross-service-auth risk:**
1. `SqlxEmbeddingWriter` — async `UPDATE npc_session_memory_embedding SET embedding=$1 WHERE npc_id=$2 AND session_id=$3 AND embedding IS NULL` (per-reality pool, search_path-scoped; mirrors `dp-kernel::PgEventStore`). pgvector bind via `pgvector::Vector`.
2. `MetaAuditWriter` — async `INSERT INTO service_to_service_audit (...)` on the meta pool (Q-L1A-3 full audit; append-only role).
3. Async conversion of the IO traits + `Worker` (keep `Queue` sync); existing unit tests → async fakes under `#[tokio::test]`.
4. `cmd`/`main.rs` real wiring: env config, sqlx pools (per-reality + meta), tokio interval ticker → `Worker::process_batch`, `tokio::signal` graceful shutdown. Provider bound to a **fail-closed `NotWiredProvider`** (returns `ProviderError`) until the deferred provider task lands — consistent with admin-cli `NotWiredHandler`.
5. hyper `/healthz` + `/readyz` + `/metrics` (prometheus): `lw_embedding_queue_depth`, `lw_embedding_queue_failures_total`, `lw_embedding_provider_tokens_total`.
6. CI live-smoke: new `worldservice_smoke` per-reality DB (pgvector ext + per_reality 0001–0008) + meta DB (`service_to_service_audit`); gated `cargo test -p world-service --test embedding_live` on `LOREWEAVE_TEST_PG_URL` + `LOREWEAVE_TEST_META_URL`; wired into `foundation-ci.yml` db-smoke.

**DEFERRED (tracked rows, trait seams left ready):**
- `D-EMBEDDING-PROVIDER-WIRING` (NEW) — provider-registry inbound `/internal/v1/embeddings` route + s2s-auth verifier + service_acl edge + `reality→owner` BYOK attribution + Rust `reqwest` `EmbeddingProvider`. Security-surfaced → own task (recommend `/amaw`).
- 059 part (6) enqueue-trigger — **no `ProjectionRunner` exists anywhere** in `crates/`; nothing to hook. Stays under 069/079 domain work.
- 059 part (7) integrity re-enqueue — blocked on `dp_kernel::load_aggregate` (same blocker as integrity-checker).

---

## Facts verified (anti-flaky: confirmed by re-read)

- Table (`0006_projections` + `0008_pgvector_setup`): `npc_session_memory_embedding(npc_id UUID, session_id UUID, content_hash TEXT, embedding VECTOR(1536) NULL, created_at TIMESTAMPTZ)` PK `(npc_id, session_id)`. HNSW cosine index.
- Audit (`migrations/meta/016`): cols `caller_service, callee_service, rpc_name, principal_mode, user_ref_id?, reality_id?, result, latency_ms, created_at_nanos, created_at default now(), payload JSONB`. CHECK: `principal_mode IN ('user','service','system','break_glass')`, `result IN ('ok','error','denied','timeout')`, `created_at_nanos > 1.7e18`, caller/rpc nonempty, latency≥0. `app_service_role`: INSERT+SELECT only.
- Workspace deps pinned: tokio, sqlx 0.8 (postgres,uuid,chrono,json,macros), async-trait, uuid, serde, serde_json, chrono, thiserror, tracing, hyper 1 (http1,server), prometheus 0.13. **reqwest absent**. NEW deps to add at workspace: `pgvector` (sqlx feature), `hyper-util`, `http-body-util`.
- sqlx model: `dp-kernel::PgEventStore` wraps `sqlx::PgPool`, search_path pre-scoped to reality; integration test gated by `LOREWEAVE_TEST_PG_URL`.
- CI: `rust-build-test` (fmt/clippy -D warnings/test/build) + `db-smoke` (compose up → wait-healthy → migrate-test-db → gated cargo smoke → Go smoke scripts). Postgres = `pgvector/pgvector:pg16`.

---

## Audit-event mapping (AuditOutcome → row)

| AuditEvent field | row column |
|---|---|
| (const) | caller_service = `world-service` |
| (const) | callee_service = `provider-registry-service` |
| (const) | rpc_name = `Embed` |
| (const) | principal_mode = `system` (background worker; not a user request) |
| reality_id | reality_id |
| — | user_ref_id = NULL (owner attribution deferred with provider) |
| outcome | result: Ok→`ok`, else→`error` |
| npc_id, session_id, provider, model, tokens, outcome-detail | payload JSONB |
| (clock) | created_at_nanos = unix_nanos |
| (measured) | latency_ms = provider call wall-time |

---

## Build order (TDD, re-VERIFY each)

1. Workspace + world-service `Cargo.toml` deps. `cargo build` green.
2. Async-convert traits + `Worker` + existing unit tests (`#[tokio::test]`). `cargo test -p world-service` green.
3. `live/sqlx_writer.rs` (`SqlxEmbeddingWriter`) + unit-level construction test.
4. `live/audit_writer.rs` (`MetaAuditWriter`).
5. `live/provider.rs` (`NotWiredProvider` fail-closed).
6. `live/worker_loop.rs` (tokio ticker + shutdown) + `live/health.rs` (hyper + prometheus).
7. `cmd/embedding-worker/main.rs` real wiring (env config).
8. `tests/embedding_live.rs` — gated live-smoke (real PG + meta).
9. CI: `migrate-test-db` extension + `smoke-embedding.sh` (or gated cargo test) step in `foundation-ci.yml`; foundation-dev `worldservice_smoke` DB.
10. VERIFY: `cargo fmt/clippy/test --workspace` + live-smoke on foundation-dev (psql-verify embedding UPDATE + audit row). `/review-impl`. POST-REVIEW.

---

## Risks

- **sync→async conversion** touches tested code — mitigate: convert mechanically, keep logic identical, re-run full suite.
- **pgvector crate ↔ sqlx 0.8** compat — verify at step 1; fallback = bind text literal `'[...]'::vector`.
- **search_path scoping** for per-reality writer — set `SET search_path = lw_reality_<id>` per acquire (mirror PgEventStore caller contract) OR connect to the per-reality DB directly in smoke.
- **language-rule-lint** — world-service stays Rust (adding a `cmd/embedding-worker` bin is fine); meta DB writes from Rust use sqlx (no Go).
