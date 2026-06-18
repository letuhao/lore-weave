# Plan — GDPR Art.33 breach rail: broker emitter (108) + durable monitor (107)

**Scope:** 108 `D-BREACH-BROKER-EMITTER` + 107 `D-BREACH-DURABLE-STORE`. **incident-bot only.**
**106 `D-BREACH-DELIVERY-CONSUMER` is SPLIT to its own task** — `notification-service` (the
assumed home) turned out to be the wrong fit: a separate module (`github.com/loreweave/notification-service`,
novel-platform), RabbitMQ-based (`loreweave.events`, key `user.*.llm.#`), writing per-**user** FE
`notifications`. A DPO breach notice is an internal compliance alert on the foundation **Redis**
backbone — not a per-user FE notification. 106 needs its own delivery-home design (recorded in DEFERRED).
**Cadence:** human-in-loop + /review-impl. **Size:** gate XL (kept; effectively M after the 106 split).

## Context
incident-bot 072 emits 3 breach lifecycle events via the `breach.EventEmitter` interface; the default
`StructuredEmitter` writes JSON lines to stdout (a transport stand-in), and the deadline `Monitor` is
in-process (a restart loses open breaches → the 72h reminder can be lost — a legal-deadline gap).

## Design
### D1 — RedisEmitter (108)
New `breach.RedisEmitter` implementing `breach.EventEmitter`: validate-before-emit (fail-closed, like
`StructuredEmitter`), then `XADD` to `lw.incidents.breach` with fields `{event_type, incident_id,
payload=<full event JSON>}` (mirrors `meta-outbox-relay/pkg/redisemit`). `main.go` selects the emitter:
`REDIS_URL` (or `LW_BREACH_STREAM_REDIS`) set → `RedisEmitter`; else `StructuredEmitter` (dev/no-broker).
The stream is the durable log 107 + the future 106 consumer both read. Adds `redis/go-redis/v9` to
incident-bot's go.mod.

### D2 — durable monitor via boot-replay (107)
incident-bot STAYS STATELESS (Q-L7-1: no DB). On boot (only when the RedisEmitter is active),
`ReplayOpenBreaches` `XRANGE - +` over `lw.incidents.breach`, reconstructs still-open breaches, and
`monitor.Track`s each before `monitor.Run`. The Redis stream (AOF/RDB-persisted) is the durable store —
`GDPRBreachOpenedV1` is the replay anchor (as the producer's comments already promised).

Reconstruction is a **pure function** `reconstructOpen(events) []*BreachRecord` (unit-tested without
Redis): collect `gdpr.breach.opened.v1` by incident_id; collect incident_ids with a
`gdpr.breach.deadline.v1` **missed** event into a `missedSet`; return opened breaches NOT in `missedSet`
as `BreachRecord{IncidentID, DetectedAt, Deadline, DataCategories, AffectedCount}`. A `missed` breach is
terminal (the monitor prunes it), so it is not re-tracked. **At-least-once** caveat: replay cannot know
whether an `approaching` reminder fired pre-restart, so a duplicate approaching reminder is possible —
acceptable (a duplicate deadline reminder is safe; missing one is not). The thin `XRANGE` I/O wrapper is
covered by a real-Redis-gated roundtrip test.

### D3 — no metrics surface (kept minimal)
incident-bot's main is a skeleton with no prometheus registry; this slice stays log-based (slog) to avoid
expanding the observability-inventory surface. A breach metrics surface is deferred.

## Files
- `services/incident-bot/internal/breach/redis_emitter.go` (+ `_test.go`)
- `services/incident-bot/internal/breach/replay.go` (+ `_test.go` — pure `reconstructOpen` unit tests + a Redis-gated roundtrip)
- `services/incident-bot/cmd/incident-bot/main.go` (emitter selection + boot-replay wiring)
- `services/incident-bot/go.mod` / `go.sum` (+ go-redis/v9)
- Lint allowlists IF the full matrix flags them: `scripts/outbox-event-emit-lint.sh` (the XADD is to
  `lw.incidents.breach`, NOT an `xreality.*` spine topic — exempt incident-bot if the lint is broad) and
  `scripts/dependency-registry-lint.sh` (`redis.NewClient` — register/allowlist like meta-outbox-relay).
- `docs/deferred/DEFERRED.md` (106 re-scoped with the notification-service finding; 107/108 → ADDRESSED) + `docs/sessions/SESSION_PATCH.md`.

## Verification
- `go build/vet/test` incident-bot; gofmt; language-rule lint (incident-bot already `go`).
- Unit: `reconstructOpen` (opened→tracked; opened+missed→skipped; empty; dup-opened); RedisEmitter
  field-shaping + validate-before-emit; emitter selection.
- **Live smoke (real Redis, gated on `INCIDENT_TEST_REDIS_URL` → dev infra-redis-1:6399):** emit
  opened+deadline events → `ReplayOpenBreaches` → assert the open set (a missed breach excluded). This is
  the emit→stream→replay roundtrip — the durability claim proven on real Redis.
- Full 15-lint matrix (per the 111 lesson — run the WHOLE matrix; new redis dep + XADD are new surfaces).
- `/review-impl` before POST-REVIEW.

## Deferred / re-scoped
- `D-BREACH-DELIVERY-CONSUMER` (106, HIGH) → re-scoped: NOT notification-service (wrong module/transport/
  semantics); needs a foundation-side delivery consumer (reuse incident-bot's `war_room` Slack provider
  for the DPO compliance channel, pluggable Notifier, delivery-confirmed durable record), kept separate
  from the emit path per Q-L7-1. Its own task.
- Breach metrics surface (emitted/replayed counters) — deferred with D3.
