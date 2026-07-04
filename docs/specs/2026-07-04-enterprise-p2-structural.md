# Enterprise Hardening — P2 Structural Improvements — Spec — 2026-07-04

**Status:** SPEC / not started. Parent: [`docs/plans/2026-07-04-enterprise-hardening-audit.md`](../plans/2026-07-04-enterprise-hardening-audit.md) (§ "P2 — structural improvements"). **P0 (8 live defects) and P1 (enforcement gates) are fully closed** as of 2026-07-04; this spec covers the remaining P2 backlog.

## What P2 is (and isn't)

P2 is **structural**, not bug-fixing (P0) and not gate-building (P1):

> The good implementation usually already exists somewhere in the fleet; P2 is **adopting it fleet-wide, unifying the parallel copies, and closing the design-time decisions** the P0/P1 work surfaced but deliberately deferred (each cleared defer-gate #2 — large/structural: a refactor, a schema/migration, a policy call, or a cross-service contract).

Because these are refactors touching many services, **each workstream is its own coherent effort with its own CLARIFY→…→COMMIT cycle**; they do not share a branch and are independently shippable. Sequencing (below) is by leverage + dependency, not a hard chain.

**How to use:** each item states Problem · grounded Evidence (code-anchored) · Target · Scope & defer-gate · Acceptance (proven by EFFECT/test, never self-report). Sizes are complexity+risk estimates per the workflow's size gate.

> **✅ Adversarial verification pass — 2026-07-04.** Every workstream's code-grounded claims were re-checked against live code by 3 cold-start Explore agents (observability / LLM-logging / notification+audit); the `⚠ Verified` blocks below record where reality diverged from the first draft. Material changes: **G** already done (no-op); **A2** is EXTEND `loreweave_obs` (it exists) + a real merge (copies aren't identical) + a Go adopt-vs-retire fork, not a simple SDK create; **B1** needs **no re-encrypt migration** (decrypt is try-all) → down to S; **B2** drops outbox-unification (streaming/sync are HTTP-only with no tx to hang an outbox on — net-new infra, unjustified) in favor of a parity test + the already-designed row-delete sweeper; **C** drops "unify SSE+/ws" (a category error — different concepts) and reframes FE i18n as a channel migration; **F** must emit first-access-per-session (per-request is a volume hazard) and has an in-repo audit template (auth-service). Claims still marked "re-verify at BUILD" where an agent couldn't reach ground truth.

---

## Workstream A — Observability unification

### A1 · Unify the two correlation-id namespaces → OTel-only  *(size: L)*

**Problem.** Two unreconciled correlation-id schemes mean Loki logs and Tempo traces **don't join** — you cannot pivot from a log line to its trace.

**Evidence (verified 2026-07-04).** OTel W3C `traceparent` (spans) vs bespoke `X-Trace-Id` uuid-hex (`services/glossary-service/internal/api/trace_id.go:41-98`), replicated **~8× across languages** (Python ASGI ×5: chat/knowledge/composition/lore-enrichment/learning `app/middleware/trace_id.py`; Go chi ×1; Rust axum `crates/service-http/src/trace.rs`; TS gateways). The bespoke id is **independent of `traceparent`** (`loreweave_obs` docstring confirms it is "UNRELATED to the OTel trace id Tempo indexes by"). **Go DOES emit OTel spans** (`observability.InitTracer` + `ChiMiddleware` in every Go `main.go`, regression-locked in `book-service/internal/api/tracing_test.go`) — but **Go logs carry no trace_id**: the fleet uses the global `slog.SetDefault(JSONHandler).With("service", …)` and calls package-level `slog.Xxx(...)` that pass **no `ctx`**.

**Target.** One namespace: W3C trace context. A shared `slog.Handler` (Go) / logging filter (Python) reads the active span and injects `trace_id`/`span_id` into every line. Do NOT hard-retire `X-Trace-Id` — instead **dual-emit**: keep the bespoke id flowing where it is load-bearing (see blocker) while adding the OTel `trace_id`, then deprecate the bespoke channel once dual-emit is proven. `loreweave_obs.current_otel_trace_id()` already exists to source the OTel id.

**⚠ Verified blockers.**
1. **Call-site sweep, not a handler swap.** A span-reading `slog.Handler` only sees the trace id if callers use the `context`-aware `slog.InfoContext/ErrorContext` variants; the fleet's bare `slog.Error(msg, …)` calls pass no ctx. Injection therefore requires a **call-site migration across every Go service**, which is the real cost (drives size **L**), not a config toggle.
2. **`X-Trace-Id` is load-bearing in 3 non-header surfaces** that `traceparent` does not populate today: the **500-error JSON body `trace_id` field** ops grep by, the **persisted `auth-service` audit column** (`migrate.go:186 trace_id TEXT`), and the ~8-impl request-propagation chain. No frontend/runtime client reads the *response header* (safe to drop that), but a pure swap would break "paste the id from a UI error into log search" — hence dual-emit, not retire.

**Scope & defer-gate.** #2 structural — a call-site sweep across every Go service + dual-emit wiring in the 8 middleware copies. Do **with A2** (same seam: the log helper is where trace_id gets injected).

**Acceptance.** A live cross-service smoke (chat → knowledge → provider-registry) produces log lines whose OTel `trace_id` matches the Tempo span; a 500-error response still carries a greppable id (bespoke or OTel) in its JSON body; a test asserts the handler injects `trace_id` under an active span and omits it cleanly with none.

> **Status (2026-07-04): substrate SHIPPED fleet-wide + book-service reference sweep SHIPPED.** (`e7043b7d2` substrate + `723984958` book-service sweep + `61cad8e9d` **fleet substrate adoption ×10**). `observability.SetupLogging` injects `otel_trace_id` (same field as Python); book-service fully swept (14 request-path sites → `*Context`; startup logs left ctx-less). Go SDK tests incl. the money test (injection survives `.With()`). **Verified (/review-impl):** all 14 swept sites use a span-carrying `r.Context()` (no no-op conversions).
>
> **Fleet substrate adoption (`61cad8e9d`) — the 10 services that already have BOTH a JSON logger AND `InitTracer` wired** now install `SetupLogging` in place of the bare `slog.SetDefault(JSON…)`: auth, catalog, glossary, notification, provider-registry, sharing, statistics, agent-registry, usage-billing, worker-infra. Behavior-identical JSON+`service`-field output PLUS `otel_trace_id` auto-injection armed for every present/future `slog.*Context` call. Zero go.mod churn (obs already imported); `go build ./...` green in all 10. **Excluded (tracked, `D-A1-TIER2-NOTRACE`):** JSON-logger-but-no-tracing workers (publisher/retention-worker/breach-notifier/meta-outbox-relay) — adopting there pulls the otel dep-graph for a permanently-dormant injector; they adopt when tracing lands. Tier-3 (no structured logger: admin-cli/ops-bots) is out of A1 scope (that's Logging-Standard adoption, not trace-id injection).
>
> **Remaining — the fleet call-site sweep is a per-service REFACTOR, not a mechanical pass (tracked `D-A1-CALLSITE-SWEEP`).** Calibration on 3 services showed the bare-`slog.Xxx` counts in `internal/` **massively overcount** convertible sites: most are **startup** (`usage-billing` admin-key parse in `NewServer`), **background loops** (`sweeper.go`), or **async email goroutines** (`auth` SMTP sends) — where there is no span, or the request ctx is *already cancelled*. A blind `slog.X→XContext` there is a **bug**, not an improvement. Even the genuinely-request-path sites often need **ctx threaded through an internal helper** (`catalog`'s `fetchBookLanguages(bookID)` takes no ctx → converting its 2 logs needs a signature change + caller + `internalGet`). So the sweep is a bounded-but-judgment-heavy refactor per service (single-digit real sites each), best done deliberately (or fanned out) — deferred under gate #2 (structural) + value-throttled because **the clickable join is Tempo-gated anyway** (below). book-service stands as the worked reference. **Sweep-on-touch**: when a Go service's request path is edited for other reasons, convert its live-span sites then.
>
> **Clickable log→trace join is gated on infra** (unchanged): Grafana's Loki datasource has `derivedFields: []` and there is no Tempo datasource yet (`infra/grafana/.../datasources.yaml:66` — "placeholder until cycle 37 L7.G tracer Tempo wire-up"). A1 emits the join KEY (`otel_trace_id`); realizing the clickable link needs the Tempo datasource + a Loki `derivedField` matching `otel_trace_id` — tracked infra work, gated on Tempo deployment (adding a derivedField to a non-existent Tempo datasource would be broken config). Emit-side is the prerequisite and is done.

### A2 · Shared logging SDK per language — split A2a (Python) / A2b (Go)  *(A2a ✅ SHIPPED · A2b pending)*

> ✅ **A2a done 2026-07-04** (`687fd4949`, `aba652a86`, `e7dbef061`, `178858d51`, `7500db04e`): `loreweave_obs.setup_logging` extended in (merged superset Redactor + dual-emit `otel_trace_id`); the **3 copied `logging_config.py` retired** (knowledge/composition/lore-enrichment → shims); **every Python runtime `logging.basicConfig` migrated** (campaign/jobs/worker-ai/translation/video-gen mains + learning main + composition/lore-enrichment/video-gen worker `__main__`); `logging-discipline-lint` **enforces basicConfig as a hard-fail** (blocking via existing CI wiring; print/println! stay advisory), negative-proven. /review-impl caught + fixed a pythonjsonlogger import-coupling (tracing-only imports no longer require the logging dep). **Remaining tail (not A2a-blocking):** chat-service is "partial-tier" (OTel but its own unstructured root logger, not `setup_logging`) — a follow-on adoption, not a basicConfig defect. **A2b (Go) is the open fork below.**

**Problem.** `logging_config.py` is copy-pasted ×3 (knowledge/composition/lore-enrichment) → drift; `contracts/logging` (Go, typed PII/Sensitive + Redactor + prod-guard) has **0 adopters** (confirmed — only its own tests import it); Python is a 3-tier spectrum where the hot-path LLM workers (translation, worker-ai, campaign, jobs, video-gen) are on plain `basicConfig`.

**⚠ Verified corrections to the original framing.**
- **`loreweave_obs` ALREADY EXISTS** (`sdks/python/loreweave_obs/__init__.py`, exports `setup_tracing` + `current_otel_trace_id`) — it is a *tracing* helper with **no** logging. So this is **EXTEND** (add `setup_logging` + a Redactor beside the tracing helpers), not create; note logging is a scope-widening of a tracing-named SDK.
- **The 3 `logging_config.py` are NOT byte-identical** (3 distinct blobs). lore-enrichment's is materially richer: extra `job_id`/`stage` ContextVars + a **third** secret regex the other two lack. So the shared `setup_logging` MUST parameterize the service name **and** accept optional extra correlation ContextVars, or lore-enrichment regresses — a real merge, not a dedup. Preserve the `pythonjsonlogger.json`-vs-`.jsonlogger` import fallback.
- **Adopting Go `contracts/logging` is a REWRITE, not an import swap** — it exposes a typed `Field`/`Emit` API (different from the `slog` the fleet actually calls) and **prod-refuses a nil `Redactor`** (`ErrNilRedactor`), so adoption also requires binding a `pii.Redactor` adapter per service.

**Target — A2a (Python, do first, higher value/lower risk).** Add `loreweave_obs.setup_logging(service_name, *, extra_context_vars=…)` (JSON + injected OTel `trace_id` via `current_otel_trace_id` + a Redactor merging all three secret regexes); adopt across all Python services incl. the `basicConfig` hot-path workers; delete the 3 `logging_config.py`.
**Target — A2b (Go, heavier).** Either adopt `contracts/logging` fleet-wide (accept the `Field`/`Emit` rewrite + wire the `pii.Redactor` adapter) **or** consciously standardize on `slog` + a shared span-reading handler (from A1) and retire `contracts/logging` as an orphan. **This is a design fork — decide in CLARIFY.** TS: NestJS Logger, kill the 6 backend `console.*`.

**Scope & defer-gate.** #2 structural (SDK extension + fleet adoption). A2a and A2b ship independently.

**Acceptance.** A2a: `logging-discipline-lint` flips **BLOCKING** and passes — 0 `basicConfig`-plain, 0 copied `logging_config.py`, every Python service imports `setup_logging`, lore-enrichment's `job_id`/`stage` fields still emitted (regression test). A2b: 0 backend `console.*`; and either `contracts/logging` importer-count > 0 (adopt) OR it is deleted (retire) — no orphan left half-alive.

---

## Workstream B — LLM-logging hardening (P0-2 structural residual + key mgmt)

### B1 · KEK `sha256`-derivation + rotation runbook  *(size: S — ✅ SHIPPED 2026-07-04)*

> ✅ **Done.** `deriveAESKey` (`usage-billing server.go`) SHA-256-derives a `sha256:`-marked KEK, keeps pad/truncate for unmarked keys → version-gated per key, no migration. Runbook on the `LLMPayloadEncryptionKey` config field. Tests: `TestDeriveAESKey_Sha256VersionGate` (money test) + `TestUnwrapSessionKey_DerivationRotation`; full usage-billing suite green. Clears `D-REVIEW-AESKEY-DERIVE`.

**Problem.** P0-3 gave the payload KEK a keyring (`LLM_PAYLOAD_ENCRYPTION_KEYS_RETIRED`); the residual is (a) `usage-billing normalizeAESKey` (`server.go:56-67`) zero-pads/truncates the passphrase to 32 bytes instead of `sha256`-deriving (`D-REVIEW-AESKEY-DERIVE`) — a >32-byte passphrase contributes only its first 32 bytes; (b) no documented rotation runbook.

**⚠ Verified — this is SMALLER than the audit doc implied: NO re-encrypt migration needed.** Decrypt already does **try-all-keys** in fixed order (primary → legacy → each retired: `unwrapSessionKey` `server.go:149-170`), and there is **no key-id column that routes decryption** (`payload_encryption_key_ref` on `usage_logs` is an observability fingerprint, never queried back to pick a key; `usage_log_details` has no key-version column). So rotation for existing rows is already covered by try-all — **no backfill/re-encrypt migration is required**.

**Target.** Switch `normalizeAESKey` to `sha256`-derive (fixed 32 bytes from any length) **version-gated per key**: because a derivation change alters the bytes for *every* key, the change must be applied only to the new active key while existing active/legacy/retired keys keep the OLD normalization in the retired keyring (try-all then finds them). Document the rotation runbook (move current key → `…_KEYS_RETIRED`, set fresh key), using the keyring + `TestUnwrapSessionKey_RetiredKeyRotation` harness that already exist.

**Scope & defer-gate.** #2 (crypto-derivation change) but **no migration** — the "orphans every row" concern the audit doc raised is mooted by try-all. Clears `D-REVIEW-AESKEY-DERIVE`.

**Acceptance.** A test: rows wrapped under the OLD (pad/truncate) normalization still decrypt after the new key uses `sha256`-derive (both live in the keyring, try-all resolves each); a new row wraps under the `sha256` key and round-trips; the rotation runbook is executed in a test (active→retired→new-active) with no decrypt regression.

### B2 · LLM-logging route parity + `llm_jobs` retention sweeper  *(✅ SHIPPED 2026-07-04)*

> ✅ **SHIPPED** (`2932fe2e9` sweeper · `30c500b5f` embed cost · `848b43e0c` parity+D-S4C):
> - **(b) Retention sweeper** — `repo.PurgeExpiredJobs` (bounded whole-row DELETE of terminal `llm_jobs` past `expires_at`, using the pre-existing partial index) + a ticker goroutine mirroring the stuck-running sweeper + `LLM_RETENTION_SWEEP_INTERVAL_S`/`_BATCH` config. pgxmock test statically asserts the WHERE predicates (the load-bearing status filter) + bounded LIMIT. Runtime row-selection → `D-B2-RETENTION-LIVE-SMOKE` (NOT run against shared dev DB). **Review-fix (`e99f3f3c5`):** the same sweeper now also prunes published `usage_outbox`/`job_event_outbox` rows (`PurgePublishedOutbox`, `LLM_OUTBOX_RETENTION_HOURS` default 24) — /review-impl caught that those tables carry plaintext `request_payload`/`response_payload` (#32) and were never deleted, an unbounded plaintext twin of the `llm_jobs` gap. `published_at IS NOT NULL` is the safety gate (never drop an un-drained row).
> - **(c) Embed cost** — `internalEmbed` SELECTs `um.pricing` + computes input-only cost via shared `billing.PriceEmbedding`, threaded through `recordSyncUsage(…, costUSD *float64, …)`. rerank/web_search pass `nil` by design (0/0 tokens → per-token cost meaningless) → `D-B2-RERANK-WEBSEARCH-PRICING`. Closes `D-REVIEW-EMBED-AUDIT-COST`.
> - **(a) Parity — and a real bug it surfaced.** Building the parity test exposed that `/record` (Route A) **silently dropped the caller's authoritative `total_cost_usd`** (streaming's tallied `actual` + embed's cost) and wrote the flat fallback, while the stream consumer (Route B) honored `cost_usd` — so the committed-spend rollup (`guardrail SUM(total_cost_usd)`) mis-counted every streaming row. This was the tracked `D-S4C-STREAMING-REALCOST`. Fixed: `recordUsageRequest` gains `total_cost_usd`, `recordUsageParams` passes it as the `recordCostUSD` override. `route_parity_test.go` locks the two builders to the same billing-critical `usageLogParams` (headline: `CostUSD`); **proven to RED on the drift**. End-to-end wire → `D-B2-PARITY-LIVE-SMOKE`. The heavy "outbox-everything" unification stays out of scope (net-new infra, unjustified).

**Problem.** Two routes reach the shared `writeUsageLog` SQL writer: streaming + the 3 sync ops use **Route A** (inline `RecordUsage` HTTP → `/internal/model-billing/record` → `recordInvocation`), while async jobs use **Route B** (`finalize→usage_outbox→relay→consumer`). Ledger integrity is met (one writer), but the paths can drift. Separately, `llm_jobs` plaintext (`input`/`result` JSONB) has `expires_at = now()+7d` (`provider-registry migrate/migrate.go:145`) **with no implemented sweeper** — plaintext currently accumulates un-purged; the durable copy is the (now-readable, post-P0-1) encrypted `usage_logs`.

**⚠ Verified — do NOT force outbox-unification.** Streaming `settle` and `recordSyncUsage` are **pure HTTP with no local DB transaction** (`stream_billing.go:203-289`, `server.go:2785-2815` — no pool/tx, no `llm_jobs` row); the async outbox seam exists only because that path already owns the `llm_jobs` UPDATE tx. "Route ALL through finalize→outbox" would mean **introducing a net-new DB table + write into two paths that write nothing locally today** — structural addition for a marginal gain (transactional at-least-once vs the current best-effort HTTP + usage-billing sweeper backstop), when ledger integrity is already met. So the reframed target:

**Target.**
- **(a) Parity, not unification (default).** Keep the two routes; add a **contract test** asserting streaming, embed, rerank, web_search, and an async job each land a `usage_logs` row of identical shape/encryption. Only if a best-effort-HTTP loss is observed in practice (evidence, not speculation) escalate to the net-new transactional write — track that as a conditional sub-item, not now.
- **(b) Retention sweeper — follow the EXISTING design intent: whole-row DELETE, not column-purge.** The `migrate.go:143-144` comment already designs a terminal-rows-past-`expires_at` DELETE; implement that sweeper. Verified safe: `input` is never API-returned (`MarshalJob` omits it) and its only reader `LoadForProcess` is `pending`-only, so a terminal purge can't collide with dispatch; `result` IS served by `GET /{v1,internal}/llm/jobs/{id}` with no time bound, but a whole-row DELETE cleanly 404s (consumers already tolerate 404), whereas a column-purge would return a confusing partial row. Coordinate the retention window with WS-F/PII stance.
- **(c) Sync cost (`D-REVIEW-EMBED-AUDIT-COST`).** **embed = cheap** — add the `pricing` column to the credential SELECT it already runs (`server.go:3060`) + compute from `result.PromptTokens`. **rerank/web-search need a non-token pricing dimension first** (they pass 0/0 tokens — `server.go:2906,2995` — so per-token cost is meaningless); either add per-call/per-request pricing or consciously leave them flat-rate + documented.

**Scope & defer-gate.** #2 — a retention sweeper + a parity contract test + the embed-cost add. The heavy "outbox everything" is explicitly **out of scope** (net-new infra, unjustified today).

**Acceptance.** Parity contract test green across all 5 call types. Retention test: a terminal `llm_jobs` row past `expires_at` is DELETEd by the sweeper, its encrypted `usage_logs` copy still decrypts, and `GET …/jobs/{id}` 404s. Embed rows carry an authoritative `TotalCostUSD`; rerank/web-search cost decision recorded.

---

## Workstream C — Notification maturity  *(size: L — reliability core SHIPPED; feature remainder tracked)*

> **Status (2026-07-04): the two reliability wins SHIPPED; the 4 feature/structural parts remain (each substantial).**
> - ✅ **(2) Dedup** (`042786197`) — `dedup_key` + partial-unique `(user_id, dedup_key)`; consumer keys `job_id:status` with `ON CONFLICT DO NOTHING` (a redelivery no longer duplicates a row); HTTP create/batch accept an optional key (idempotent). Pure key-shape test; runtime → `D-C-DEDUP-LIVE-SMOKE`.
> - ✅ **(6) NoopNotifier not-silent** (`afedf0668`) — a loud one-time startup WARN when `RABBITMQ_URL` is unset (notifications disabled), so the prod misconfig is visible instead of surfacing as missing notifications.
> - ✅ **(5) PII redaction on bodies** (`e759aa6e3`) — `internal/redact.Body()` scrubs secret-shaped tokens (Bearer/sk-/api-key) from both ingress bodies before storage/push; NARROW scope (mirrors the Python RedactFilter) — emails/names/CJK preserved (over-redaction would corrupt legit content). Test locks both directions.
> - ✅ **(3) User opt-out preferences** (`35ea27165`) — `notification_preferences(user_id, category, enabled)` (per-user scope); `internal/prefs.Suppressed/Set/List` (fail-OPEN — a lookup error/missing row never drops a notification); gates on all 3 insert paths (consumer skip+Ack, HTTP 200-suppressed, batch `suppressed` count); `GET/PUT /v1/notifications/preferences`. Suppressed-semantics test.
> - ⏳ **Remaining (2 slices):** **(1) HTTP-producer transactional outbox** `D-C-PRODUCER-OUTBOX` — gate #2 structural (a new outbox table + relay on each producer service, modelled on book-service's `insertBookOutbox`; cross-service; needs a real plan). **(4) FE canonical-i18n consolidation** `D-C-FE-I18N` — **NOT a broken feature**: `NotificationItem.tsx:38-43` already localizes llm_job notifications from `metadata.operation`/`metadata.status`, and the BE list API already exposes `message_key`/`message_params`. The tail is a **consolidation** — migrate the FE off the metadata path onto the canonical `message_key`+`message_params` columns (also covers future non-llm_job producers that set a key but no metadata.operation) + add `notif.*` catalog entries across the 4 locales. Real FE slice, but the headline "notifications are localized" already holds for the main case.

**Problem.** `notification-service` now has a shared envelope (P1 `contracts/notifyevent`) but the delivery plane is still immature: HTTP-ingest producers are **fire-and-forget-swallow** (lost if the service is down; no outbox); the AMQP consumer is at-least-once but `notifications` has **no dedup key** → requeue duplicates rows; `NoopNotifier` silently drops when `RABBITMQ_URL` unset; **two live transports** (SSE + `/ws`) for one concept; only `llm_job` events reach live-push; no user opt-out; no PII discipline on bodies; D-NOTIF-I18N shipped the BE columns but **FE per-locale rendering** is still pending.

**⚠ Verified corrections.**
- **Dedup on the AMQP path is FREE** — `TerminalEvent.JobID` is a stable UUID already on the wire and the consumer already requires it non-nil (`consumer.go:254`). Dedup key = `job_id:status` (one job emits one terminal event per status). **But the HTTP-ingest path has NO stable id** (`createNotification` `server.go:114-175` takes no idempotency field). So a strict `(user_id, dedup_key)` UNIQUE forces every HTTP producer to supply a key — instead use a **partial unique index** `UNIQUE(user_id, dedup_key) WHERE dedup_key IS NOT NULL` (AMQP fills it, HTTP producers opt in over time).
- **DROP "unify SSE + `/ws`" — they are NOT redundant and neither is in notification-service.** SSE `/v1/notifications/stream` (api-gateway-bff `notifications.controller.ts`) is the notification push; `/ws` (`ws-server.ts`) is the **game/agent realtime** channel (different concept, different payloads). Unifying them is a category error; leave both.
- **FE i18n is a channel MIGRATION, not net-new render.** The BE `message_key`/`message_params` columns exist + are populated + exposed (P1 done). But the FE (`NotificationItem.tsx:30-43`) still derives i18n from `metadata.operation`/`metadata.status` (an **older** channel) and the `message_key` column is **invisible to FE** (`api.ts` `Notification` type lacks the field). The tail = add `message_key`/`message_params` to the FE type + render from the key, deprecating the `metadata.operation` path.

**Target.** Producer-side transactional outbox for the HTTP producers (kills fire-and-forget-swallow — model on book-service's `insertBookOutbox`); partial-unique `(user_id, dedup_key)` on `notifications` (AMQP sources `job_id:status`); user opt-out preferences; FE renders from the `message_key` column per locale (closes D-NOTIF-I18N tail); PII redaction on notification bodies; make `NoopNotifier` at least WARN-log on drop rather than silently return nil.

**Scope & defer-gate.** #2 — schema migration (outbox + partial-unique dedup + opt-out) + FE i18n channel migration (~93 manual imports, `fallbackLng:'en'`). No transport work.

**Acceptance.** Requeue-a-duplicate AMQP event asserts one row (partial-unique holds on `job_id:status`); service-down test asserts the HTTP outbox redelivers on recovery (no loss); a browser smoke shows a `notif.*` notification rendered from `message_key` in a non-English locale; opt-out suppresses delivery. Closes `D-NOTIF-I18N` FE tail.

---

## Workstream D — Latency SLO source-of-truth  *(buildable core ✅ SHIPPED; perf-nightly infra-gated)*

> ✅ **SHIPPED** — `contracts/slo/latency.yaml` (8 top-level user HTTP endpoints across the latency-heavy AI + domain services, each with a p95 target/window/owner; sync-only scope, async-enqueue + SSE excluded with rationale) + `scripts/slo-latency-lint.py` (presence/shape gate: required fields, positive p95, known verb, unique id+route, real `services/<name>/` — proven to red on all 6 bad-row classes) wired **blocking** into `lint-foundation.yml` p1-lints. Registered in the standards index (§B SoT + §D gate + Performance row).
> **Infra-gated tail (`D-D-PERF-NIGHTLY`):** the p95-vs-target assertion + k6 smoke — there is **no perf-nightly harness in the repo** (verified: no `perf`/`nightly`/`k6` workflow), so, exactly like A1's Tempo dependency, the SoT+lint are the buildable prerequisite (done) and the measurement side is gated on building perf-nightly. Not "blocked" — it's unbuilt infra; scoped as its own slice.

**Problem.** No platform latency SLO — DP-T tier latency contracts stop at the MMO boundary; the latency-heavy services (chat, knowledge, translation, composition) have no p95 gate on any user HTTP surface.

**Target.** `contracts/slo/latency.yaml` SoT (per top-level user HTTP endpoint: p95 target) + a presence/shape lint + wire a p95 assertion into perf-nightly + a k6 smoke against real platform endpoints (advisory → blocking only on the non-noisy top-level check).

**Scope & defer-gate.** #2 — new contract + CI wiring; most machinery exists to copy (the MMO DP-T latency contracts + perf-nightly).

**Acceptance.** The lint fails on a missing/malformed SLO row; perf-nightly emits a p95-vs-target result per registered endpoint; a deliberately-slow endpoint trips the gate in a dry-run.

---

## Workstream E — Salience ↔ learning-service feedback integration  *(✅ RESOLVED 2026-07-05 — documented keep-separate)*

> ✅ **DECIDED — keep separate** (spec option b). Decision record: [`2026-07-05-salience-learning-boundary.md`](2026-07-05-salience-learning-boundary.md). Verified against code: the two loops run at **different granularities** (salience = per-`(user,project,entity)` chat-thumbs, sourced entirely in-service from `entity_access_log.feedback_score`; learning-service quality signals are keyed by chapter/translation/run/model/wiki/chat-message). learning-service **publishes/exposes NO per-entity quality signal** — its one per-`glossary_entity_id` datum (`glossary_name_confirmed`) is a binary human flag in its own DB, on no endpoint/event. Integration would be **net-new production on both sides** (a new continuous per-entity signal + a new contract) for **no demonstrated gain**, and a platform-wide signal is the **wrong tier** for a per-user ranking (tenancy: salience is per-user, not System-global). The term is default-OFF and flip-gated. Tracked as **`D-E-SALIENCE-LEARNING-BRIDGE`** (conscious won't-fix, revisit-gated: reopen only if an ambiguous-query eval shows the in-service term is ceiling-limited by sparse thumbs, or learning-service grows a real per-entity quality signal for another consumer). Acceptance met by the "documented decision (boundary rationale)" branch.

**Problem.** Two learning loops that don't know about each other: `learning-service` (cross-service eval/quality flywheel) vs `knowledge-service` salience (`app/context/selectors/salience.py`) whose `feedback_weight` is **in-service** and **not** sourced from learning-service's quality signal.

**Target.** Decide the boundary (the P1 note left this as "document + decide"): either (a) source salience `feedback_weight` from a learning-service-published quality signal (a new contract), or (b) consciously keep them separate and document why. If (a): a contract for the quality signal + knowledge consuming it.

**Scope & defer-gate.** #2 — a product/architecture decision first, then a cross-service contract. May resolve as a documented "keep separate" (won't-fix) — start with the decision.

**Acceptance.** Either a documented decision record (boundary rationale) or, if integrating, a test that a learning-published quality delta moves the salience `feedback_weight` for the same entity.

---

## Workstream F — Platform tenant-boundary audit log  *(✅ SHIPPED 2026-07-05)*

> ✅ **SHIPPED** — an append-only `tenant_access_audit` table + a coalesced first-per-window emit in BOTH domain services, modeled on auth-service's append-only pattern (UUID PK, `outcome` CHECK enum, `created_at` index, `REVOKE UPDATE/DELETE FROM app_service_role`, no FK so the trail outlives a deleted book).
> - **book-service** (`migrate.go` `tenantAuditSQL` + `api/tenant_audit.go` + `authBook` wiring): emits in the `authBook` chokepoint when the book has a KNOWN owner ≠ caller — `granted` when the caller's grant satisfies `need`, `denied` on under-grant (403) OR no-grant-on-existing-book (404). A **missing book** (owner=Nil) and an **own-book** access are NOT crossings → never audited. Records `actor_id, book_id, owner_id, outcome, coalesce_bucket` (owner denormalized for forensics).
> - **glossary-service** (`migrate.go` `tenantAuditSQL` + `api/tenant_audit.go` + `checkGrant` wiring): resolves grants cross-service (`ResolveAccess` returns only a Level, no owner), so it emits when the caller holds a **real sub-owner grant** (view/edit/manage) — `granted`/`denied` by whether it satisfies `need`. `Level==none` is **skipped** (indistinguishable from a missing book at this layer — no confirmed tenant, avoids auditing probes) and `Level==owner` is own-tenant. Records `actor_id, book_id, outcome, coalesce_bucket` (NO owner column — resolvable from `book_id` in book-service's DB).
> - **Volume control = "first-access-per-window"** (the practical stand-in for per-session; there is no session id at the grant layer): the emit does `ON CONFLICT (actor_id, {book_id|resource}, outcome, coalesce_bucket) DO NOTHING` against a partial-unique index, `coalesce_bucket = now.Truncate(window)` (`TENANT_AUDIT_COALESCE_WINDOW_S`, default 3600, floored to 1s). A collaborator paging chapters emits **one** `granted` row per window, not one per GET.
> - **PII is structural, not a scrub step** — the row is ids + an `outcome` enum + a truncated bucket timestamp only; there is **no free-text/path/payload column**, so "no un-scrubbed field is persisted" holds by construction (asserted by the insert-shape test: exactly 5 args book / 4 args glossary, no detail arg).
> - **Emit is fire-and-forget** — a background-context goroutine (the request ctx cancels on response) with a 5s timeout + panic-recover + error-log; nil pool ⇒ no-op. A best-effort audit must NEVER block or fail the request.
> - **Injectable `emitTenantAudit` hook** on each Server (mirrors book-service's `resolveBook` seam) so the emit DECISION is unit-tested with a synchronous spy: 5 book tests (granted/denied-under-grant/denied-no-grant/no-emit-own/no-emit-missing) + 4 glossary tests (granted/denied/no-emit-owner/no-emit-none) + insert-shape + bucket-coalescing tests, all green.
> - **Deferred `D-F-AUDIT-LIVE-SMOKE`:** a real cross-tenant read on a stacked-up book+glossary asserting a row appears + the coalescing holds across a second read in-window. NOT run against the shared dev DB (which holds real rows); gated on a scratch stack.

**Problem.** No audit covers domain tenant-boundary crossings — **verified**: book-service `resolveBookAuth`/`authBook` (`collaborators.go:80-168`) and glossary `checkGrant`/`requireGrant` (`ownership.go:49-89`) write only HTTP 401/404/403 on a cross-tenant (collaborator) read — **no audit row**. No general auth-failure audit exists on the main platform (the only failure-outcome audit is narrow: auth-service's `admin_token_issuance_audit` + `mcp_call_audit`).

**⚠ Verified — two things reshape the design.**
- **Volume risk is real → do NOT log per-request.** `authBook` runs on **every** per-book route with no request-scoped memoization (2 SELECTs each), and glossary `requireGrant` fires a **cross-service HTTP** `ResolveAccess` per request. A collaborator paging chapters would emit one audit row per GET. Target **emit-on-first-cross-tenant-access-per-session** (or sample/coalesce), not per-read — this is a design requirement, not a nice-to-have.
- **A domain-level audit template already exists to copy** — auth-service's `admin_token_issuance_audit` (`migrate.go:103-124`) + `mcp_call_audit` (`migrate.go:179-204`): UUID PK, denormalized actor for post-deletion forensics, `outcome` CHECK enum, `created_at` index, and `REVOKE UPDATE, DELETE … FROM app_service_role` append-only enforcement. Model on **this in-repo domain pattern**, not just the meta apparatus.

**Target.** An append-only scrubbed audit row on cross-tenant access (first-per-session) + auth-failure, in each domain service's own DB, using the auth-service append-only pattern (`outcome` enum + REVOKE UPDATE/DELETE + scrubbed detail, no raw-string accessor). Reuse the projection-trigger pattern where a projection table exists.

**Scope & defer-gate.** #2 — new per-service audit tables + a coalescing/first-access emit path; the auth-service audit tables are the template to copy.

**Acceptance.** A cross-tenant read (user A reads a book granted by user B) and an auth-failure each emit exactly one scrubbed audit row; a raw-PII-leak test asserts no un-scrubbed field is persisted.

---

## Workstream G — Docs hygiene: service map  *(✅ ALREADY RESOLVED — verified 2026-07-04, no-op)*

**Verified DONE.** CLAUDE.md already de-inlined the stale 12-service table (line 22: "This file does **not** enumerate them … Authoritative service→language map: `contracts/language-rule.yaml`") and `bash scripts/language-rule-lint.sh` returns **`[language-rule] PASS`** — every present `services/<name>/` has a row in the authoritative map. No work remains; this row is closed out.

---

## Sequencing (by leverage + dependency, not a hard chain)

Post-verification sizes: **G ✅done · B1 S · A2a M · B2 M · D M · F M · A1 L · A2b L · C L · E L(decision-first)**.

1. **G** — ✅ already resolved (no-op).
2. **B1** (S) — cheapest real item; self-contained crypto-derivation + runbook, no migration. Good warm-up.
3. **A1 + A2a** (observability) — do together (shared log-helper seam: A2a's `setup_logging` is where A1's trace_id injection lands). A1 carries the Go call-site sweep. Unlocks trace-joined debugging for everything after. **A2b (Go `contracts/logging` adopt-vs-retire)** is a separate CLARIFY fork — schedule after A2a.
4. **B2** (M) — parity test + retention sweeper (NOT outbox-unification); retention window coordinates with F.
5. **C** (L) — self-contained; dedup + HTTP outbox + FE i18n channel migration (no transport work).
6. **D** (M) — self-contained; benefits from A (trace-joined perf).
7. **F** (M) — first-access-per-session audit (coordinate PII/retention stance with B2).
8. **E** (L) — decision-first; may be a documented won't-fix.

**Cross-cutting risk:** the repo runs **concurrent sessions on one checkout** — every workstream stages exact paths (`git commit -- <paths>`, never `git add -A`), re-verifies shared spine files survived concurrent edits, and lands its SESSION_HANDOFF update in the same commit as its code.

## Deferred rows this spec absorbs (from the parent audit doc)

- `D-REVIEW-AESKEY-DERIVE` → **B1** (verified: no re-encrypt migration needed — try-all covers rotation)
- `D-REVIEW-EMBED-AUDIT-COST` → **B2** (embed cheap; rerank/web-search need a non-token pricing dimension or a documented flat-rate)
- `D-NOTIF-I18N` (FE tail) → **C** (a `metadata.operation`→`message_key` channel migration)
- P0-2 structural residual → **B2** (route parity + retention sweeper; outbox-unification explicitly out of scope)
