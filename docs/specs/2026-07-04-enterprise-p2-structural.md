# Enterprise Hardening — P2 Structural Improvements — Spec — 2026-07-04

**Status:** SPEC / not started. Parent: [`docs/plans/2026-07-04-enterprise-hardening-audit.md`](../plans/2026-07-04-enterprise-hardening-audit.md) (§ "P2 — structural improvements"). **P0 (8 live defects) and P1 (enforcement gates) are fully closed** as of 2026-07-04; this spec covers the remaining P2 backlog.

## What P2 is (and isn't)

P2 is **structural**, not bug-fixing (P0) and not gate-building (P1):

> The good implementation usually already exists somewhere in the fleet; P2 is **adopting it fleet-wide, unifying the parallel copies, and closing the design-time decisions** the P0/P1 work surfaced but deliberately deferred (each cleared defer-gate #2 — large/structural: a refactor, a schema/migration, a policy call, or a cross-service contract).

Because these are refactors touching many services, **each workstream is its own coherent effort with its own CLARIFY→…→COMMIT cycle**; they do not share a branch and are independently shippable. Sequencing (below) is by leverage + dependency, not a hard chain.

**How to use:** each item states Problem · grounded Evidence (code-anchored, re-verify at BUILD — investigation notes go stale) · Target · Scope & defer-gate · Acceptance (proven by EFFECT/test, never self-report). Sizes are complexity+risk estimates per the workflow's size gate.

---

## Workstream A — Observability unification

### A1 · Unify the two correlation-id namespaces → OTel-only  *(size: L)*

**Problem.** Two unreconciled correlation-id schemes mean Loki logs and Tempo traces **don't join** — you cannot pivot from a log line to its trace.

**Evidence.** OTel W3C `traceparent` (spans) vs bespoke `X-Trace-Id` uuid-hex (`services/glossary-service/internal/api/trace_id.go`, replicated ~5×). **Go logs carry no trace_id at all** (fleet uses bare `slog` with no span-context injection).

**Target.** One namespace: W3C trace context. A shared helper injects the active span's `trace_id`/`span_id` into every structured log line (Go + Python + TS). Retire the bespoke `X-Trace-Id` middleware (or make it a thin alias that reads/writes `traceparent`).

**Scope & defer-gate.** #2 structural — touches every service's logging setup + the 5 `trace_id` middleware copies. Do **with A2** (same seam: the log helper is where trace_id gets injected).

**Acceptance.** A live cross-service smoke (chat → knowledge → provider-registry) produces log lines whose `trace_id` matches the Tempo span; a test asserts the log helper emits `trace_id` when a span is active and omits it cleanly when none is. No service left on `X-Trace-Id`.

### A2 · Shared logging SDK per language  *(size: L)*

**Problem.** `logging_config.py` is **byte-identical copy-pasted ×3** (knowledge/composition/lore-enrichment) → guaranteed drift; `contracts/logging` (Go, typed PII/Sensitive + Redactor + prod-guard) has **0 adopters**; Python is a 3-tier spectrum where the hot-path LLM workers (translation, worker-ai, campaign, jobs, video-gen) are on plain `basicConfig`.

**Target.** One idiom per language, promoted to a shared SDK: `sdks/python/loreweave_obs.setup_logging()` (JSON + span-context trace_id + a Redactor); adopt Go `contracts/logging` fleet-wide (or fold into `loreweave_obs` Go mirror); pick NestJS Logger for TS and kill the 6 raw `console.*` on the backend. Delete the 3 copied `logging_config.py`.

**Scope & defer-gate.** #2 structural (SDK creation + fleet adoption). This is the P1 note "promote `logging_config.py` → SDK" that was deferred to P2.

**Acceptance.** `logging-discipline-lint` (built in P1, currently advisory for these) flips to **BLOCKING** and passes: 0 `basicConfig`-plain, 0 backend `console.*`, 0 copied `logging_config.py`, every Python service imports `setup_logging`. Orphan-adoption check: `contracts/logging` importer-count > 0.

---

## Workstream B — LLM-logging hardening (P0-2 structural residual + key mgmt)

### B1 · Dedicated `LLM_PAYLOAD_ENCRYPTION_KEY` + rotation + KEK derivation  *(size: M)*

**Problem.** P0-3 gave the payload KEK a keyring (`LLM_PAYLOAD_ENCRYPTION_KEYS_RETIRED`) but two structural residuals remain: (a) `usage-billing normalizeAESKey` zero-pads/truncates the passphrase to 32 bytes instead of `sha256`-deriving (`D-REVIEW-AESKEY-DERIVE`) — a >32-byte passphrase contributes only its first 32 bytes; (b) no rotation runbook/automation.

**Target.** `sha256`-derive the KEK (fixed 32-byte output from any passphrase length) behind a versioned key id, with a re-encrypt migration for existing rows; document + script rotation (add-new-active + retire-old, using the keyring that already exists).

**Scope & defer-gate.** #2 — switching derivation **orphans every existing encrypted row** → needs a re-encrypt migration (this is exactly why `D-REVIEW-AESKEY-DERIVE` was deferred). Clears `D-REVIEW-AESKEY-DERIVE`.

**Acceptance.** Round-trip test across a rotation: write under key v1 → rotate → v1 moves to retired → old rows still decrypt, new rows use v2. Migration re-encrypts a seeded corpus and a decrypt-all assertion passes.

### B2 · LLM-logging chokepoint unification + `llm_jobs` retention policy  *(size: L — P0-2 residual)*

**Problem.** Two routes reach the shared `writeUsageLog` SQL writer: streaming + the 3 sync ops use **Route A** (inline `RecordUsage` HTTP → `/internal/model-billing/record` → `recordInvocation`), while async jobs use **Route B** (`finalize→usage_outbox→relay→consumer`). Ledger integrity is met (one writer), but the "route ALL through one finalize path" design goal isn't literally met, so the two paths can drift. Separately, `llm_jobs` plaintext (`input`/`result` JSONB) has `expires_at = now()+7d` (`provider-registry migrate/migrate.go:145`) **with no implemented sweeper** — plaintext currently accumulates un-purged; the durable copy is the (now-readable, post-P0-1) encrypted `usage_logs`.

**Target.** (a) Collapse Route A into the finalize→outbox path (or formalize Route A as a sanctioned second path with a shared contract test proving both produce identical `usage_logs` rows for the same call). (b) Decide + implement the plaintext retention policy: a sweeper that purges `llm_jobs.input/.result` past `expires_at` (relying on the encrypted `usage_logs` as the durable record), or extend/remove the TTL — a **PII-retention decision**, coordinate with B1 and WS-F.

**Scope & defer-gate.** #2 — a cross-service billing-path refactor + a retention/PII policy call. This is the P0-2 structural residual (the live audit-ledger defect is already closed; see parent doc § P0-2).

**Acceptance.** A contract test asserts streaming, embed, rerank, web_search, and an async job all land a `usage_logs` row with identical shape/encryption via the unified path. A retention test: a plaintext `llm_jobs` row past `expires_at` is purged by the sweeper while its encrypted `usage_logs` copy remains decryptable. `D-REVIEW-EMBED-AUDIT-COST` (sync ops flat-cost) folded in if the pricing-resolution plumbing is built here.

---

## Workstream C — Notification maturity  *(size: L)*

**Problem.** `notification-service` now has a shared envelope (P1 `contracts/notifyevent`) but the delivery plane is still immature: HTTP-ingest producers are **fire-and-forget-swallow** (lost if the service is down; no outbox); the AMQP consumer is at-least-once but `notifications` has **no dedup key** → requeue duplicates rows; `NoopNotifier` silently drops when `RABBITMQ_URL` unset; **two live transports** (SSE + `/ws`) for one concept; only `llm_job` events reach live-push; no user opt-out; no PII discipline on bodies; D-NOTIF-I18N shipped the BE columns but **FE per-locale rendering** is still pending.

**Target.** Producer-side transactional outbox (kills fire-and-forget-swallow); `(user_id, dedup_key)` unique on `notifications`; user opt-out preferences; unify SSE + `/ws` onto one transport; FE renders `notif.*` `message_key`+`params` per user locale (closes the D-NOTIF-I18N tail); PII redaction on notification bodies.

**Scope & defer-gate.** #2 — schema migration (outbox + dedup + opt-out) + FE i18n (~93 manual imports, `fallbackLng:'en'`) + a transport unification.

**Acceptance.** Requeue-a-duplicate test asserts one row (dedup key holds); service-down test asserts the outbox redelivers on recovery (no loss); a browser smoke shows a `notif.*` notification rendered in a non-English locale; opt-out suppresses delivery. Closes `D-NOTIF-I18N` FE tail.

---

## Workstream D — Latency SLO source-of-truth  *(size: M)*

**Problem.** No platform latency SLO — DP-T tier latency contracts stop at the MMO boundary; the latency-heavy services (chat, knowledge, translation, composition) have no p95 gate on any user HTTP surface.

**Target.** `contracts/slo/latency.yaml` SoT (per top-level user HTTP endpoint: p95 target) + a presence/shape lint + wire a p95 assertion into perf-nightly + a k6 smoke against real platform endpoints (advisory → blocking only on the non-noisy top-level check).

**Scope & defer-gate.** #2 — new contract + CI wiring; most machinery exists to copy (the MMO DP-T latency contracts + perf-nightly).

**Acceptance.** The lint fails on a missing/malformed SLO row; perf-nightly emits a p95-vs-target result per registered endpoint; a deliberately-slow endpoint trips the gate in a dry-run.

---

## Workstream E — Salience ↔ learning-service feedback integration  *(size: L)*

**Problem.** Two learning loops that don't know about each other: `learning-service` (cross-service eval/quality flywheel) vs `knowledge-service` salience (`app/context/selectors/salience.py`) whose `feedback_weight` is **in-service** and **not** sourced from learning-service's quality signal.

**Target.** Decide the boundary (the P1 note left this as "document + decide"): either (a) source salience `feedback_weight` from a learning-service-published quality signal (a new contract), or (b) consciously keep them separate and document why. If (a): a contract for the quality signal + knowledge consuming it.

**Scope & defer-gate.** #2 — a product/architecture decision first, then a cross-service contract. May resolve as a documented "keep separate" (won't-fix) — start with the decision.

**Acceptance.** Either a documented decision record (boundary rationale) or, if integrating, a test that a learning-published quality delta moves the salience `feedback_weight` for the same entity.

---

## Workstream F — Platform tenant-boundary audit log  *(size: M)*

**Problem.** The audit apparatus is mature for MMO-meta (`*_audit` tables + `contracts/meta/scrubber.go`) but **no audit contract covers domain tenant-boundary crossings** — book/glossary cross-tenant reads emit **nothing**. Combined with the P0 finding "no auth-failure / tenant-boundary security audit log on the main platform."

**Target.** An append-only scrubbed audit row on every cross-tenant access + auth-failure on the main platform (model on the meta `*_audit` pattern — `error_detail_scrubbed` + hash, no raw-string accessor). Reuse the projection-trigger pattern where a projection table exists.

**Scope & defer-gate.** #2 — new audit tables/contract across the domain services; the meta pattern is the template to copy.

**Acceptance.** A cross-tenant read (user A reads a book granted by user B) and an auth-failure each emit exactly one scrubbed audit row; a raw-PII-leak test asserts no un-scrubbed field is persisted.

---

## Workstream G — Docs hygiene: fix CLAUDE.md service table (12→46)  *(size: XS)*

**Problem.** The CLAUDE.md "Services" table historically listed only 12 of ~46 services — the root of the recurring "this service doesn't exist" confusion (learning/statistics/notification all exist and run). *(Note: the current CLAUDE.md already de-inlined the table and points to `contracts/language-rule.yaml` + `docs/ARCHITECTURE.md` — re-verify at BUILD whether this is already resolved; if so, this item is a no-op/close-out.)*

**Target.** Ensure the authoritative service map is complete + linked, and no stale curated subset misleads agents.

**Scope & defer-gate.** XS — docs only, high leverage (prevents a whole class of agent errors). Do first (cheap).

**Acceptance.** Every present `services/<name>/` appears in the authoritative map (`language-rule-lint.sh` already enforces this for the language map — confirm it's green and the doc points there).

---

## Sequencing (by leverage + dependency, not a hard chain)

1. **G** (XS, docs) — cheapest, prevents agent errors; verify-then-close.
2. **A1 + A2** (observability) — do together (shared log-helper seam); unlocks trace-joined debugging for everything after.
3. **B1 + B2** (LLM-logging hardening) — closes the P0-2 structural residual + key rotation; B2's retention decision coordinates with F.
4. **C** (notification) — self-contained; closes the D-NOTIF-I18N FE tail.
5. **D** (latency SLO) — self-contained; benefits from A (trace-joined perf).
6. **F** (tenant-boundary audit) — coordinate the PII/retention stance with B2.
7. **E** (salience↔learning) — start with the decision; may be a documented won't-fix.

**Cross-cutting risk:** the repo runs **concurrent sessions on one checkout** — every workstream stages exact paths (`git commit -- <paths>`, never `git add -A`), re-verifies shared spine files survived concurrent edits, and lands its SESSION_HANDOFF update in the same commit as its code.

## Deferred rows this spec absorbs (from the parent audit doc)

- `D-REVIEW-AESKEY-DERIVE` → **B1**
- `D-REVIEW-EMBED-AUDIT-COST` → **B2** (if pricing-resolution is built there)
- `D-NOTIF-I18N` (FE tail) → **C**
- P0-2 structural residual (chokepoint + retention) → **B2**
