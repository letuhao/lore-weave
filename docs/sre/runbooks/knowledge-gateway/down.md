---
runbook_id: knowledge-gateway/down
version: 1
owner: sre-team
applies_to_alerts: []
applies_to_incidents: []
applies_to_services: [knowledge-gateway, api-gateway-bff, composition-service]
last_verified: 2026-08-10
last_verified_by: knowledge-architecture-refactor
verification_method: reading_review
next_verification_due: 2026-11-10
severity_hints: [sev2]
dry_run_required_for_destructive: false
related_runbooks: [glossary-service/down, knowledge-service/down]
external_access_needed: []
born_from_incident_id: null
shipped_cycle: null
locked_decisions_consumed: []
---

# knowledge-gateway (the KAL) — down

> **Not drilled.** Written from the code paths (`kal/downstream.ts`,
> `kal-read.controller.ts`, `kal-write.controller.ts`) as the F5 precondition for the KAL
> owning writes — plan T29. Nobody has yet taken this service down on purpose and followed
> these steps. Upgrade `verification_method` after the first real page or drill.

## TL;DR (30 seconds)

The KAL is the **only sanctioned caller** of glossary/knowledge `/internal/*` routes (INV-KAL).
When it is down, callers lose knowledge reads and **all fact/entity commands**. Nothing else
can route around it — that is by design, and it is why this is a P1 with a documented degraded
mode rather than a P2.

Reads degrade to *absent context*, which is safe. Writes must be **refused**, not buffered by
the caller — see "Do not" below.

## Symptoms

- `composition-service` builds packs with no cast/canon block (context silently thinner).
- `api-gateway-bff` returns 502 on `/v1/kal/**`.
- Fact-producing workers see 502 on `POST /v1/kal/books/{id}/facts/*`.

## Blast radius

| Consumer | Effect |
|---|---|
| composition-service | context assembly continues **without** KG/canon blocks |
| api-gateway-bff | `/v1/kal/**` 502s to the FE |
| fact producers (extraction, translation) | commands fail; must retry later, not drop |

The glossary and knowledge services are unaffected — they keep serving their own surfaces.
Only the federated KAL contract is gone.

## Triage

1. `docker compose ps knowledge-gateway` / pod status. Restart loop?
2. `GET /health/ready` on the gateway. It forwards the KG temporal capability from
   knowledge-service (T26), so a **ready** gateway with an unhealthy backend still answers —
   check the backends separately (see the two related runbooks).
3. If ready but slow: the KAL calls both backends with a bare `fetch` and **no timeout**
   (`kal/downstream.ts`). A hung backend parks KAL requests until the client gives up. Check
   the backends' latency before suspecting the gateway itself.

## Degraded mode: `limited`

Callers must treat missing knowledge as **missing**, never as empty-and-authoritative:

- composition/chat: omit the KG block; do **not** render "no canon found" as a fact about the
  book.
- Writes: surface the failure to the producer so it retries. A producer that swallows a 502
  loses the fact, and no later read repairs that.

## Do not

- **Do not** let a caller queue KAL commands locally to "replay later". The KAL's write verbs
  are `non_idempotent` at the dep level (`appendFact` applied twice is two facts). Replay
  belongs to the producer's own outbox, which already has the idempotency key.
- **Do not** route around the KAL by calling glossary/knowledge `/internal/*` directly. That
  is INV-KAL, and `scripts/knowledge-http-surface-gate.py` fails the build for it.

## Recovery

Restart the gateway; it is stateless. Confirm with a read that crosses to each backend:

```
GET /v1/kal/books/{book_id}/entities/{entity_id}/neighborhood   # → knowledge-service
GET /v1/kal/books/{book_id}/entities/{entity_id}/facts          # → glossary-service
```

Both returning 200 means both downstream legs are live, which a `/health/ready` alone does not
prove.
