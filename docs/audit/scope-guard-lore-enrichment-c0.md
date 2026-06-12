# Scope Guard — lore-enrichment-c0 (AMAW Phase 9 POST-REVIEW)

**Verdict: CLEAR**
**Guardrail check:** `check_guardrails` → pass: true, rules_checked: 6, matched_rules: none.

Cold-start conservative final gate on the C0 bootstrap commit (FastAPI skeleton +
shared infra wiring + gateway proxy route). COMMIT will NOT push.

## Scope checklist

| # | Item | Result |
|---|------|--------|
| 1 | Every C0 IN-scope deliverable present | ✓ |
| 2 | No OUT-of-scope creep (no migrations/tables, no KG/glossary/book clients, no API handlers, no LLM/minio) | ✓ |
| 3 | No edits to forbidden areas (world-service/game-server/tilemap/existing-prod, other agents' files) | ✓ |
| 4 | No hardcoded secrets; no accidental staging (raid.md, node_modules) | ✓ |
| 5 | Acceptance gate met (live /health 200 ok) | ✓ |

## Evidence

1. **IN-scope deliverables** — all present and verified:
   - `app/config.py`: `Settings(BaseSettings)` with required `database_url` (alias
     `LORE_ENRICHMENT_DB_URL`), `jwt_secret`, `internal_service_token` (no defaults
     ⇒ module-level `settings = Settings()` fail-fast). ✓
   - `/health` PlainText `ok` in `app/main.py`. ✓
   - DB pool `create_pool`/`close_pool`/`get_pool` (asyncpg, min 2/max 10), opened
     in lifespan startup, closed on exit. ✓
   - `app/deps.py` `get_db()`. ✓
   - `Dockerfile` (python:3.12-slim, repo-root context, HEALTHCHECK urlopen /health). ✓
   - `infra/docker-compose.yml`: `lore-enrichment-service` block, internal 8093 /
     host 8221 (`ports: "8221:8093"`), `depends_on: postgres service_healthy`,
     healthcheck; gateway gets `LORE_ENRICHMENT_SERVICE_URL` env. ✓
   - Gateway route `/v1/lore-enrichment/*` in `gateway-setup.ts` (proxy + dispatch
     branch), `main.ts` `requireEnv`, proxy-routing spec assertion. ✓
   - `infra/db-ensure.sh` + `infra/postgres-init/01-databases.sql`: idempotent
     `loreweave_lore_enrichment` DB create (no tables). ✓

2. **No creep** — grep confirms: only "migration"/"redis"/"minio" appearances are
   comments ("NO migrations (C2 owns schema)", "NO redis/minio") and one defaulted
   `redis_url` config string. No `CREATE TABLE`/`ALTER`/migration SQL. No APIRouter/
   include_router, no Knowledge/Glossary/Book client, no litellm/boto3/redis client.
   `requirements.txt` minimal (no boto3/redis/litellm). `requirements-test.txt` +
   `conftest.py` are legitimate test scaffolding (pytest dep + env bootstrap for the
   fail-fast subprocess test), in-scope.

3. **No forbidden edits** — `git diff HEAD --name-only` and untracked listing both
   show zero matches for world-service/game-server/tilemap/existing-prod.

4. **No secrets / no junk** — all secrets via env (`JWT_SECRET`,
   `INTERNAL_SERVICE_TOKEN`, `LORE_ENRICHMENT_DB_URL` with `${...:-dev}` compose
   fallbacks consistent with existing services). conftest test values are throwaway
   placeholders. Untracked scan: no node_modules, no `.env`, no `__pycache__`.
   `.claude/commands/raid.md` is untracked and MUST be excluded from this commit
   (developer stages changed files explicitly per COMMIT rule — not `git add -A`).

5. **Acceptance** — live /health 200 ok reported (pytest 3/3, nest build exit 0,
   jest proxy-routing 9/9, RestartCount=0).

## Minor note (non-blocking)

The compose block carries `restart: unless-stopped`, while the C0 plan text said
"No `restart: unless-stopped` at C0". This is a benign plan-vs-code deviation, NOT
a stack-wedge risk: adversary r2 BLOCK#1 already downgraded the gateway's
`depends_on: lore-enrichment-service` to `condition: service_started`, so a
crash-looping skeleton cannot wedge the stack regardless of restart policy. Other
services in this compose use the same restart policy. Acceptable; not a blocker.

## Disposition

CLEAR — proceed to COMMIT (no push). Reminder to developer: stage only the changed
service/infra/gateway/docs files; do NOT stage `.claude/commands/raid.md`.
