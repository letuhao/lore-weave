# `migrations/meta/` — `loreweave_meta` schema migrations

> **Owner:** foundation cycle 2 (L1.A-1) and onward.
> **Parent layer plan:** `docs/plans/2026-05-29-foundation-mega-task/L1A_meta_tables.md` §0 partition + §1 routing+lifecycle.

## Conventions

- Filename: `NNN_table_name.up.sql` + `NNN_table_name.down.sql` (numeric prefix, snake_case table).
- Sequence number monotone across cycles; cycle 2 ships `001..008`.
- Every `.up.sql` ends with `INSERT INTO instance_schema_migrations` for self-tracking only AFTER `instance_schema_migrations` itself is created (so 002 onward is recorded; 002 records 001+002).
- Every `.down.sql` is the inverse (`DROP TABLE IF EXISTS ... CASCADE`); irreversible operations (e.g., audit data) call this out at the top.
- All audit tables (`*_audit`, `*_log`) MUST have:
  - `REVOKE UPDATE, DELETE ON <table> FROM app_service_role, app_admin_role;`  (S04 §12T.4 append-only)
  - timestamp + actor columns
  - retention class comment in header

## Application

Migrations apply against the `loreweave_meta` database, created externally (cycle 1 docker-compose stack via `infra/docker-compose.meta-ha.yml`). For local dev:

```bash
PGPASSWORD=postgres psql -h 127.0.0.1 -p 15432 -U postgres -d postgres \
  -c "CREATE DATABASE loreweave_meta;"
PGPASSWORD=postgres psql -h 127.0.0.1 -p 15432 -U postgres -d loreweave_meta \
  -f migrations/meta/001_reality_registry.up.sql
# … etc.
```

## Cycle 2 — L1.A-1 Routing + Lifecycle (this cycle)

| # | Table | Source §  |
|---|---|---|
| 001 | `reality_registry` | L1A §1.1 |
| 002 | `instance_schema_migrations` | L1A §1.2 |
| 003 | `publisher_heartbeats` | L1A §1.3 |
| 004 | `lifecycle_transition_audit` | L1A §1.4 |
| 005 | `reality_close_audit` | L1A §1.5 |
| 006 | `archive_verification_log` | L1A §1.6 |
| 007 | `reality_migration_audit` | L1A §1.7 |
| 008 | `session_cost_summary` | Q-L1A-1 hybrid (meta rollup table only; rollup worker later) |

## Roles assumed to exist (created in a future infra-bootstrap migration)

- `app_service_role` — normal service writers via `MetaWrite()`
- `app_admin_role` — admin-cli + retention crons
- `app_readonly_role` — SRE/forensics readers

The REVOKE statements at the end of each audit `.up.sql` are conditional via `DO $$ ... EXCEPTION ... END $$` so they're idempotent in the dev stack where roles may not yet exist (cycle 1 docker-compose ships single `postgres` superuser).
