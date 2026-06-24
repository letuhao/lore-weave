# Plan — roleplay-service (lean Rust foundation) v1

- **Date:** 2026-06-24
- **Spec:** [docs/specs/2026-06-24-roleplay-scripted-acting.md](../specs/2026-06-24-roleplay-scripted-acting.md)
- **Detailed design:** [docs/specs/2026-06-24-roleplay-service-detailed-design.md](../specs/2026-06-24-roleplay-service-detailed-design.md)
- **Size:** **XL** — new Rust service + new shared crate + cross-service contract (chat-service) + gateway + FE re-point + a data/feature re-home. Continuous run, commit at each milestone risk boundary.
- **Strategy:** infra gate first (kit + scaffold + gateway), then the domain (scripts + start), then re-point the FE, then cut over. Keep the working interview feature LIVE on chat-service until the Rust path re-passes the M7 browser smoke (no flag-day). `/review-impl` at the new service boundary.
- **Checkpoint cadence:** commit at each R-milestone; **POST-REVIEW (human)** at R3 (cutover). Cross-service **live-smoke** at R1 (start orchestration) + R2 (browser smoke).

## Decisions locked (CLARIFY/DESIGN closed)
Rust now (M1–M7 was the spike); lean scope (no world-model/sharding/NPC-scale infra); **System + Per-user tiers only** (book-tier + grant client deferred); actor-memory = `rp_memory` (charter authoritative, executive deferred); turn loop + voice + debrief **reused from chat-service**; the HTTP infra is a shared **`crates/service-http`** kit (roleplay = first consumer; tilemap/world migrate opportunistically).

---

## R0 — Infra gate (kit + scaffold + gateway) · *no behavior*

**`crates/service-http`** (the standardization sweep — §0.5 of the DDD):
- `serve()` + graceful shutdown; `health::routes()` (`/livez`/`/readyz` DB-aware/`/metrics`); `ProblemDetails` (RFC 7807 **+ `message`** for FE-readability); `require_internal_token`; **`require_user`** (JWT HS256 → `Extension<UserId>`); `trace` layer + `init_tracing()` (JSON logs w/ service+trace_id, `X-Trace-Id` in/out); `metrics` layer; `config::require_env`; `db::init(url, migrator)`.
- New workspace deps: `jsonwebtoken = "9"`, `chrono` (+ `sqlx` `chrono` feature). Register `crates/service-http` as a workspace member.
- **Tests:** `require_user` (valid / expired / bad-sig / non-uuid-sub → 401); `require_internal_token`; `ProblemDetails` serializes `message`.

**roleplay-service scaffold** (build *on* the kit; mirror tilemap):
- Workspace member; `Cargo.toml`; `Dockerfile` (copy tilemap, rename); `infra/docker-compose.yml` entry (host **8221** → internal 7110; `JWT_SECRET`, `INTERNAL_SERVICE_TOKEN`, `DATABASE_URL=…/loreweave_roleplay`, `CHAT_SERVICE_URL`); `main.rs` (config → `db::init` → `serve`); empty router + health.
- **gateway:** `roleplayProxy` (`/v1/roleplay`) + `roleplayUrl` in [gateway-setup.ts](../../services/api-gateway-bff/src/gateway-setup.ts) + config; create the `loreweave_roleplay` DB (compose postgres init).
- **language-rule.yaml:78** `missing`→`rust`.

- **Verify:** `cargo build/test -p service-http -p roleplay-service` green; `clippy` clean; service boots; **`GET /v1/roleplay/livez` → 200 through the gateway** (live-smoke token); `scripts/language-rule-lint.sh` green; `ai-provider-gate.py` green (no LLM). **Commit.**

## R1 — Scripts + start-orchestration (the domain) · `roleplay-service` + `chat-service`

- **`migrations/0001_init.sql`** — `roleplay_scripts` + `rp_sessions` + `rp_memory`; partial-unique indexes (`uq_rp_system_code`, `uq_rp_user_code` w/ `NULLS NOT DISTINCT`); tier CHECK (system/user; book forward-schema); **System seed** (3 presets, idempotent `ON CONFLICT`).
- **models.rs** — `Script`, `Scenario` (charter superset), request/response DTOs.
- **handlers/scripts.rs** — CRUD: list (System + own, `DISTINCT ON (code)` merge), get/create/patch/delete. Tenancy: writes `WHERE owner_user_id = uid` (System/other → 404); create forces `tier='user'`; identity from `Extension<UserId>` (INV-T2).
- **handlers/start.rs** — freeze charter from `scenario` → reqwest chat-service `POST /internal/chat/sessions` (X-Internal-Token) → insert `rp_sessions` + `rp_memory` (one tx) → return `{session_id}`. Order: **chat session first** (EC-3).
- **chat-service** — `POST /internal/chat/sessions` (`require_internal_token`) + `InternalCreateSession` model = the extracted `/start` INSERT (carries `working_memory_seed`).
- **contracts/api/roleplay-service/** — OpenAPI for `/v1/roleplay/scripts*` + `/start` (contract-first invariant).
- **Verify (TDD):** tenancy **deny** tests (System write → 404; cross-user → 404); start round-trip with a **wiremock** chat-service + **`rp_memory` read-back** (spec §10.6); **cross-service live-smoke** — real start against the running chat-service → a real `chat_sessions` row with the seed. **`/review-impl`** (new user-facing boundary + tenant isolation + the internal-token trust seam). **Commit.**

## R2 — Frontend re-point + reused acting · `frontend`

- `features/interview/` → `features/roleplay/`; `api.ts` → `/v1/roleplay/scripts` + `/start`; **acting stays `/v1/chat`** (reused `ChatView`, seed-anchored); **debrief stays chat-service M6** (`/evaluate`) for v1.
- Nav: rename the entry to **Roleplay** (en/vi); route `/interview`→`/roleplay` (redirect kept).
- **Verify:** FE typecheck + tests; **re-run the M7 browser smoke end-to-end on `/v1/roleplay`** (pick persona → start → answer → acting → debrief) — the go/no-go that the Rust path matches the proven UX. **Commit.**

## R3 — Cutover + POST-REVIEW

- Flip the FE fully onto roleplay-service; **retire chat-service `/v1/chat/templates*`** (keep `/evaluate` — debrief still lives there in v1). No user data to migrate (test data).
- **POST-REVIEW (human)** — present the new service boundary + the smoke evidence; SESSION update; **commit.** RETRO.

---

## Cross-cutting (every milestone)
- **Invariants:** language-rule (rust — lint enforces); tenancy (System read-only + Per-user owner-scoped; identity from JWT); provider-gateway + MCP-first **untouched** (roleplay-service makes no LLM calls in v1); gateway (one new REST proxy). Run `language-rule-lint.sh`, `ai-provider-gate.py`, `cargo clippy` before each commit.
- **TDD:** failing test → implement → fresh green run. Rust unit (`#[tokio::test]`) + integration (`tests/`, wiremock) + the env-gated live-smoke.

## Deferred (post-v1, tracked)
- **`crates/reality-db`** — multi-reality DB routing (extract world-service `db_pool` + reuse `meta-rs` + net-new live `pool-per-shard + search_path` client). Game plane.
- **AI script-prep** (`roleplay_draft_script` MCP tool), **file attach**, **executive** (Rust `state` evolution → gives `rp_memory` its live reader), **genre-aware debrief** (move off chat M6), **book-tier** (world-anchored roleplay + **Rust E0 grant client** + glossary/KG reads), **ES major-event** emission, **world-model goal authority**, **multi-character/voice**, **semantic recall**.
- **Opportunistic:** migrate tilemap/world onto `crates/service-http` when next touched.

## Risks / watch
- **First user-facing Rust service** — the JWT/auth boundary is net-new; `/review-impl` at R1 is mandatory (tenant isolation).
- **Cross-service start orchestration** — 2-step (chat create + local write); idempotent by session id, chat-first so a local-write failure still leaves an anchored session (EC-3).
- **Migration safety** — chat-service script endpoints stay live until R2's browser smoke passes; cutover only at R3.
- **PG version** — confirm `NULLS NOT DISTINCT` (PG15+) + the uuid default fn at R0.
- **Rust build/CI time** — multi-stage Dockerfile caches deps; first build is slow.

## Acceptance → milestone map
| Acceptance | Milestone |
|---|---|
| `service-http` kit + auth/trace/errors tested | R0 |
| `/v1/roleplay/livez` 200 through gateway; lint=rust | R0 |
| Tenancy deny (System/cross-user → 404) | R1 |
| Start → real chat session w/ seed (live-smoke) | R1 |
| `rp_memory` round-trip validated | R1 |
| M7 browser smoke green on `/v1/roleplay` | R2 |
| chat-service `/templates*` retired; POST-REVIEW | R3 |
