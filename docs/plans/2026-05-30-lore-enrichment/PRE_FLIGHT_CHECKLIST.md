# Lore-Enrichment — Pre-Flight Checklist

> Manual sign-off BEFORE RAID cycle execution begins. Mostly verified at C0/C1; some are human-confirm.

## Environment & isolation
- [ ] On branch `lore-enrichment/foundation`; **no edits** to `world-service`/`game-server` or other agents' files (isolation rule).
- [ ] `infra/docker-compose.yml` can bring up dependencies: postgres, redis, neo4j, **knowledge-service**, **glossary-service**, **book-service**, provider-registry, api-gateway-bff.
- [ ] New DB `loreweave_lore_enrichment` created (or migration creates it).
- [ ] Service port assigned + free (proposed internal 8093 / host 8217 — **confirm not taken**) and gateway route registered.

## Secrets / config (service fails to start if missing)
- [ ] `LORE_ENRICHMENT_DB_URL`, `INTERNAL_SERVICE_TOKEN`, `JWT_SECRET` set.
- [ ] Read access DSNs / tokens for knowledge-service, glossary, book-service.
- [ ] Provider-registry configured (no hardcoded model names; LLM/embedding via adapter layer).
- [ ] `REDIS_URL` reachable for events + cost tracking.

## Upstream readiness
- [ ] knowledge-service exposes graph / graph-stats / context / embedding-model for a test project.
- [ ] glossary `POST /books/{book_id}/extract-entities` + wiki generate reachable with internal token.
- [ ] book-service chapter/hierarchy read reachable.
- [ ] A Fengshen Yanyi test book/project seeded for the demo path (book + initial glossary + extracted KG).

## RAID operational
- [ ] `.raid/active-task.yaml` validates: `python scripts/raid/task_config.py validate` → exit 0.
- [ ] Quota profile present (`contracts/raid/quota-profile.yaml`); cost-cap policy understood.
- [ ] Runtime logs initialized: `docs/raid/CYCLE_LOG.md`, `ESCALATIONS.md`, `QUOTA_LOG.jsonl`, `docs/audit/AUDIT_LOG.jsonl`.
- [ ] pre-commit hook decision: install RAID/workflow-gate hook on this branch or rely on manual gate.

## Cost / safety
- [ ] P1 (template+retrieval) only until the eval gate (C12) exists; fabrication/re-cook stay disabled.
- [ ] Secret-scan + prod-isolation lint wired for DPS cycles.
