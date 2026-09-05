---
runbook_id: glossary-service/down
version: 1
owner: sre-team
applies_to_alerts: []
applies_to_incidents: []
applies_to_services: [glossary-service, knowledge-gateway, knowledge-service, translation-service, composition-service]
last_verified: 2026-08-10
last_verified_by: knowledge-architecture-refactor
verification_method: reading_review
next_verification_due: 2026-11-10
severity_hints: [sev1, sev2]
dry_run_required_for_destructive: false
related_runbooks: [knowledge-gateway/down, knowledge-service/down]
external_access_needed: []
born_from_incident_id: null
shipped_cycle: null
locked_decisions_consumed: []
---

# glossary-service — down

> **Not drilled.** Written from the code paths as the F5 precondition for the KAL owning
> writes (plan T29). Upgrade `verification_method` after the first real page or drill.

## TL;DR (30 seconds)

glossary-service is the **write sink** for every KAL command and the SSOT for entities and
facts. When it is down the correct behaviour is **refuse writes loudly** — degraded mode
`read_only`, not `limited`. A command accepted while this service is down is a command lost,
and no later read repairs that.

## Why `critical_write` and why it matters here

Its `retry_class` is `critical_write` rather than `idempotent`. Fact appends and entity
lifecycle transitions are the two things this platform cannot silently drop: T27 and T28 were
two full tasks spent closing exactly this class of divergence on the *emit* side (a state
change that reached no consumer). Losing the write itself is the same failure one layer up.

## Symptoms

- KAL `/v1/kal/books/*/facts/*` and entity commands 502.
- Translation staleness stops advancing (`glossary.entity_updated` stops flowing).
- composition-service cast reads empty.
- knowledge-service's glossary_sync consumer idles — **expected**, not a second incident.

## Triage

1. Service up? `docker compose ps glossary-service`, `GET /health/ready`.
2. **Postgres reachable?** This service owns `loreweave_glossary`. A DB outage presents as a
   glossary outage — check the DB before restarting the service.
3. **Outbox backing up?** `SELECT count(*) FROM outbox_events WHERE published_at IS NULL;`
   A growing unpublished count with a healthy service means the *relay* is the problem, not
   this service — the writes are committed and safe; propagation is delayed.

## Degraded mode: `read_only`

- The KAL must **reject** command verbs with the downstream status, never a synthesised 200.
  `kal/downstream.ts` already maps 4xx through faithfully and 5xx → 502; keep it that way.
- Reads that do not touch glossary (KG neighborhood, retrieve) keep serving.
- Producers retry from their own outbox. Do **not** add a queue in the KAL.

## The recovery hazard worth knowing

Writes that **committed** before the outage are safe: the outbox is transactional, so the row
and its event landed together or not at all. On recovery the relay drains the backlog and
consumers converge. That is the design working, and it means **the correct action after
recovery is usually to wait and watch the backlog drain, not to replay anything by hand.**

A hand-replay of producer commands on top of a draining outbox is how you get duplicate facts —
`appendFact` is not idempotent.

## Verify recovery

```
GET  /v1/kal/books/{book_id}/entities/{entity_id}/facts    # read path
```

Then confirm the outbox is draining (unpublished count falling), and that
`glossary.entity_updated` is arriving on `loreweave:events:glossary`.
