# Plan — 106 D-BREACH-DELIVERY-CONSUMER: the `breach-notifier` service

**Scope:** a NEW standalone foundation service `services/breach-notifier` (Go) that consumes
the `lw.incidents.breach` Redis stream (produced by incident-bot 108), DELIVERS the GDPR
Art.33 DPO notice via a pluggable Notifier, and records a **durable delivery-confirmed**
marker distinct from "emitted" (closing D-BREACH-DELIVERY-CONSUMER). Chosen home (user):
standalone service (own go.mod / DB / migration / ops / config). **Cadence:** human-in-loop +
/review-impl. **Size:** XL. **DB migration:** test-DB only; flagged at POST-REVIEW; not applied
to any non-test DB.

## Context
incident-bot EMITS `gdpr.dpo_notice_required.v1` (+ opened/deadline) to the durable
`lw.incidents.breach` stream (108) but nothing DELIVERS the DPO notice. "DPO notified" today
means "obligation queued + streamed". This service makes it real: deliver + record a
confirmed timestamp. Q-L7-1 (incident-bot decides+emits; a SEPARATE consumer delivers) is
honored by this being a distinct service.

## Design
### D1 — consumer (mirror meta-worker/pkg/consumer + redisconsume)
`internal/consume`: a `MessageSource` (XReadGroup consumer group `breach-notifier` on
`lw.incidents.breach`, MKSTREAM, BUSYGROUP-tolerant; mirror meta-worker/pkg/redisconsume) +
a thin loop: per message, route on `event_type`. Only `gdpr.dpo_notice_required.v1` is
actioned; opened/deadline are ACKed-and-ignored (this consumer group only cares about the
obligation). Deliver-success → ACK; deliver-failure → do NOT ACK (Redis re-delivers); the
record captures the attempt either way.

### D2 — pluggable Notifier (own, stub default + Slack scaffold)
`internal/deliver`: `Notifier` interface `Deliver(ctx, DPONotice) (channel string, err error)`.
- `LogNotifier` (default) — structured-log delivery (dev/no-creds); returns channel="log".
- `SlackNotifier` — fail-closed without `SLACK_BOT_TOKEN` (B6); the real `chat.postMessage`
  HTTP call is a scaffold returning a not-wired error, EXACTLY mirroring incident-bot's
  war_room/slack_provider (the live round-trip is deferred to a live-smoke — no dev creds).
  NOT a cross-module import of incident-bot's internal provider (boundary: each service owns
  its client). main selects Slack when `SLACK_BOT_TOKEN` is set, else LogNotifier.

### D3 — durable delivery-confirmed store (own DB, own migration)
`internal/store`: `DeliveryStore` interface + `PgDeliveryStore`. Migration
`0001_breach_dpo_delivery`: table `breach_dpo_delivery` (incident_id TEXT PK, subject TEXT,
deadline TIMESTAMPTZ, channel TEXT, status TEXT CHECK in (pending,delivered,failed), attempts
INT, last_error TEXT, delivered_at TIMESTAMPTZ NULL, created_at/updated_at). **Idempotent:**
on a notice, if a row with status=delivered exists → skip + ACK (no double-notify); else
attempt, then UPSERT (delivered/failed, attempts++, delivered_at on success). The
delivered_at timestamp is the "confirmed delivery" distinct from the emit — the thing the
deferral demanded.

### D4 — service shell (mirror meta-outbox-relay main.go)
`cmd/breach-notifier/main.go`: config (REDIS_URL, BREACH_NOTIFIER_DB_URL, LW_BREACH_STREAM,
CONSUMER_GROUP/NAME, SLACK_BOT_TOKEN opt, HTTP_ADDR), connect Redis+PG, run migration,
EnsureGroups, consumer loop goroutine + /healthz//readyz//metrics + graceful shutdown.
Prometheus metrics: `lw_breach_delivery_{delivered,failed,skipped_duplicate,iteration_errors}_total`,
`lw_breach_delivery_pending` gauge.

## Files (new service)
- `services/breach-notifier/go.mod` + `go.sum`
- `cmd/breach-notifier/main.go`
- `internal/consume/{source,loop}.go` (+ tests)
- `internal/deliver/{notifier,log,slack}.go` (+ tests)
- `internal/store/{store,pg}.go` (+ PG-gated test)
- `internal/handler/handler.go` (route notice → store-check → deliver → record; + tests)
- `migrations/0001_breach_dpo_delivery.{up,down}.sql`
- `Dockerfile`
- Config: `contracts/language-rule.yaml` (breach-notifier: go), `contracts/service_acl/matrix.yaml`
  (breach-notifier — own DB; add iff the matrix models it / role-grant scan requires the table),
  `contracts/capacity/budgets.yaml` (new worker), `contracts/observability/inventory.yaml` (metrics).
- Reuse: `contracts/incidents` (event types), publisher/pkg/retry (backoff) if useful.

## Verification
- `go build/vet/test` breach-notifier; gofmt; language-rule lint (new go service mapped).
- Unit: notice routing (only dpo_notice_required actioned); Notifier stub + Slack fail-closed;
  store idempotency (delivered → skip); handler (deliver→record delivered+ack; fail→record
  failed+no-ack); nil-dep guards.
- PG-gated (`PIIKMS_TEST_PG_URL`): apply 0001, exercise PgDeliveryStore upsert/idempotency.
- **Live smoke (real Redis + PG, dev infra):** incident-bot-style emit a dpo_notice_required
  to `lw.incidents.breach` → breach-notifier consumes → LogNotifier delivers → breach_dpo_delivery
  row status=delivered. Real Slack delivery deferred (no creds) → `D-BREACH-SLACK-LIVE`.
- **Full 15-lint matrix** (new service touches language-rule + likely service_acl/capacity/
  observability — run the WHOLE matrix per the 111 lesson).
- `/review-impl` before POST-REVIEW.

## Deferred (anticipated)
- `D-BREACH-SLACK-LIVE` — real Slack chat.postMessage round-trip (no dev creds; fold under D-INCIDENT-LIVE-SMOKE).
- 106 → ADDRESSED on completion (delivery + confirmed-record real; Slack transport scaffolded).
