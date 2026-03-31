# Data Re-Engineering — Detailed Task Breakdown

> **Parent plan:** `101_DATA_RE_ENGINEERING_PLAN.md`
> **Created:** 2026-04-01
> **Method:** Impact-first discovery cycles. Each cycle picks a task, traces all affected files, creates sub-tasks.

---

## Discovery Cycle 1: Postgres 18 Upgrade + uuidv7 Migration

### Impact Map

**9 migration files** need `gen_random_uuid()` → `uuidv7()`:

| Service | File | Tables | pgcrypto Used For |
|---------|------|--------|-------------------|
| auth-service | `internal/migrate/migrate.go` | 4 tables | only `gen_random_uuid()` |
| book-service | `internal/migrate/migrate.go` | 3 tables | only `gen_random_uuid()` |
| sharing-service | `internal/migrate/migrate.go` | 0 (FKs only) | only extension line |
| catalog-service | `internal/migrate/migrate.go` | 0 (TEXT PK) | not used |
| provider-registry | `internal/migrate/migrate.go` | 5 tables | only `gen_random_uuid()` |
| usage-billing | `internal/migrate/migrate.go` | 3 tables | only `gen_random_uuid()` |
| glossary-service | `internal/migrate/migrate.go` | 8 tables | only `gen_random_uuid()` |
| translation-service | `app/migrate.py` | 3 tables | not used |
| chat-service | `app/db/migrate.py` | 3 tables | not used |

**Total: 29 tables across 9 services. pgcrypto only used for `gen_random_uuid()` — safe to replace with `uuidv7()`.**

**Note:** Encryption in auth-service, provider-registry, usage-billing uses Go `crypto/*` packages (application-level), NOT Postgres `pgcrypto`. No impact from removing the extension.

### Infrastructure Impact

| File | Change |
|------|--------|
| `infra/docker-compose.yml` | `postgres:16-alpine` → `postgres:18-alpine`, add `PGDATA` env, add Redis service |
| `infra/db-ensure.sh` | Add `loreweave_events` database |
| Docker volumes | Delete `loreweave_pg` volume (clean break, PG18 data format incompatible) |

---

## Detailed Sub-Tasks

### D0: Pre-Flight Validation

```
D0-01  Spin up postgres:18-alpine, test uuidv7() and JSON_TABLE availability
       Files: none (manual psql test)
       Test: SELECT uuidv7();
             SELECT * FROM JSON_TABLE('{"a":1}'::jsonb, '$' COLUMNS (a INT PATH '$.a')) AS jt;
       Pass/fail gate: both must return results

D0-02  Run ALL 9 service migrations against PG18
       Method: start PG18, create all DBs, run each service with migration-only mode
       or manually execute migration SQL from each migrate.go/migrate.py
       Files to read: all 9 migration files listed above
       Pass/fail: all CREATE TABLE statements succeed

D0-03  Test JSON_TABLE inside PL/pgSQL trigger function
       File: create test SQL script (new file: infra/test-pg18-features.sql)
       Test: CREATE TABLE + trigger using JSON_TABLE + INSERT + verify extracted data
       Pass/fail: trigger fires, data extracted correctly

D0-04  Test pgx v5 JSONB scanning with json.RawMessage
       File: create test Go program (new file: services/book-service/cmd/pg18test/main.go)
       Test: INSERT JSONB → SELECT → scan as json.RawMessage → json.Marshal → verify inline JSON
       Pass/fail: response contains inline JSON object, not base64 string
```

### D1-01: Postgres 18 + Redis in docker-compose

```
D1-01a  Update docker-compose Postgres image + config
        File: infra/docker-compose.yml
        Changes:
          - image: postgres:16-alpine → postgres:18-alpine
          - Add: PGDATA: /var/lib/postgresql/18/docker
          - Volume stays: loreweave_pg:/var/lib/postgresql

D1-01b  Add Redis service to docker-compose
        File: infra/docker-compose.yml
        Add:
          redis:
            image: redis:7-alpine
            ports: ["6399:6379"]
            volumes: [loreweave_redis:/data]
            healthcheck: redis-cli ping
        Add volume: loreweave_redis

D1-01c  Add loreweave_events database to db-ensure.sh
        File: infra/db-ensure.sh
        Add: loreweave_events to DATABASES list

D1-01d  Delete old Postgres volume (documented step, not code)
        Command: docker volume rm infra_loreweave_pg
        Note: This is a manual step during migration execution
```

### D1-02: Clean Schema — uuidv7 everywhere + JSONB body

```
D1-02a  auth-service migration: gen_random_uuid() → uuidv7(), drop pgcrypto
        File: services/auth-service/internal/migrate/migrate.go
        Changes: 4 table PKs, remove CREATE EXTENSION pgcrypto line

D1-02b  book-service migration: gen_random_uuid() → uuidv7(), JSONB body, drop pgcrypto
        File: services/book-service/internal/migrate/migrate.go
        Changes:
          - 3 table PKs → uuidv7()
          - chapter_drafts.body: TEXT → JSONB
          - chapter_drafts.draft_format: DEFAULT 'plain' → DEFAULT 'json'
          - chapter_revisions: add body_format column, id → uuidv7()
          - chapter_revisions.body: TEXT → JSONB
          - Add virtual column: block_count
          - Remove pgcrypto

D1-02c  sharing-service migration: drop pgcrypto
        File: services/sharing-service/internal/migrate/migrate.go
        Changes: remove CREATE EXTENSION pgcrypto (no tables use UUID gen)

D1-02d  provider-registry migration: gen_random_uuid() → uuidv7(), drop pgcrypto
        File: services/provider-registry-service/internal/migrate/migrate.go
        Changes: 5 table PKs, remove pgcrypto

D1-02e  usage-billing migration: gen_random_uuid() → uuidv7(), drop pgcrypto
        File: services/usage-billing-service/internal/migrate/migrate.go
        Changes: 3 table PKs, remove pgcrypto

D1-02f  glossary-service migration: gen_random_uuid() → uuidv7(), drop pgcrypto
        File: services/glossary-service/internal/migrate/migrate.go
        Changes: 8 table PKs, remove pgcrypto

D1-02g  translation-service migration: gen_random_uuid() → uuidv7()
        File: services/translation-service/app/migrate.py
        Changes: 3 table PKs (no pgcrypto to remove)

D1-02h  chat-service migration: gen_random_uuid() → uuidv7()
        File: services/chat-service/app/db/migrate.py
        Changes: 3 table PKs (no pgcrypto to remove)

D1-02i  Verify: start all services, migrations run, all healthchecks pass
```

---

## Cycle 1 Summary

| Phase | Sub-tasks | New files | Modified files |
|-------|-----------|-----------|---------------|
| D0 | 4 | 2 (test scripts) | 0 |
| D1-01 | 4 | 0 | 2 (docker-compose, db-ensure.sh) |
| D1-02 | 9 | 0 | 9 (all migration files) |
| **Total** | **17** | **2** | **11** |

---

## Remaining Cycles (to be completed in subsequent sessions)

| Cycle | Focus | Tasks |
|-------|-------|-------|
| 2 | D1-03: chapter_blocks + trigger | Trigger SQL, test data, edge cases |
| 3 | D1-04 + D1-05: outbox + events schema | outbox table, events DB schema, pg_notify |
| 4 | D1-06: book-service JSONB refactor | All 8 handlers, test rewrites |
| 5 | D1-07 + D1-08: createChapter + internal API | Plain text import, text_content field |
| 6 | D1-09 + D1-10: worker-infra service | Go project scaffold, task registry, relay |
| 7 | D1-11: Frontend JSONB save/load | _text snapshots, TiptapEditor changes |
| 8 | D1-12: Integration test | End-to-end verification |
