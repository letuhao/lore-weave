---
runbook_id: knowledge-service/down
version: 1
owner: sre-team
applies_to_alerts: []
applies_to_incidents: []
applies_to_services: [knowledge-service, knowledge-gateway, glossary-service, chat-service]
last_verified: 2026-08-10
last_verified_by: knowledge-architecture-refactor
verification_method: reading_review
next_verification_due: 2026-11-10
severity_hints: [sev2]
dry_run_required_for_destructive: false
related_runbooks: [knowledge-gateway/down, glossary-service/down]
external_access_needed: []
born_from_incident_id: null
shipped_cycle: null
locked_decisions_consumed: []
---

# knowledge-service — down

> **Not drilled.** Written from the code paths as the F5 precondition for the KAL owning
> writes (plan T29). Upgrade `verification_method` after the first real page or drill.

## TL;DR (30 seconds)

knowledge-service owns the **derived** KG (Neo4j) and semantic retrieval. It is `idempotent`
from the KAL's side because the KAL only ever **reads** it — knowledge-service's writes arrive
by event, not by call. So an outage here loses *context quality*, never *authored truth*.

The graph is derived from the glossary SSOT. Anything lost while it is down is recoverable by
replaying events; nothing here is the last copy of anything.

## Symptoms

- KAL `neighborhood` / `retrieve` 502.
- Chat and composition build packs without KG context.
- `/health/ready` on the gateway reports `kgTemporal=temporal_unsupported` — the T26 capability
  is forwarded from this service, so its absence changes what the gateway advertises.

## Blast radius

| Consumer | Effect |
|---|---|
| chat-service | answers without graph context — thinner, not wrong |
| composition-service | packs omit KG blocks |
| glossary lifecycle events | **queue on Redis**, consumed on recovery |

## The event backlog is the important part

`glossary.entity_deleted` / `entity_restored` / `entity_purged` / `entity_status_changed` are
consumed here (T27/T28). While this service is down those events **accumulate on the stream**
rather than being lost, and the KG converges when it comes back.

Two things follow:

- **Do not trim the stream** to "clean up" during the incident. Trimming drops lifecycle
  transitions, and a dropped `entity_deleted` leaves a retired entity answering RAG queries
  with nothing that ever corrects it.
- On recovery, watch the DLQ. A handler that fails three times lands there — and a payload-shape
  mismatch shows up as a *silent* DLQ, not an error to the producer. This is exactly how the
  T27 handlers were found to have never worked at all.

## Triage

1. Service up? `GET /health/ready`.
2. **Neo4j reachable?** This service fails-fast on an unreachable Neo4j at startup; a restart
   loop usually means the graph, not the service.
3. **Postgres reachable?** It owns `loreweave_knowledge` (projects, extraction state).
4. Consumer alive? Check for `EventConsumer` lines on `loreweave:events:glossary`.

## Degraded mode: `limited`

Callers omit KG context and say nothing about the graph. A missing graph must never be rendered
as "this book has no entities" — that is a claim about the book, not about the outage.

## Verify recovery

```
GET /internal/books/{book_id}/kg/neighborhood?entity_id={glossary_entity_id}
```

200 with edges (or a clean empty 200 for a cold-start book). Then confirm the glossary stream
backlog is draining and the DLQ is not growing.
