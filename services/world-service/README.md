# world-service

Geography substrate service for the LLM MMO RPG design track (`docs/03_planning/LLM_MMO_RPG/`).

**Owns:** the `world_geometry` aggregate (GEO_001) + the POL_001 / SET_001 / ROUTE_001 activation generators (geography pipeline stages 1–8) — *still unbuilt*, see below — plus the per-reality database lifecycle, which is what this crate actually does today.

> **This file described a "Cycle 0 scaffold — empty-compiling Rust crate, no behavior" until 2026-08-11**, and said the crate was blocked because "the kernel and the foundation tier do not yet exist as code". Both statements had been false for months: `dp-kernel` is ~15k lines and a path dependency of this crate. Corrected rather than deleted, because the stale version is a better argument for reading code over READMEs than any warning would be.

## What is built

| Surface | What it is |
|---|---|
| **HTTP server** (`world-service`) | `POST /internal/v1/realities` + `/livez` `/readyz` `/metrics`, on `crates/service-http`. **Internal only** (invariant I1 — external traffic goes through `api-gateway-bff`); every versioned route is gated on `X-Internal-Token`. Contract: [`contracts/api/world/provisioning.v1.yaml`](../../contracts/api/world/provisioning.v1.yaml), enforced by `tests/route_conformance.rs`. |
| `provisioner` · `provision_flow` · `capacity_glue` · `capacity_planner` | The 11-step `provision_reality` flow, shard placement under a per-shard advisory lock, and the resume-before-place logic. `provision_flow` is shared by the HTTP route and the `provision` worker so neither restates the other. |
| `deprovisioner` · `orphan_scan` | Teardown, and the nightly reaper's classification. |
| `reality_seeder` | L5.G — canon/book/knowledge readers, translation gate, checkpointing, lifecycle transitions. |
| `embedding_queue` | L3.I — drains the queue, writes `VECTOR(1536)`, audits every provider call. Has its **own** axum probe surface on its own port; that is the worker's liveness, not the service's. |
| `rebuild` · `replay_aggregate` | Projection rebuild + per-row replay, the workers `admin-cli` invokes. |
| `db_pool` | One pool per shard host (not per database) for pgbouncer transaction mode. |

Nine `[[bin]]` targets: the server, plus `provision`, `rebuilder`, `orphan_scanner`, `embedding-worker`, `replay-aggregate`, and the three drills (`provision-drill`, `freeze-drill`, `capacity-place`).

## What is NOT built

The **GEO_001 aggregate itself** — geometry, political, settlement and route deltas. That work was blocked on the DP-kernel; the kernel now exists, so it is unbuilt rather than blocked. Its OpenAPI specs are still unfrozen: see the table in [`contracts/api/world/`](../../contracts/api/world/).

## Running it

Config is fail-closed — a missing secret is exit 2 naming every absent variable, never a default. The credential names are the `provision` worker's on purpose, so one correct deployment configures both:

```
WORLD_HTTP_BIND              default 0.0.0.0:7120
LOREWEAVE_INTERNAL_TOKEN     required
PROVISION_META_DSN           required   reality_registry + shard_utilization
PROVISION_SHARD_ADMIN_DSN    required   runs CREATE DATABASE
PROVISION_BRIDGE_URL/_TOKEN  required   the Go meta-write bridge (I8)
PROVISION_SHARD_HOSTPORT     required
PROVISION_PG_USER            required
PROVISION_PG_PASSWORD        optional   may be empty under peer/trust auth
PROVISION_SQL_DIR            default contracts/migrations/per_reality
```

Provisioning needs an image that provides pgvector (`infra/postgres-pgvector.Dockerfile`); a cluster without it dies at migration `0006`.

Design refs: [`features/00_geography/`](../../docs/03_planning/LLM_MMO_RPG/features/00_geography/).
