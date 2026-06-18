# Runbook — Pgbouncer Connection Exhaustion

> **Owner:** Platform SRE
> **Pages:** `lw_pgbouncer_cl_active / lw_pgbouncer_cl_max > 0.9` for > 5m
> **Last verified:** 1970-01-01 (stub — full drill in cycle 7 SR2/SR3 sub-program)
> **Source:** L1.G.5; companion to `infra/pgbouncer/pgbouncer.ini`

## Capacity recap

Per `infra/pgbouncer/pgbouncer.ini` (locked Q-L1G-1):

```
max_client_conn        5000   ; virtual cap surfaced to app
default_pool_size       25    ; backend conns per (db, user)
reserve_pool_size        5
min_pool_size            5
max_db_connections     500    ; HARD per-host backend cap
pool_mode = transaction
```

App-side, every Go service uses `contracts/meta::DbPoolRegistry` and every
Rust service uses `services/world-service::DbPoolRegistry`. Both reject
configs whose aggregate per-host `backend_cap` exceeds 500.

## What "exhausted" means

Two distinct exhaustion modes — they look similar in dashboards but
require different fixes:

| Mode                | Indicator                                            | Fix                                          |
|---------------------|------------------------------------------------------|----------------------------------------------|
| Virtual exhausted   | `cl_waiting > 0` AND `cl_active < max_client_conn`   | App-side: stop holding TX open, raise pool   |
| Backend exhausted   | `sv_active = max_db_connections` AND `cl_waiting > 0`| Server-side: scale shard OR raise pool cap   |

## Investigation checklist

1. **Pull the snapshot:**

   ```bash
   psql -h 127.0.0.1 -p 16432 -U pgbouncer_admin pgbouncer -c "SHOW POOLS;"
   psql -h 127.0.0.1 -p 16432 -U pgbouncer_admin pgbouncer -c "SHOW CLIENTS;"
   ```

2. **Identify the offender pool.** A single (db, user) at 100% backend
   usage while others are idle indicates an application-side leak (TX
   not closing) on that one database. If MANY pools are at high usage,
   the shard is genuinely over capacity → scale.

3. **Cross-check with the app:**

   ```promql
   sum by (service) (lw_pool_active_connections{shard="pg-shard-0.internal"})
   ```

   The worst offender is your starting suspect.

4. **If it's app-side**: dump the active query list with
   `SHOW CLIENTS` (look for `state=active` with long `connect_time`)
   and grep app logs for the matching `application_name`.

## Transaction-mode constraints (always check these first when something "doesn't work")

pgbouncer is in **transaction** mode (LOCKED Q-L1G-1). The server
connection is returned to the pool at every `COMMIT`/`ROLLBACK`. This
means the following Postgres features will misbehave:

1. **Session-scoped advisory locks** (`pg_advisory_lock` without `_xact_`).
   The lock is held by a server connection that may be reassigned to a
   different client at any time. **Use `pg_advisory_xact_lock` instead**
   (the version that auto-releases at TX end).

2. **`LISTEN` / `NOTIFY`.** A `LISTEN` on a transient server connection
   will silently miss notifications when the connection is reassigned.
   **Use a dedicated session-mode pgbouncer instance (different listen
   port) for LISTEN/NOTIFY consumers.** Foundation V1 does not need
   one — every consumer uses Redis Streams (L1.F).

3. **`SET` outside a TX.** Setting `search_path` or any other GUC at
   the session level is invisible to the next client landing on that
   server connection. **Use `SET LOCAL` inside an explicit BEGIN block**
   for per-reality schema scoping.

4. **Unprepared statements.** Postgres's protocol-level prepared
   statements are cached server-side, but pgbouncer transaction mode
   doesn't carry the prepare across connections. Set
   `default_pool_size = 0` for a carve-out pool if you genuinely need
   prepared statements (rare in this codebase).

The Rust `db_pool::PoolRole` enum (and the Go mirror) intentionally has
NO `SessionWriter` role variant. Don't add one.

## Resolution playbook

### Mode 1 — virtual exhausted (`cl_waiting > 0`)

Almost always app-side. Sequence:

1. Look for the leaky service (step 3 above).
2. Bounce the service (kill its pool's idle conns):
   ```bash
   kubectl rollout restart deployment/<service-name>
   ```
3. If the leak repeats post-restart, raise a `kind=defect` ticket
   against the service — there's a leaked TX in code.
4. Do NOT raise `max_client_conn` to mask a leak. The cap exists to
   keep the leaky service from monopolizing the cluster.

### Mode 2 — backend exhausted (`sv_active = max_db_connections`)

1. Capacity-planner snapshot:
   ```sql
   SELECT * FROM shard_utilization WHERE shard_id = 'pg-shard-0.internal';
   ```
   (table lands in cycle 7 — until then, manually count
   `reality_registry` rows on the affected shard).

2. If shard utilization ≥ 0.80 → provision a new shard (V1 manual via
   docker-compose; V1+30d via Terraform per Q-L1C-1).

3. If shard utilization < 0.80 → backend cap was set too tight. Verify
   the `db_pool.rs` MAX_BACKEND_CONNECTIONS / Go MaxBackendConnections
   constants agree with `pgbouncer.ini::max_db_connections`. They should
   all be 500 — config drift is the most common cause.

## Drills

- **Quarterly** (cycle 7 sub-program): kill a single shard's
  pgbouncer instance during a load test; verify automatic restart
  via systemd (V1 docker-compose: `docker compose restart pgbouncer`),
  app reconnect within 30s, no lasting data loss.
- **Annual** (post-V1+30d Terraform): swap a shard's pgbouncer
  instance to pgcat (`Q-L1G-1` re-eval trigger); verify transaction
  semantics preserved before flipping production.
