# knowledge-service

FastAPI service providing multilingual, project-scoped memory context for LoreWeave chat sessions.

## Scope

This repository is being built incrementally across three tracks (see
[`docs/03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md`](../../docs/03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md)).

**Current status: Track 1 / Phase K0 — scaffold only.**

K0 ships plumbing only: config, logging, DB pools, internal auth, `/health`.
No business logic. No schemas. No extraction. See Track 1 plan for subsequent
phases.

## Ports

- Internal container port: `8092`
- External host port: `8216`
- Gateway route: `GET /v1/knowledge/*` via `api-gateway-bff`

## Environment variables

Required (service fails to start if missing):

- `KNOWLEDGE_DB_URL` — asyncpg DSN for `loreweave_knowledge`
- `GLOSSARY_DB_URL` — asyncpg DSN for `loreweave_glossary` (read-only)
- `INTERNAL_SERVICE_TOKEN` — shared secret for `/internal/*` routes
- `JWT_SECRET` — HS256 secret used by public `/v1/*` routes (added in K7)

Optional:

- `REDIS_URL` — default `redis://redis:6379`
- `LOG_LEVEL` — default `INFO`
- `PORT` — default `8092`

## Run locally

From the repo root:

```bash
docker compose -f infra/docker-compose.yml up -d knowledge-service
curl http://localhost:8216/health
```
