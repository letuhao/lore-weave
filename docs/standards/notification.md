# Notification Standard

**Status:** ACTIVE (rules) · enforcement to build — see §Enforcement · **Date:** 2026-07-04
**Governs:** how user-facing notifications are produced, shaped, delivered, and read across the platform. (Operational/ops alerts — `contracts/alerts/` + the SRE alerting services — are a separate, already-governed concern.) Indexed in [`README.md`](./README.md); current-state + live bugs in [audit](../plans/2026-07-04-enterprise-hardening-audit.md#area-5--notification).

> **Why.** `notification-service` exists and is reasonably shaped, but there is **no shared envelope contract** — four producers copy-paste divergent wire shapes, the category enum is enforced on one ingress path but violated by another (auth's `mcp_approval` is silently 400-dropped), delivery is fire-and-forget-swallow on one path and no-dedup at-least-once on the other, and there is no user opt-out or PII discipline. The service is fine; the missing *contract around it* is the problem.

## Rules

- **NOTIF-1 · One versioned envelope, cross-language.** A single `contracts/notifications/envelope.{go,yaml}` with generated Go **and** Python mirrors (model on `contracts/alerts/envelope.go`), killing the copy-pasted `TerminalEvent` struct and the three divergent HTTP bodies. `i18n_key` + `params` are first-class fields (with matching DB columns) so localization actually works.
- **NOTIF-2 · Category is a single-source enum, enforced on EVERY ingress.** One SoT enum (`translation | social | wiki | system | llm_job | mcp_approval | campaign | billing | …`) enforced identically on the HTTP ingest **and** the AMQP consumer (today the consumer's raw SQL bypasses `validCategory`), with a `result.error` on reject — **never a silent 400-swallow** (fixes the `mcp_approval` drop). Adding a category = one enum edit, not a per-path patch.
- **NOTIF-3 · Channel abstraction.** A notification declares its channels (in-app-persist, live-SSE/WS, email, future web-push); producers don't hand-pick HTTP-vs-AMQP ad hoc. The two live transports (SSE + `/ws`) are unified to one. Decide the in-app/live-push story so translation/composition/approval events push live too, not only `llm_job`.
- **NOTIF-4 · Delivery guarantee + idempotency.** Critical-path producers use the repo's **transactional outbox** (not fire-and-forget-swallow; `NoopNotifier` silently dropping is a leak); the `notifications` table carries a **`(user_id, dedup_key)` unique** so AMQP requeue and double-notify can't create duplicate rows.
- **NOTIF-5 · User preference / opt-out.** A per-user notification settings table (per-user scope key, per the tenancy tiers): per-category mute + email opt-in. None exists today.
- **NOTIF-6 · PII discipline on bodies.** `title`/`body`/`metadata` free text (book titles, LLM error messages, tool names) is the one place server content fans out to a user's devices — apply the PII SDK ([Security SEC-5](./security.md)); define what may enter each field.

## Enforcement

| Rule | Status | Gate |
|---|---|---|
| NOTIF-1 envelope | **to build (P1)** | `contracts/notifications/envelope.{go,yaml}` + generated mirrors + a snapshot test (model: `contracts/alerts/`) |
| NOTIF-2 category enum on all ingress | **to build (P1)** | one SoT enum imported by both ingress paths + a contract test asserting HTTP and AMQP validate identically; **P0 fix-now:** add `mcp_approval`/`llm_job`/… and reconcile the consumer's raw-SQL bypass |
| NOTIF-4 dedup + outbox | **ENFORCED** | `UNIQUE(user_id, dedup_key)` partial-unique shipped (P2·C); **producer-outbox wiring shipped** (D-C-PRODUCER-OUTBOX `99b800bf9`) — translation/composition/auth write the notification into a transactional outbox; worker-infra's relay delivers `aggregate_type='notification'` rows to `/internal/notifications` with retry, idempotent via a deterministic `dedup_key`. Live end-to-end redelivery proof → `D-C-PRODUCER-OUTBOX-LIVE-SMOKE` (scratch stack) |
| NOTIF-2 no-silent-drop | **to build (P1)** | a producer→consumer wiring test: every category a producer emits is accepted by the consumer (the Agent-Extensibility no-silent-no-op rule) |

## Checklist — a new notification producer
- [ ] Uses the shared envelope (NOTIF-1); category is in the SoT enum (NOTIF-2)
- [ ] Declares channels; doesn't hand-pick transport (NOTIF-3)
- [ ] Emits via transactional outbox with a dedup key (NOTIF-4)
- [ ] Honors per-user opt-out (NOTIF-5)
- [ ] Body/metadata PII-checked (NOTIF-6)
- [ ] A wiring test proves the category is accepted end-to-end (no silent drop)
