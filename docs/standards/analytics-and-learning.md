# Analytics & Learning Standard

**Status:** ACTIVE (rules) · enforcement to build — see §Enforcement · **Date:** 2026-07-04
**Governs:** how engagement analytics (statistics-service) and the feedback/learning loops (learning-service + knowledge salience) consume cross-service signal, so the read-models stay single-owner and the correction events don't silently drift. Indexed in [`README.md`](./README.md); current-state in [audit](../plans/2026-07-04-enterprise-hardening-audit.md#area-6--analytics--learning).

> **Why.** Both `statistics-service` and `learning-service` exist and run. Statistics is already consolidated (one owner, event-sourced; book-service migrated off local stats) and mainly needs its event contract frozen. Learning is fragmented across **two independent loops** (learning-service's cross-service eval flywheel + knowledge-service's in-service salience) plus **five per-service correction "capture" sites with no single event contract** — so a producer drift fails silently at the consumer (`build_dispatcher` registers a handler per event name; a renamed/unregistered event is ignored).

## Rules

### Statistics (engagement analytics)
- **STAT-1 · One owner, others only emit.** `statistics-service` owns engagement aggregates/leaderboards. Every other service **emits an outbox event, never stores its own aggregate** (book-service already migrated — this codifies it so it can't regress).
- **STAT-2 · Frozen event contract.** The producer→statistics event payloads (`book.viewed`, `reading.progress`, `chapter.translated`, `book.rated`, `voice.turn`, …) are a committed cross-service schema with a consumer field-assertion test (joined only by a JSON string today).
- **STAT-3 · Explicit boundary vs usage-billing.** "Engagement analytics" (statistics-service) and "USD spend metering" (usage-billing-service) are distinct axes with no shared tables; "usage metrics" must not be used ambiguously across both.

### Learning (feedback / eval flywheel)
- **LEARN-1 · One correction/feedback event contract.** Every producer (chat, composition, translation, glossary, knowledge) conforms to one schema: required fields (`target_type`/`id`, `op`, structural before/after, content-hash, actor, origin), **redact-by-default** (hash, not raw content — already the learning-service convention but enforced only at the consumer), and an idempotency key (`origin_service`, `origin_event_id`).
- **LEARN-2 · No silent drop at the consumer.** Every correction event type a producer emits has a registered `build_dispatcher` handler — asserted by a wiring test (the [Agent Extensibility](./agent-extensibility.md) no-silent-no-op rule applies verbatim). A renamed/unregistered event failing silently is a defect.
- **LEARN-3 · Two loops, documented boundary.** knowledge-service salience (in-service adaptive ranking) and learning-service (cross-service eval flywheel) are **distinct**; document it. Whether salience's `feedback_weight` should source from learning-service's quality signal is an open integration decision (currently it does not — a latent gap, not a bug).
- **LEARN-4 · Judges obey the provider rules.** learning-service's LLM judges resolve models via provider-registry (BYOK) — the [provider-gateway + no-hardcoded-model](./README.md#a-platform-build-standards) rules bind; this standard just references them.

## Enforcement

| Rule | Status | Gate |
|---|---|---|
| STAT-2 event contract | **to build (P1)** | committed producer→statistics payload schema + consumer field-assertion test |
| STAT-1 one-owner | **to build (P2)** | a lint/review rule flagging a non-statistics service that stores an engagement aggregate |
| LEARN-1 correction contract | **to build (P1)** | one shared correction-event schema + redaction-at-source + idempotency-key |
| LEARN-2 no-silent-drop | **to build (P1)** | producer→`build_dispatcher` handler-coverage wiring test |
| LEARN-4 provider rules | **ENFORCED** | `scripts/ai-provider-gate.py` |

## Checklist — a new producer of a stat/correction event
- [ ] Emits an outbox event; does NOT store its own aggregate (STAT-1)
- [ ] Payload matches the committed event schema (STAT-2 / LEARN-1)
- [ ] Correction content redacted at source (hash, not raw) + idempotency key (LEARN-1)
- [ ] A wiring test proves the consumer has a handler for the event (LEARN-2)
- [ ] LLM judge/scorer resolves the model via provider-registry (LEARN-4)
