# User-created realities — the create-database feature, and its security layers

**Status:** DESIGN (2026-08-08). Not built. No code changes accompany this document.

**Reconciles:** User Boundaries & Tenancy, User Data Scope & Protection, Data Plane **DP-A1–A19 / DP-R1–R8 / DP-T0–T3**, Foundation Invariants **I1–I19**, Data Plane channels **DP-Ch1–Ch37**

> Prior art this was written against, opened before designing: `06_data_plane/05_control_plane_spec.md`
> (`DP-C1` responsibilities, `DP-C10` admin interface), `migrations/meta/001_reality_registry.up.sql`,
> `services/world-service/src/provisioner.rs` (the 11-step flow), `provisioner_live.rs`
> (`safe_ident`, the meta bridge, I4 isolation), `deprovisioner.rs`, `capacity_planner.rs`.
> **What it found is in §1, and it is the reason this document exists.**

---

## 1 · Phase 0 — what already models this, measured

Three queries, in this order, because the cheap one reframes the expensive ones. *(That order is the
lesson: the previous round asked "does this table have rows" before "does this database type exist",
and spent a session hardening a migration for a database that has never been instantiated.)*

| # | question | answer |
|---|---|---|
| 1 | How many per-reality databases exist? | **`SELECT count(*) … LIKE 'reality%'` → 0.** Never one, ever. |
| 2 | What can create one? | **`provision_reality`'s only caller is `services/world-service/src/bin/provision_drill.rs`** — an ops drill binary. No HTTP route, no gateway path, no frontend, no MCP tool. |
| 3 | Who owns a reality? | **`reality_registry` has no owner column.** Its only user columns are `close_initiated_by` and `drop_approved_by` — both operator fields. |

⇒ **The shipped design is *an operator provisions a world; users join it*.** `DP-C10` names an
**admin interface** and nothing else. The requirement — *users create their own realities* — is a
**different resource with different tenancy**, and the schema encodes the other one.

A fourth fact, quietly the most telling:

```sql
CONSTRAINT reality_registry_db_host_format CHECK (
    db_host ~ '^pg-shard-[0-9]+\.(internal|prod|staging)$'
```

The dev host is `postgres`. **The registry rejects the only environment that exists**, on host format
alone. The schema was written for an infrastructure that has never been stood up, and locks out the
one that has. That is why "just run the provisioner and see" is not available.

---

## 2 · The decision this document needs, stated before the design

**Is a reality a USER-OWNED resource or an OPERATOR-OWNED one?** The rest of this document assumes
user-owned, because that is the requirement given. It is written so that the assumption is visible
rather than buried, because it changes the schema, the authorization model, the quota model and the
deletion story — and because the shipped schema currently answers the other way.

If the answer is *operator-owned with user-requested creation* (an admin approves), the layers below
still apply; only §5's `owner_user_id` becomes `requested_by` plus an approval state.

---

## 3 · Tier table (`DP-R2`)

| datum | tier | scope key | store | why |
|---|---|---|---|---|
| `reality_registry` row (identity, host, status, **owner**) | **CP / meta** | `owner_user_id` | meta Postgres | Control-plane fact, cross-instance by nature. `DP-A2`: CP is not on the hot path. |
| reality quota / entitlement per user | **CP / meta** | `owner_user_id` | meta Postgres | An authorization input; must be readable without touching a reality DB. |
| the reality's own schema (`events`, `channels`, …) | **per-reality** | `reality_id` | `reality_<id>` Postgres | `DPA-SCOPE` §4: anything reading/writing a per-reality aggregate is game-layer. |
| provisioning progress / step ledger | **per-reality** | `reality_id` | `schema_migrations` in the reality DB | `1b14-01`: re-entry needs a ledger the reality itself carries. |
| the creation request in flight | **transient** | — | none (idempotency key in meta) | Nothing durable that a retry cannot reconstruct. |

---

## 4 · Threat model — this is a CREATE DATABASE feature

Ordinary CRUD threat modelling does not cover this. The operation allocates a **database**, on a
**shard**, through a role holding **`CREATEDB`**, using a name that must be **string-interpolated
into DDL** because `CREATE DATABASE` cannot bind parameters. Each of those is a distinct hazard.

| id | threat | why it is real here |
|---|---|---|
| `T1` | **Resource exhaustion** — a user creates realities until the shard dies | Disk, connection slots, catalog bloat, backup cost, and `max_connections` are all per-cluster. The dev stack already carries **112 abandoned throwaway databases** — the same failure with nobody malicious. |
| `T2` | **DDL injection via the name** | `CREATE DATABASE` takes no parameters. Any user-influenced byte in that string is an injection surface. |
| `T3` | **Privilege escalation** | The provisioning path needs `CREATEDB`. Today the only login role is `loreweave`, which is **`rolsuper` + `rolbypassrls`** (`1b7db-03`). A user-reachable path to a superuser connection is the whole game. |
| `T4` | **Cross-tenant access** | A user reaching another user's reality database, or a reality's schema referencing another reality's rows. |
| `T5` | **Abandonment** | Create and walk away. Every abandoned reality is a database, a registry row and a backup line, forever. |
| `T6` | **Partial provisioning** | The flow is 11 steps across two databases and an HTTP bridge. A crash mid-way must not leave an unreachable half-reality — which is exactly what `1b14-01` measured before the ledger. |
| `T7` | **Enumeration** | `reality_id` in URLs or errors leaking the existence of other users' worlds. |
| `T8` | **Cost amplification** | Provisioning is expensive and slow. A cheap-to-call endpoint is a DoS lever against the whole cluster, not just the caller. |

---

## 5 · The layers

Defence in depth, and **each layer states what it does NOT do** — a layer credited with a
neighbour's job is how a gap becomes invisible.

### L0 · Entry — one door
`api-gateway-bff` only (the gateway invariant, `I1`). Authenticated session; no service-to-service
shortcut and no unauthenticated path. **Does not** decide whether this user may create anything.

### L1 · Authorization — may this identity create a reality at all
An explicit entitlement check against the user's tier, evaluated **server-side**, never inferred from
the client. **Does not** bound how many.

### L2 · Quota + rate — how many, how fast
A per-user cap and a creation rate limit, **enforced in the same transaction as the registry insert**
so two concurrent requests cannot both pass a read-then-write check (`T1`, `T8`). Per Settings &
Configuration Boundary this is a **user-tier setting with a deploy-time ceiling**: `effective =
AND(deploy_allows, plan_grants)`. **Does not** protect against a single expensive reality.

### L3 · Name derivation — the user never supplies an identifier
The database name is **derived server-side from a generated `reality_id`** (`reality_<uuid-hex>`).
The user's chosen display name is data in a column, never part of any identifier. `safe_ident()`
already exists and stays — but as the **last** line of defence, not the first. **A validator on a
user-supplied name is the wrong shape**: the correct shape is that no user byte reaches DDL (`T2`).

### L4 · Least privilege — the role that creates databases
A dedicated role with `CREATEDB` and **not** superuser, **not** `BYPASSRLS`, used only for
provisioning. ⚠ **This layer does not exist today and it is the blocking one**: `loreweave` is the
sole login role and it is superuser. `1b7db-03` recorded that as tracked debt when nothing
user-facing could reach it. **A user-facing create-database feature promotes it to a prerequisite**
(`T3`).

### L5 · Isolation — what the new database allows
`REVOKE CONNECT ON DATABASE … FROM PUBLIC` (`I4`) already runs, plus a grant naming only the roles
that may connect. **Does not** stop a service that already holds a broad credential — that is `L4`'s
job, and the two are frequently confused.

### L6 · Ownership — the scope key
`reality_registry.owner_user_id NOT NULL`, and **every** read filtered by it. Per User Boundaries a
resource without a scope key is a tenancy defect; the registry has none today. Listing, status and
deletion all resolve through the owner (`T4`, `T7`).

### L7 · Audit — the user action, not just the effect
The existing `meta_write_audit` (`I8`) and `lifecycle_transition_audit` capture the *write*. A
user-triggered privileged operation additionally needs **who asked, from where, and what was
decided** — including refusals, because a denied quota check is the signal that matters.

### L8 · Reaping — abandonment is a lifecycle state
An unfinished provision is garbage-collected; a completed-but-abandoned reality follows the
`deprovisioner`'s existing archive → verify → soft-delete → drop path. **Does not** happen by
itself: `orphan_scanner` exists, its trigger for user-owned realities does not (`T5`).

### L9 · Idempotency — a retry is not a second reality
A client-supplied idempotency key in meta, plus the per-reality `schema_migrations` ledger so a
resumed provision continues rather than restarts (`T6`, and `1b14-01` is the measured version of
getting this wrong).

---

## 6 · What changes

| artifact | change |
|---|---|
| `migrations/meta/001_reality_registry` | `owner_user_id UUID NOT NULL` + index; the `db_host` CHECK widened to admit a real environment, or the environment renamed to satisfy it — **one of the two, deliberately** |
| meta | a quota/entitlement table, or a column on the existing user tier |
| `world-service` | an authenticated route, or an MCP tool if an agent may call it (MCP-first) |
| `api-gateway-bff` | the route, with rate limiting |
| Postgres roles | a `CREATEDB`-only provisioning role — **`L4`, and it blocks the rest** |
| `provisioner.rs` | owner threaded through; quota checked transactionally; idempotency key |

## 7 · Explicitly NOT in scope

Sharding policy beyond what `capacity_planner` already does · billing · the reality's *content*
(worlds, channels, actors) · migrating the 112 abandoned dev databases · changing the per-reality
schema itself.

## 8 · Open questions for the PO

1. **User-owned or operator-approved?** (§2) — everything else follows from it.
2. **Quota**: what is the default per-user cap, and is it a plan tier or a flat number?
3. **The `db_host` CHECK**: widen it, or make dev match `pg-shard-N.internal`? The second keeps the
   constraint honest and costs a compose rename.
4. **Deletion**: may a user destroy their own reality outright, or only request it? The
   `deprovisioner` already models approval (`drop_approved_by`), which reads as operator-owned.
5. **`L4` sequencing**: the `CREATEDB`-only role is a prerequisite. Does it land in this feature, or
   as its own hardening task first?
