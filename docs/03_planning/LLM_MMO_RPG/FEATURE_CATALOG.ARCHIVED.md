# Feature Catalog

> **Status:** Living reference — updated as features are discovered or designed.
> **Purpose:** Bird's-eye view of every feature touching this product. Provides stable IDs for cross-reference across design docs. Use this to answer "what does the product actually include?" without having to read every doc.
> **Created:** 2026-04-23

---

## How to use this file

- **Every feature has a stable ID** (e.g. `NPC-3`). Cross-reference from other docs via ID.
- **Status** tells you where the feature stands:
  - ✅ **Designed** — has a concrete design in one of the numbered docs
  - 🟡 **Partial** — designed in broad strokes, has pending decisions
  - 📦 **Deferred** — known, explicitly pushed to a future design doc (tied to a `DF*` in [OPEN_DECISIONS.md](OPEN_DECISIONS.md))
  - ❓ **Open** — identified but no design yet
  - 🚫 **Out of scope** — considered and rejected
- **Tier** tells you when the feature is needed:
  - `V1` — required for first solo RP prototype
  - `V2` — coop scene (2–4 players in one reality)
  - `V3` — full persistent multiverse MMO
  - `V4+` — future vision, exploratory
  - `INFRA` — infrastructure, no tier (always needed)
  - `PLT` — platform-hosted only (self-hosted can skip)
- **Dep** lists upstream features that must exist for this one to work.
- **Design ref** points to the doc section that owns the design detail.

When adding new features:
1. Assign the next ID in its category
2. Set status + tier + dep
3. Point `Design ref` to where the detail lives (or `TBD`)
4. Mark deferred ones with a `DF` tag from [OPEN_DECISIONS.md](OPEN_DECISIONS.md)

---

## Category map

| Code | Category | What it covers |
|---|---|---|
| **IF** | Infrastructure | Storage, sharding, realtime transport — invisible to users |
| **WA** | World Authoring | Book → glossary → reality pipeline; author-side tools |
| **PO** | Player Onboarding | Account, reality discovery, PC creation |
| **PL** | Play Loop | Session, turn, prompt, LLM inference, event broadcast |
| **NPC** | NPC Systems | NPC persona, memory, behavior, canon-faithfulness |
| **PCS** | PC Systems | PC state, lifecycle, offline behavior |
| **SOC** | Social | Session mechanics, PvP, group chat, moderation |
| **NAR** | Narrative / Canon | Canon layers, canonization, world rules |
| **EM** | Emergent / Advanced | Fork, travel, rebase, reality lifecycle |
| **PLT** | Platform | Tiers, billing, admin, moderation at platform level |
| **CC** | Cross-cutting | UI, i18n, accessibility, observability |
| **DL** | Daily Life | Offline PC/NPC routines (DF1 umbrella) |

---

## IF — Infrastructure

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| IF-1 | Event-sourced storage (events as SSOT, projections as derived state) | ✅ | INFRA | — | [02 §4](02_STORAGE_ARCHITECTURE.md) |
| IF-2 | Snapshot-fork semantics (peer realities, cascading read) | ✅ | INFRA | IF-1 | [03 §6–7](03_MULTIVERSE_MODEL.md) |
| IF-3 | Reality registry + DB-per-reality with subtree grouping | ✅ | INFRA | IF-1 | [02 §7](02_STORAGE_ARCHITECTURE.md), [03 §7](03_MULTIVERSE_MODEL.md) |
| IF-4 | Meta registry (cross-reality player index, instance routing) | ✅ | INFRA | IF-3 | [02 §7.2, §12E.2](02_STORAGE_ARCHITECTURE.md) |
| IF-4a | Meta-worker service (dedicated Go, xreality.* event consumer) | ✅ | INFRA | IF-4, IF-5 | [02 §12E.3](02_STORAGE_ARCHITECTURE.md) (R5-L2) |
| IF-4b | Cross-instance event propagation (`xreality.*` topics) | ✅ | INFRA | IF-5 | [02 §12E.3](02_STORAGE_ARCHITECTURE.md) (R5-L2) |
| IF-4c | Cross-instance data access governance policy | ✅ | INFRA | — | [docs/02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md](../../02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md) (R5 anti-pattern) |
| IF-5 | Realtime transport (Redis Streams + WebSocket fanout per region) | 🟡 | INFRA | IF-1 | [02 §9](02_STORAGE_ARCHITECTURE.md); reuse [70_ASYNC_JOB_WEBSOCKET_ARCHITECTURE_PLAN](../70_ASYNC_JOB_WEBSOCKET_ARCHITECTURE_PLAN.md) |
| IF-5a | Session as single-writer command processor (mandatory) | ✅ | V1 | — | [02 §12G.2](02_STORAGE_ARCHITECTURE.md) (R7-L1) |
| IF-5b | Event scope tagging (`session` / `region` / `reality` / `world`) | ✅ | V1 | IF-1 | [02 §12G.3](02_STORAGE_ARCHITECTURE.md) (R7-L2) |
| IF-5c | Cross-session event handler service (dedicated Go) | ✅ | V1 | IF-1 | [02 §12G.5](02_STORAGE_ARCHITECTURE.md) (R7-L3) |
| IF-5d | Session event queue (per session, priority pop before user input) | ✅ | V1 | IF-5a | [02 §12G.4](02_STORAGE_ARCHITECTURE.md) (R7-L4) |
| IF-5e | NPC single-session constraint (V1; multi-presence deferred V2+) | ✅ | V1 | NPC-1 | [02 §12G.7](02_STORAGE_ARCHITECTURE.md) (R7-L6) |
| IF-6 | Outbox pattern (crash-safe publish) | ✅ | INFRA | IF-1, IF-5 | [02 §9.2, §12F.1](02_STORAGE_ARCHITECTURE.md) |
| IF-6a | Publisher service (dedicated Go, leader election, partition-by-reality) | ✅ | INFRA | IF-6 | [02 §12F.2](02_STORAGE_ARCHITECTURE.md) (R6-L2) |
| IF-6b | Per-reality outbox lag monitoring + 3-tier alerts | ✅ | INFRA | IF-6a | [02 §12F.3](02_STORAGE_ARCHITECTURE.md) (R6-L3) |
| IF-6c | Client catchup protocol (WS handshake + REST `/v1/realities/{id}/events?since=`) | ✅ | V1 | IF-6a | [02 §12F.4](02_STORAGE_ARCHITECTURE.md) (R6-L4) |
| IF-6d | Dead-letter queue with retry backoff + admin resolution | ✅ | INFRA | IF-6 | [02 §12F.5](02_STORAGE_ARCHITECTURE.md) (R6-L5) |
| IF-6e | Redis stream MAXLEN + DB fallback (Redis is cache, DB is SSOT) | ✅ | INFRA | IF-6 | [02 §12F.6](02_STORAGE_ARCHITECTURE.md) (R6-L6, resolves R12) |
| IF-6f | Graceful shutdown + handoff | ✅ | INFRA | IF-6a | [02 §12F.7](02_STORAGE_ARCHITECTURE.md) (R6-L7) |
| IF-7 | Event schema versioning + upcaster chain | ✅ | INFRA | IF-1 | [02 §10, §12C.3](02_STORAGE_ARCHITECTURE.md) |
| IF-7a | Additive-first discipline (policy) | ✅ | INFRA | IF-7 | [02 §12C.1](02_STORAGE_ARCHITECTURE.md) (R3-L1 locked) |
| IF-7b | Schema-as-code + registry (Go source + codegen) | ✅ | INFRA | IF-7 | [02 §12C.2](02_STORAGE_ARCHITECTURE.md) (R3-L2 locked) |
| IF-7c | Schema validation on write | ✅ | INFRA | IF-7 | [02 §12C.4](02_STORAGE_ARCHITECTURE.md) (R3-L4 locked) |
| IF-7d | Breaking change via new event_type (90d deprecation cooldown) | ✅ | INFRA | IF-7 | [02 §12C.5](02_STORAGE_ARCHITECTURE.md) (R3-L5 locked) |
| IF-7e | Polyglot type generation (Go → TS + Python) | ✅ | INFRA | IF-7b | [02 §12C.7](02_STORAGE_ARCHITECTURE.md) |
| IF-7f | Archive upgrade (upcast at cold-archive) | 📦 | V2 | IF-10 | [02 §12C.6](02_STORAGE_ARCHITECTURE.md) (R3-L6 deferred V2) |
| IF-8 | Snapshots (per-aggregate periodic checkpoints) | ✅ | INFRA | IF-1 | [02 §6](02_STORAGE_ARCHITECTURE.md) |
| IF-9 | Projection rebuild pipeline | ✅ | INFRA | IF-1, IF-8 | [02 §5.5, §12B](02_STORAGE_ARCHITECTURE.md) |
| IF-9a | Per-aggregate parallel rebuild (8-worker default) | ✅ | INFRA | IF-9 | [02 §12B.2](02_STORAGE_ARCHITECTURE.md) (R2-L2 locked) |
| IF-9b | V1 freeze-rebuild for schema migration | ✅ | V1 | IF-9 | [02 §12B.3](02_STORAGE_ARCHITECTURE.md) (R2-L3 locked) |
| IF-9c | V2 blue-green projection tables (dual-write + atomic swap) | ✅ | V2 | IF-9 | [02 §12B.3](02_STORAGE_ARCHITECTURE.md) (R2-L3 locked) |
| IF-9d | Integrity checker (daily sample + monthly full) | ✅ | V1 | IF-9 | [02 §12B.4](02_STORAGE_ARCHITECTURE.md) (R2-L4 locked) |
| IF-9e | Catastrophic rebuild procedure (freeze-rebuild-thaw, rolling 50 concurrent) | ✅ | V1 | IF-9 | [02 §12B.5](02_STORAGE_ARCHITECTURE.md) (R2-L5 locked) |
| IF-10 | Archive to MinIO (hot/warm/cold tiering of events) | ✅ | INFRA | IF-1 | [02 §11, §12A.4](02_STORAGE_ARCHITECTURE.md) |
| IF-10a | Audit split — separate `event_audit` table from `events` | ✅ | INFRA | IF-1 | [02 §12A.1](02_STORAGE_ARCHITECTURE.md) (R1-L1 locked) |
| IF-10b | Event emission discipline — state events vs derivable, only state events persisted | ✅ | INFRA | IF-1 | [02 §12A.2](02_STORAGE_ARCHITECTURE.md) (R1-L2 locked) |
| IF-10c | Tiered retention per event type (nightly cleanup job) | ✅ | INFRA | IF-10 | [02 §12A.3](02_STORAGE_ARCHITECTURE.md) (R1-L3 locked) |
| IF-10d | Snapshot-then-truncate non-canon aggregates | ✅ | V3 | IF-8 | [02 §12A.5](02_STORAGE_ARCHITECTURE.md) (R1-L5 locked) |
| IF-10e | lz4 compression on JSONB columns + ZSTD for MinIO cold | ✅ | INFRA | IF-1 | [02 §12A.6](02_STORAGE_ARCHITECTURE.md) (R1-L6 locked) |
| IF-11 | Auto-freeze + auto-archive of inactive realities | 🟡 | INFRA | IF-3, IF-10 | [03 §12.1](03_MULTIVERSE_MODEL.md) |
| IF-12 | pgvector-per-reality embedding storage | ✅ | INFRA | IF-3 | Locked S2 |
| IF-13 | Schema migrations across N instance DBs (idempotent, staggered) | ✅ | INFRA | IF-3 | [02 §7.5, §12D.2](02_STORAGE_ARCHITECTURE.md) |
| IF-13a | Automated DB provisioning + deprovisioning | ✅ | INFRA | IF-3 | [02 §12D.1](02_STORAGE_ARCHITECTURE.md) (R4-L1) |
| IF-13b | Migration orchestrator (dedicated Go service) | ✅ | INFRA | IF-13 | [02 §12D.2](02_STORAGE_ARCHITECTURE.md) (R4-L2) |
| IF-13c | Tiered backup strategy (active/frozen/archived → different schedules) | ✅ | INFRA | IF-3, IF-10 | [02 §12D.3](02_STORAGE_ARCHITECTURE.md) (R4-L3) |
| IF-13d | pgbouncer connection pooling (per-shard, transaction mode) | ✅ | INFRA | IF-3 | [02 §12D.4](02_STORAGE_ARCHITECTURE.md) (R4-L4) |
| IF-13e | Metrics aggregation with reality_id labels | ✅ | INFRA | IF-3 | [02 §12D.5](02_STORAGE_ARCHITECTURE.md) (R4-L5) |
| IF-13f | Shared Postgres server sharding (many DBs per server) | ✅ | V2 | IF-3 | [02 §12D.6](02_STORAGE_ARCHITECTURE.md) (R4-L6) |
| IF-13g | Orphan DB detection + cleanup | ✅ | INFRA | IF-3 | [02 §12D.7](02_STORAGE_ARCHITECTURE.md) (R4-L7) |
| IF-13h | DB subtree split runbook — freeze-copy-cutover (V1/V2) | ✅ | V1 | IF-3, IF-13 | [02 §12N.4](02_STORAGE_ARCHITECTURE.md) (C2-D1/D2) |
| IF-13i | `migrating` lifecycle state + `reality_migration_audit` | ✅ | V1 | IF-13h | [02 §12N.3](02_STORAGE_ARCHITECTURE.md) (C2-state) |
| IF-13j | Pre/post-migration integrity verification (reuse R2-L4 logic) | ✅ | V1 | IF-9d, IF-13h | [02 §12N.4](02_STORAGE_ARCHITECTURE.md) step 8 |
| IF-13k | Migration rollback (source untouched until success) | ✅ | V1 | IF-13h | [02 §12N.10](02_STORAGE_ARCHITECTURE.md) |
| IF-13l | Logical-replication split (Tier 2, near-zero-downtime) | 📦 | V3+ | IF-13h | [02 §12N.5](02_STORAGE_ARCHITECTURE.md) (C2-D1 Tier 2) |
| IF-13m | Subtree-split coordination (multi-reality parallel migration) | 📦 | V3+ | IF-13l | [02 §12N.6](02_STORAGE_ARCHITECTURE.md) |
| IF-14 | Meta registry HA — Patroni + sync replica + async replica (C3 resolution) | ✅ | V1 | IF-4 | [02 §12O.3](02_STORAGE_ARCHITECTURE.md) (C3-D1/D2) |
| IF-14a | Meta access library (shared Go, primary/replica routing) | ✅ | V1 | IF-14 | [02 §12O.5](02_STORAGE_ARCHITECTURE.md) (C3-arch) |
| IF-14b | Redis cache for reality routing (30s TTL, xreality invalidation) | ✅ | V1 | IF-14, IF-4b | [02 §12O.6](02_STORAGE_ARCHITECTURE.md) (C3-D3) |
| IF-14c | App-level failover retry + backoff | ✅ | V1 | IF-14 | [02 §12O.7](02_STORAGE_ARCHITECTURE.md) |
| IF-14d | Degraded mode (cache-serve + buffered heartbeats/audit) | ✅ | V1 | IF-14b | [02 §12O.8](02_STORAGE_ARCHITECTURE.md) |
| IF-14e | WAL archive + PITR (30d retention) | ✅ | V1 | IF-14 | [02 §12O.9](02_STORAGE_ARCHITECTURE.md) |
| IF-14f | Meta HA monitoring + alerts | ✅ | V1 | IF-14 | [02 §12O.12](02_STORAGE_ARCHITECTURE.md) |
| IF-14g | Cross-region DR (active-passive + automated DNS failover) | 📦 | V3+ | IF-14 | [02 §12O.9](02_STORAGE_ARCHITECTURE.md) (C3-D5) |
| IF-14h | 2nd sync replica for multi-AZ tolerance | 📦 | V3+ | IF-14 | [02 §12O.3](02_STORAGE_ARCHITECTURE.md) |
| IF-14i | Separate audit DB cluster | 📦 | V3+ | IF-14 | [02 §12O.10](02_STORAGE_ARCHITECTURE.md) (C3-D4 evaluate) |
| IF-14j | Per-shard HA for reality DBs | 📦 | V3+ | IF-3 | [02 §12O.11](02_STORAGE_ARCHITECTURE.md) (C3-D6) |
| IF-15 | L3 override reverse index (C4 resolution) | ✅ | V1 | IF-4, IF-4a | [02 §12P](02_STORAGE_ARCHITECTURE.md) (C4-D1..D4) |
| IF-15a | Event-handler side-effect maintenance | ✅ | V1 | IF-15, IF-5c | [02 §12P.3](02_STORAGE_ARCHITECTURE.md) |
| IF-15b | O(1) preview + force-propagate targeting queries | ✅ | V1 | IF-15 | [02 §12P.4](02_STORAGE_ARCHITECTURE.md) |
| IF-15c | Index rebuild command (recovery) | ✅ | V1 | IF-15 | [02 §12P.6](02_STORAGE_ARCHITECTURE.md) |
| IF-16 | Lifecycle transition CAS discipline (C5 resolution) | ✅ | V1 | IF-4 | [02 §12Q](02_STORAGE_ARCHITECTURE.md) (C5-D1..D6) |
| IF-16a | `AttemptStateTransition()` helper in `contracts/meta/` | ✅ | V1 | IF-16 | [02 §12Q.3](02_STORAGE_ARCHITECTURE.md) |
| IF-16b | `lifecycle_transition_audit` table | ✅ | V1 | IF-16 | [02 §12Q.4](02_STORAGE_ARCHITECTURE.md) |
| IF-16c | Transition graph validation + mutual exclusion | ✅ | V1 | IF-16 | [02 §12Q.6-7](02_STORAGE_ARCHITECTURE.md) |
| IF-16d | Lint rule enforcing helper usage | ✅ | V1 | IF-16 | [02 §12Q.8](02_STORAGE_ARCHITECTURE.md) |
| IF-17 | Adversarial review follow-ups (H/M/P consolidated) | ✅ | V1 | various | [02 §12R](02_STORAGE_ARCHITECTURE.md) |
| IF-17a | Session size caps + queue UX (H3 revised — NPC single-session PERMANENT) | ✅ | V1 | IF-16, NPC-1 | [02 §12R.1](02_STORAGE_ARCHITECTURE.md) (H3-NEW-D1..D5) |
| IF-17b | NPC availability schedule (schema reserved, V2+ feature) | 📦 | V2+ | IF-17a | [02 §12R.1.3](02_STORAGE_ARCHITECTURE.md) (H3-NEW-D6) |
| IF-17c | Reality `seeding` state + bootstrap worker | ✅ | V1 | IF-16a, migration-orchestrator | [02 §12R.2](02_STORAGE_ARCHITECTURE.md) (H5-D1..D3) |
| IF-17d | Bootstrap locale translation integration | ✅ | V1 | IF-17c, translation-service | [02 §12R.2.3](02_STORAGE_ARCHITECTURE.md) (M-REV-5-D1) |
| IF-17e | Upcaster for deprecated event types | ✅ | V1 | IF-7 | [02 §12C.5 updated, §12R.3](02_STORAGE_ARCHITECTURE.md) (H4-D1) |
| IF-17f | Adversarial-review observability suite | ✅ | V1 | — | [02 §12R.4](02_STORAGE_ARCHITECTURE.md) (H1/H2/H6/M-REV-6) |
| IF-17g | HNSW pre-warm on reality thaw | ✅ | V1 | IF-18 | [02 §12R.5](02_STORAGE_ARCHITECTURE.md) (M-REV-3-D1) |
| IF-17h | Projection rebuild determinism rule | ✅ | V1 | IF-9 | [02 §12R.7](02_STORAGE_ARCHITECTURE.md) (P4-D1) |
| IF-17i | Admin command keyword metadata + search | ✅ | V1 | IF-20 | [02 §12R.9](02_STORAGE_ARCHITECTURE.md) (P2-D1) |
| IF-18 | Reality creation rate limit (S1) | ✅ | V1 | IF-4 | [02 §12S.1](02_STORAGE_ARCHITECTURE.md) (S1-D1) |
| IF-19 | Session-scoped memory model (replaces §12H per-pair) | ✅ | V1 | IF-1, NPC-1 | [02 §12S.2](02_STORAGE_ARCHITECTURE.md) (S2-NEW-D1..D5) |
| IF-19a | Event visibility + whisper schema (5 values) | ✅ | V1 | IF-1 | [02 §12S.2.1](02_STORAGE_ARCHITECTURE.md) (S2-NEW-D2) |
| IF-19b | session_participants capability table | ✅ | V1 | IF-5a | [02 §12S.2.2](02_STORAGE_ARCHITECTURE.md) (S2-NEW-D3) |
| IF-19c | npc_session_memory aggregate (replaces npc_pc_memory) | ✅ | V1 | IF-19 | [02 §12S.2.3](02_STORAGE_ARCHITECTURE.md) |
| IF-19d | npc_pc_relationship derived projection | ✅ | V1 | IF-19 | [02 §12S.2.4](02_STORAGE_ARCHITECTURE.md) (S2-NEW-D5) |
| IF-19e | Prompt-assembly canonical query (capability-based) | ✅ | V1 | IF-19 | [02 §12S.2.5](02_STORAGE_ARCHITECTURE.md) (S2-NEW-D4) |
| IF-20 | Event cascade_policy (S3) | ✅ | V1 | IF-1, IF-2 | [02 §12S.3.1](02_STORAGE_ARCHITECTURE.md) (S3-NEW-D1..D3) |
| IF-21 | Privacy level full tier system (S3 Option A) | ✅ | V1 | IF-1 | [02 §12S.3.2](02_STORAGE_ARCHITECTURE.md) (S3-NEW-D6..D8) |
| IF-21a | Per-tier retention (sensitive 30d, confidential 7d) | ✅ | V1+30d | IF-21 | [02 §12S.3.2](02_STORAGE_ARCHITECTURE.md) |
| IF-21b | Force-propagate rejection on non-normal privacy | ✅ | V1 | IF-21 | [02 §12S.3.2](02_STORAGE_ARCHITECTURE.md) |
| IF-21c | Cascade auto-constrain on non-normal privacy | ✅ | V1 | IF-21 | [02 §12S.3.2](02_STORAGE_ARCHITECTURE.md) |
| IF-21d | Whisper tiered UX (4 command variants) | ✅ | V1 | IF-21 | [02 §12S.3.4](02_STORAGE_ARCHITECTURE.md) |
| IF-21e | Fork UX warning with inheritance counts | ✅ | V1 | IF-20, IF-21 | [02 §12S.3.5](02_STORAGE_ARCHITECTURE.md) |
| IF-21f | Per-event encryption (MinIO SSE-C for confidential) | 📦 | V2+ | IF-21 | [02 §12S.3.2](02_STORAGE_ARCHITECTURE.md) |
| IF-21g | Admin access tier gating (was V1+30d, now V1) | ✅ | V1 | IF-21, IF-23 | [02 §12S.5, §12U.7](02_STORAGE_ARCHITECTURE.md); unblocked by S5 lock 2026-04-24. Implemented via IF-23g SQL filter. |
| IF-22 | Meta integrity & access control (S4) | ✅ | V1 | IF-4 | [02 §12T](02_STORAGE_ARCHITECTURE.md) (S4-D1..D8) |
| IF-22a | `MetaWrite()` canonical helper (generalizes §12Q) | ✅ | V1 | IF-16a | [02 §12T.2](02_STORAGE_ARCHITECTURE.md) (S4-D1) |
| IF-22b | `meta_write_audit` append-only table | ✅ | V1 | IF-22a | [02 §12T.5](02_STORAGE_ARCHITECTURE.md) (S4-D2) |
| IF-22c | CHECK constraints on meta tables | ✅ | V1 | IF-4 | [02 §12T.3](02_STORAGE_ARCHITECTURE.md) (S4-D3) |
| IF-22d | Append-only audit (REVOKE + retention role) | ✅ | V1 | IF-22 | [02 §12T.4](02_STORAGE_ARCHITECTURE.md) (S4-D4) |
| IF-22e | `meta_read_audit` for sensitive queries | ✅ | V1+30d | IF-22 | [02 §12T.6](02_STORAGE_ARCHITECTURE.md) (S4-D5) |
| IF-22f | Per-service Postgres roles (least privilege) | ✅ | V1 | IF-22 | [02 §12T.8](02_STORAGE_ARCHITECTURE.md) (S4-D6) |
| IF-22g | Meta anomaly detection + PAGE alerts | ✅ | V1+60d | IF-22 | [02 §12T.7](02_STORAGE_ARCHITECTURE.md) (S4-D7) |
| IF-22h | WORM cold-archive for audit tables | 📦 | V2+ | IF-22d, IF-10 | [02 §12T.4](02_STORAGE_ARCHITECTURE.md) (S4-D8) |
| IF-22i | Hash-chain tamper detection on audit | 📦 | V2+ | IF-22d | [02 §12T.4](02_STORAGE_ARCHITECTURE.md) (S4-D8) |
| IF-23 | Admin command impact classification (S5) | ✅ | V1 | IF-20 | [02 §12U](02_STORAGE_ARCHITECTURE.md) (S5-D1..D8) |
| IF-23a | Three-tier ImpactClass (destructive/griefing/informational) | ✅ | V1 | IF-23 | [02 §12U.2](02_STORAGE_ARCHITECTURE.md) (S5-D1) |
| IF-23b | Tier-specific authorization (dual-actor / reason / notification) | ✅ | V1 | IF-23 | [02 §12U.2](02_STORAGE_ARCHITECTURE.md) (S5-D2) |
| IF-23c | ImpactClass metadata + CI lint enforcement | ✅ | V1 | IF-20 | [02 §12U.3](02_STORAGE_ARCHITECTURE.md) (S5-D3) |
| IF-23d | admin_action_affects_user notification table | ✅ | V1 | IF-23 | [02 §12U.4-5](02_STORAGE_ARCHITECTURE.md) (S5-D4) |
| IF-23e | Griefing-tier periodic review dashboard | ✅ | V1+30d | IF-23 | [02 §12U.6](02_STORAGE_ARCHITECTURE.md) (S5-D5) |
| IF-23f | User admin-activity page (`/me/admin-activity`) | ✅ | V1+30d | IF-23d | [02 §12U.5](02_STORAGE_ARCHITECTURE.md) |
| IF-23g | Privacy-level access SQL filter (S3 V1+30d → V1) | ✅ | V1 | IF-21, IF-23 | [02 §12U.7](02_STORAGE_ARCHITECTURE.md) (S5-D6) |
| IF-23h | ML classification-drift + grief-pattern detection | 📦 | V2+ | IF-23 | [02 §12U.10](02_STORAGE_ARCHITECTURE.md) (S5-D8) |
| IF-24 | LLM cost controls (S6) | ✅ | V1 | IF-15 | [02 §12V](02_STORAGE_ARCHITECTURE.md) (S6-D1..D8) |
| IF-24a | Per-user turn rate limit (Redis token bucket, tier-aware) | ✅ | V1 | IF-24 | [02 §12V.2](02_STORAGE_ARCHITECTURE.md) (S6-D1) |
| IF-24b | Per-session cost cap with warn + hard cap | ✅ | V1 | IF-24 | [02 §12V.3](02_STORAGE_ARCHITECTURE.md) (S6-D2) |
| IF-24c | Per-user daily cost budget | ✅ | V1+30d | IF-24 | [02 §12V.4](02_STORAGE_ARCHITECTURE.md) (S6-D3) |
| IF-24d | Real-time cost observability + alerts | ✅ | V1 | IF-24 | [02 §12V.5](02_STORAGE_ARCHITECTURE.md) (S6-D4) |
| IF-24e | Circuit breaker (user + platform levels) | ✅ | V1+30d | IF-24 | [02 §12V.6](02_STORAGE_ARCHITECTURE.md) (S6-D5) |
| IF-24f | `user_cost_ledger` table (per-LLM-call logging) | ✅ | V1 | IF-24 | [02 §12V.7](02_STORAGE_ARCHITECTURE.md) (S6-D6) |
| IF-24g | Model selection tier gating | ✅ | V1 | IF-24 | [02 §12V.8](02_STORAGE_ARCHITECTURE.md) (S6-D7) |
| IF-24h | ML cost anomaly + predictive modeling + tier suggestions | 📦 | V2+ | IF-24 | [02 §12V.10](02_STORAGE_ARCHITECTURE.md) (S6-D8) |
| IF-25 | Queue abuse prevention (S7) | ✅ | V1 | IF-17a | [02 §12W](02_STORAGE_ARCHITECTURE.md) (S7-D1..D7) |
| IF-25a | Per-user queue depth cap (5 simultaneous) | ✅ | V1 | IF-25 | [02 §12W.2](02_STORAGE_ARCHITECTURE.md) (S7-D1) |
| IF-25b | Two-stage queue expiration (10-min + 24h) | ✅ | V1 | IF-25 | [02 §12W.3](02_STORAGE_ARCHITECTURE.md) (S7-D2) |
| IF-25c | `user_queue_metrics` + queue state transitions | ✅ | V1 | IF-25 | [02 §12W.4](02_STORAGE_ARCHITECTURE.md) (S7-D3) |
| IF-25d | Queue priority decay (acceptance-rate-based) | ✅ | V1+30d | IF-25c | [02 §12W.5](02_STORAGE_ARCHITECTURE.md) (S7-D4) |
| IF-25e | Abandonment cool-down (10/24h → 1h ban) | ✅ | V1 | IF-25c | [02 §12W.6](02_STORAGE_ARCHITECTURE.md) (S7-D5) |
| IF-25f | Reality-level queue override schema (DF4 activates) | 📦 | V1 schema / V2+ enforcement | IF-25 | [02 §12W.7](02_STORAGE_ARCHITECTURE.md) (S7-D6) |
| IF-25g | ML abuse pattern + reputation system | 📦 | V2+ | IF-25 | [02 §12W.8](02_STORAGE_ARCHITECTURE.md) |
| IF-26 | Audit log PII + retention (S8) | ✅ | V1 | IF-1, IF-22 | [02 §12X](02_STORAGE_ARCHITECTURE.md) (S8-D1..D8) |
| IF-26a | `pii_registry` + per-user KEK crypto-shred erasure | ✅ | V1 | IF-26 | [02 §12X.2](02_STORAGE_ARCHITECTURE.md) (S8-D1) |
| IF-26b | PII classification migration tags + CI lint | ✅ | V1 | IF-26 | [02 §12X.3](02_STORAGE_ARCHITECTURE.md) (S8-D2) |
| IF-26c | Unified retention tier matrix (supersedes scattered rules) | ✅ | V1 | IF-26 | [02 §12X.4](02_STORAGE_ARCHITECTURE.md) (S8-D3) |
| IF-26d | Free-text PII scrubber (admin reason, transcripts, notes) | ✅ | V1 | IF-26 | [02 §12X.5](02_STORAGE_ARCHITECTURE.md) (S8-D4) |
| IF-26e | `admin/user-erasure` Tier 1 destructive runbook (30d SLA) | ✅ | V1 | IF-26a, IF-23 | [02 §12X.6](02_STORAGE_ARCHITECTURE.md) (S8-D5) |
| IF-26f | Audit hash chain + daily Merkle root (V1+30d) | ✅ | V1+30d | IF-26 | [02 §12X.7](02_STORAGE_ARCHITECTURE.md) (S8-D6) |
| IF-26g | Structured logging library + ingest scrubber (30d retention) | ✅ | V1 | — | [02 §12X.8](02_STORAGE_ARCHITECTURE.md) (S8-D7) |
| IF-26h | `user_consent_ledger` + revocation event fan-out | ✅ | V1 | IF-26 | [02 §12X.9](02_STORAGE_ARCHITECTURE.md) (S8-D8) |
| IF-29 | Prompt assembly governance (S9) | ✅ | V1 | IF-15, IF-14 | [02 §12Y](02_STORAGE_ARCHITECTURE.md) (S9-D1..D10) |
| IF-29a | Centralized `contracts/prompt/` library + CI lint on provider SDK bypass | ✅ | V1 | IF-29 | [02 §12Y.2](02_STORAGE_ARCHITECTURE.md) (S9-D1) |
| IF-29b | Versioned prompt template registry (schema-as-code) | ✅ | V1 | IF-29 | [02 §12Y.3](02_STORAGE_ARCHITECTURE.md) (S9-D2) |
| IF-29c | Strict 8-section prompt structure + `[INPUT]` sandboxing | ✅ | V1 | IF-29 | [02 §12Y.4](02_STORAGE_ARCHITECTURE.md) (S9-D3) |
| IF-29d | Capability + privacy filter pre-assembly gate (S2/S3/S8 enforcement) | ✅ | V1 | IF-29 | [02 §12Y.5](02_STORAGE_ARCHITECTURE.md) (S9-D4) |
| IF-29e | Multi-layer injection defense (delimiter + instruction + scanner + canary + post-output) | ✅ | V1 | IF-29 | [02 §12Y.6](02_STORAGE_ARCHITECTURE.md) (S9-D5) |
| IF-29f | Per-intent token budget hard caps | ✅ | V1 | IF-29 | [02 §12Y.7](02_STORAGE_ARCHITECTURE.md) (S9-D6) |
| IF-29g | PII redactor + per-provider policy (trains_on_inputs / retention / trusted / tier) | ✅ | V1 | IF-29, IF-14 | [02 §12Y.8](02_STORAGE_ARCHITECTURE.md) (S9-D7) |
| IF-29h | `prompt_audit` deterministic replay (hash + context, no body) | ✅ | V1 | IF-29 | [02 §12Y.9](02_STORAGE_ARCHITECTURE.md) (S9-D8) |
| IF-29i | Regression fixture harness (mock V1 / nightly real-model V1+30d) | ✅ | V1 | IF-29b | [02 §12Y.10](02_STORAGE_ARCHITECTURE.md) (S9-D9) |
| IF-29j | 4-layer canon markup in prompt templates (L1/L2/L3/L4 + SEVERED) | ✅ | V1 | IF-29, WA-4 | [02 §12Y.11](02_STORAGE_ARCHITECTURE.md) (S9-D10) |
| IF-30 | Severance-vs-deletion taxonomy (S10) | ✅ | V1 | IF-1, IF-3 | [02 §12Z](02_STORAGE_ARCHITECTURE.md) (S10-D1..D8) |
| IF-30a | 5-state `GoneState` enum (active/severed/archived/dropped/user_erased) | ✅ | V1 | IF-30 | [02 §12Z.2](02_STORAGE_ARCHITECTURE.md) (S10-D1) |
| IF-30b | `GetEntityStatus()` unified query API + 60s cache | ✅ | V1 | IF-30a | [02 §12Z.3](02_STORAGE_ARCHITECTURE.md) (S10-D2) |
| IF-30c | Prompt marker enum (5 markers) + §12Y scanner whitelist | ✅ | V1 | IF-30, IF-29e | [02 §12Z.4](02_STORAGE_ARCHITECTURE.md) (S10-D3) |
| IF-30d | `admin/entity-provenance` cross-audit timeline CLI | ✅ | V1 | IF-30b, IF-22 | [02 §12Z.5](02_STORAGE_ARCHITECTURE.md) (S10-D4) |
| IF-30d-ui | Entity-provenance timeline web viewer | ✅ | V1+30d | IF-30d | [02 §12Z.5](02_STORAGE_ARCHITECTURE.md) (S10-D4) (DF9/DF11 subsurface) |
| IF-30e | State precedence rule + compound states | ✅ | V1 | IF-30a | [02 §12Z.6](02_STORAGE_ARCHITECTURE.md) (S10-D5) |
| IF-30f | Per-state recovery gate matrix (no universal undelete) | ✅ | V1 | IF-30b | [02 §12Z.7](02_STORAGE_ARCHITECTURE.md) (S10-D6) |
| IF-30f-relink | `admin/relink-ancestor` severance reconnection | 📦 | V2+ | IF-30f, DF6 | [02 §12Z.7](02_STORAGE_ARCHITECTURE.md) (S10-D6) |
| IF-30g | Per-state notification templates (auto-routed by `GoneState`) | ✅ | V1 | IF-30a | [02 §12Z.8](02_STORAGE_ARCHITECTURE.md) (S10-D7) |
| IF-30h | Compliance report section separation (GDPR Art. 30 isolation) | ✅ | V1 | IF-30 | [02 §12Z.9](02_STORAGE_ARCHITECTURE.md) (S10-D8) |
| IF-31 | Service-to-service authentication (S11) | ✅ | V1 | — | [02 §12AA](02_STORAGE_ARCHITECTURE.md) (S11-D1..D10) |
| IF-31a | SPIFFE-like per-service SVID + workload attestation | ✅ | V1 | IF-31 | [02 §12AA.2](02_STORAGE_ARCHITECTURE.md) (S11-D1) |
| IF-31b | Full mTLS service-to-service (Envoy sidecar) | ✅ | V1+30d | IF-31a | [02 §12AA.3](02_STORAGE_ARCHITECTURE.md) (S11-D2) |
| IF-31c | Service ACL matrix + CI lint | ✅ | V1 | IF-31 | [02 §12AA.4](02_STORAGE_ARCHITECTURE.md) (S11-D3) |
| IF-31d | Explicit principal-mode per RPC + confused-deputy defense | ✅ | V1 | IF-31 | [02 §12AA.5](02_STORAGE_ARCHITECTURE.md) (S11-D4) |
| IF-31e | Admin JWT distinct claim schema (role + session + tier + approver + 15min TTL) | ✅ | V1 | IF-31, IF-24 (S5) | [02 §12AA.6](02_STORAGE_ARCHITECTURE.md) (S11-D5) |
| IF-31f | Vault-based secret management + SVID-bound paths | ✅ | V1 | IF-31a | [02 §12AA.7](02_STORAGE_ARCHITECTURE.md) (S11-D6) |
| IF-31g | Event signing in outbox (Ed25519 + freshness) | ✅ | V1+30d | IF-31a, IF-10 | [02 §12AA.8](02_STORAGE_ARCHITECTURE.md) (S11-D7) |
| IF-31h | Private subnet + per-service egress allowlist + VPC flow monitoring | ✅ | V1 | IF-31 | [02 §12AA.9](02_STORAGE_ARCHITECTURE.md) (S11-D8) |
| IF-31i | Two-tier RPC audit (structured logs 90d + `service_to_service_audit` 5y) | ✅ | V1 | IF-31 | [02 §12AA.10](02_STORAGE_ARCHITECTURE.md) (S11-D9) |
| IF-31j | Dev/staging/prod parity + break-glass emergency access | ✅ | V1 | IF-31, IF-20 | [02 §12AA.11](02_STORAGE_ARCHITECTURE.md) (S11-D10) |
| IF-32 | WebSocket token security (S12) | ✅ | V1 | IF-10 (publisher), IF-31 | [02 §12AB](02_STORAGE_ARCHITECTURE.md) (S12-D1..D10) |
| IF-32a | WS ticket handshake (60s one-shot, subprotocol header, not URL) | ✅ | V1 | IF-32 | [02 §12AB.2](02_STORAGE_ARCHITECTURE.md) (S12-D1) |
| IF-32b | Per-connection WS session + 15-min refresh | ✅ | V1 | IF-32a | [02 §12AB.3](02_STORAGE_ARCHITECTURE.md) (S12-D2) |
| IF-32c | Per-message S2/S3 authorization + 30s cache | ✅ | V1 | IF-32, IF-S2-cap | [02 §12AB.4](02_STORAGE_ARCHITECTURE.md) (S12-D3) |
| IF-32d | Origin allowlist + ticket origin binding | ✅ | V1 | IF-32 | [02 §12AB.5](02_STORAGE_ARCHITECTURE.md) (S12-D4) |
| IF-32e | Per-connection + per-user WS rate limits | ✅ | V1 | IF-32, IF-24 (S6) | [02 §12AB.6](02_STORAGE_ARCHITECTURE.md) (S12-D5) |
| IF-32f | Client fingerprint binding + replay defense (seq + nonce) | ✅ | V1+30d | IF-32a | [02 §12AB.7](02_STORAGE_ARCHITECTURE.md) (S12-D6) |
| IF-32g | Versioned WS message schema (`contracts/ws/v1.yaml`) | ✅ | V1 | IF-32 | [02 §12AB.8](02_STORAGE_ARCHITECTURE.md) (S12-D7) |
| IF-32h | Lifecycle audit + enumerated close codes (1000, 4001–4010) | ✅ | V1 | IF-32, IF-22 | [02 §12AB.9](02_STORAGE_ARCHITECTURE.md) (S12-D8) |
| IF-32i | Forced disconnect via signed Redis control channel (<1s SLA) | ✅ | V1 | IF-32, IF-31g | [02 §12AB.10](02_STORAGE_ARCHITECTURE.md) (S12-D9) |
| IF-32j | WS observability + DF9/DF11 dashboards | ✅ | V1 | IF-32 | [02 §12AB.11](02_STORAGE_ARCHITECTURE.md) (S12-D10) |
| IF-32-split | Dedicated `ws-gateway` service split | 📦 | V1+30d | IF-32 | [02 §12AB.12](02_STORAGE_ARCHITECTURE.md) (S12-D10 trigger at >10K active conn/instance) |
| IF-33 | DF3 canonization security invariants (S13 pre-spec) | ✅ | V1 | — | [02 §12AC](02_STORAGE_ARCHITECTURE.md) (S13-D1..D10) |
| IF-33a | Author authority + `book_authorship` table + MetaWrite enforcement | ✅ | V1 | IF-33, IF-3 | [02 §12AC.2](02_STORAGE_ARCHITECTURE.md) (S13-D1) |
| IF-33b | Canonize/decanonize as S5 Tier 1 Destructive (symmetric) | ✅ | V1 | IF-33, IF-23 | [02 §12AC.3](02_STORAGE_ARCHITECTURE.md) (S13-D2) |
| IF-33c | Pre-canon validation pipeline (injection + PII + privacy + length + dup + lock-level) | ✅ | V1 | IF-33, IF-26d, IF-29e | [02 §12AC.4](02_STORAGE_ARCHITECTURE.md) (S13-D3) |
| IF-33d | `canon_entries` immutable provenance + content_hash | ✅ | V1 | IF-33 | [02 §12AC.5](02_STORAGE_ARCHITECTURE.md) (S13-D4) |
| IF-33e | `canonization_audit` (5y) + per-author/book/burst rate limits | ✅ | V1 | IF-33 | [02 §12AC.6](02_STORAGE_ARCHITECTURE.md) (S13-D5) |
| IF-33f | Post-erasure attribution preservation (S8 interaction) | ✅ | V1 | IF-33, IF-26 | [02 §12AC.7](02_STORAGE_ARCHITECTURE.md) (S13-D6) |
| IF-33g | Hot-propagation rate controls + observability | ✅ | V1+30d | IF-33, C4 (§12P) | [02 §12AC.8](02_STORAGE_ARCHITECTURE.md) (S13-D7) |
| IF-33h | Decanonization protocol + compensating events | ✅ | V1 | IF-33 | [02 §12AC.9](02_STORAGE_ARCHITECTURE.md) (S13-D8) |
| IF-33i | Canon injection defense: marker wrapping + canon-echo canary + quarterly retrospective scan | ✅ | V1+30d | IF-33, IF-29e | [02 §12AC.10](02_STORAGE_ARCHITECTURE.md) (S13-D9) |
| IF-33j | Cross-reality impact disclosure UX + 7d review SLA + mass-canonization detection | ✅ | V1+30d | IF-33 | [02 §12AC.11](02_STORAGE_ARCHITECTURE.md) (S13-D10) |
| IF-33-df3 | DF3 Canonization Author Review Flow (full feature) | 📦 | V2+ | IF-33 + DF3 | [DF3 entry](OPEN_DECISIONS.md); S13 invariants locked, full design pending |
| IF-34 | SLOs + error budget policy (SR1) | ✅ | V1 | — | [02 §12AD](02_STORAGE_ARCHITECTURE.md) (SR1-D1..D8) |
| IF-34a | User-journey SLI metrics (7 core SLIs) | ✅ | V1 | IF-34 | [02 §12AD.2](02_STORAGE_ARCHITECTURE.md) (SR1-D1) |
| IF-34b | Tiered SLO targets (free/paid/premium) | ✅ | V1 | IF-34a | [02 §12AD.3](02_STORAGE_ARCHITECTURE.md) (SR1-D2) |
| IF-34c | Error budget policy + burn-rate CI gating | ✅ | V1+30d | IF-34b | [02 §12AD.4](02_STORAGE_ARCHITECTURE.md) (SR1-D3) |
| IF-34d | Multi-tenant isolation SLO (noisy-neighbor + meta 99.99%) | ✅ | V1 | IF-34 | [02 §12AD.5](02_STORAGE_ARCHITECTURE.md) (SR1-D4) |
| IF-34e | Reliability review cadence (daily/weekly/monthly/quarterly) | ✅ | V1 | IF-34 | [02 §12AD.6](02_STORAGE_ARCHITECTURE.md) (SR1-D5) |
| IF-34f | Alert-to-SLO derivation + CI lint | ✅ | V1 | IF-34a | [02 §12AD.7](02_STORAGE_ARCHITECTURE.md) (SR1-D6) |
| IF-34g | Internal status page | ✅ | V1+30d | IF-34 | [02 §12AD.8](02_STORAGE_ARCHITECTURE.md) (SR1-D7) |
| IF-34g-public | Public status page + external SLA | 📦 | V2+ | IF-34g | [02 §12AD.8](02_STORAGE_ARCHITECTURE.md) (SR1-D7 post-monetization) |
| IF-34h | SLO observability cost controls (cardinality + retention tiers) | ✅ | V1 | IF-34 | [02 §12AD.9](02_STORAGE_ARCHITECTURE.md) (SR1-D8) |
| IF-35 | Incident classification + on-call rotation (SR2) | ✅ | V1 | IF-34 | [02 §12AE](02_STORAGE_ARCHITECTURE.md) (SR2-D1..D10) |
| IF-35a | Severity matrix SEV0–SEV3 + auto-escalation rules | ✅ | V1 | IF-35 | [02 §12AE.2](02_STORAGE_ARCHITECTURE.md) (SR2-D1) |
| IF-35b | On-call rotation structure (SRE/Security/Data specialty) | ✅ | V1 | IF-35 | [02 §12AE.3](02_STORAGE_ARCHITECTURE.md) (SR2-D2) |
| IF-35c | Alert routing table + fallback chain | ✅ | V1 | IF-35a, IF-34f | [02 §12AE.4](02_STORAGE_ARCHITECTURE.md) (SR2-D3) |
| IF-35d | Incident lifecycle 6-state machine | ✅ | V1 | IF-35 | [02 §12AE.5](02_STORAGE_ARCHITECTURE.md) (SR2-D4) |
| IF-35e | Incident Commander role + handoff protocol | ✅ | V1 | IF-35d | [02 §12AE.6](02_STORAGE_ARCHITECTURE.md) (SR2-D5) |
| IF-35f | Communication protocol + templates (war room/status/updates) | ✅ | V1 | IF-35, IF-34g | [02 §12AE.7](02_STORAGE_ARCHITECTURE.md) (SR2-D6) |
| IF-35g | `incidents` tracker table (5y, meta DB) | ✅ | V1 | IF-35 | [02 §12AE.8](02_STORAGE_ARCHITECTURE.md) (SR2-D7) |
| IF-35h | Review cadences + postmortem triggers | ✅ | V1 | IF-35g | [02 §12AE.9](02_STORAGE_ARCHITECTURE.md) (SR2-D8) |
| IF-35i | Privacy + security fast-paths (GDPR 72h / active attack / canon injection / audit tamper) | ✅ | V1 | IF-35a, IF-26, IF-33 | [02 §12AE.10](02_STORAGE_ARCHITECTURE.md) (SR2-D9) |
| IF-35j | Incident infrastructure independence (external PagerDuty + status page + runbook mirror) | ✅ | V1 | IF-35 | [02 §12AE.11](02_STORAGE_ARCHITECTURE.md) (SR2-D10) |
| IF-36 | Runbook library (SR3) | ✅ | V1 | IF-34f, IF-35 | [02 §12AF](02_STORAGE_ARCHITECTURE.md) (SR3-D1..D10) |
| IF-36a | Canonical runbook schema (YAML frontmatter + Markdown template) | ✅ | V1 | IF-36 | [02 §12AF.2](02_STORAGE_ARCHITECTURE.md) (SR3-D1) |
| IF-36b | Directory structure + auto-generated INDEX.md | ✅ | V1 | IF-36a | [02 §12AF.3](02_STORAGE_ARCHITECTURE.md) (SR3-D2) |
| IF-36c | 27-runbook V1 gate (required before production cutover) | ✅ | V1 | IF-36a | [02 §12AF.4](02_STORAGE_ARCHITECTURE.md) (SR3-D3) |
| IF-36d | 90-day verification cadence + overdue tracking | ✅ | V1 | IF-36 | [02 §12AF.5](02_STORAGE_ARCHITECTURE.md) (SR3-D4) |
| IF-36e | Three drift-detection CI lints (alert-sync + service-annotate + dead-ref) | ✅ | V1 | IF-36 | [02 §12AF.6](02_STORAGE_ARCHITECTURE.md) (SR3-D5) |
| IF-36f | Dry-run-first rule + CI enforcement | ✅ | V1 | IF-36a | [02 §12AF.7](02_STORAGE_ARCHITECTURE.md) (SR3-D6) |
| IF-36g | Generic triage runbooks (i-don-t-know + new-on-call + escalation) | ✅ | V1 | IF-36c | [02 §12AF.8](02_STORAGE_ARCHITECTURE.md) (SR3-D7) |
| IF-36h | External access inventory + break-glass fallback docs | ✅ | V1 | IF-36 | [02 §12AF.9](02_STORAGE_ARCHITECTURE.md) (SR3-D8) |
| IF-36i | Post-incident runbook update flow (action items + born_from_incident_id) | ✅ | V1 | IF-36, IF-35g | [02 §12AF.10](02_STORAGE_ARCHITECTURE.md) (SR3-D9) |
| IF-36j | Runbook accessibility (git + Notion mirror + on-call startup ritual) | ✅ | V1 | IF-36 | [02 §12AF.11](02_STORAGE_ARCHITECTURE.md) (SR3-D10) |
| IF-37 | Postmortem process (SR4) | ✅ | V1 | IF-35, IF-36 | [02 §12AG](02_STORAGE_ARCHITECTURE.md) (SR4-D1..D10) |
| IF-37a | Canonical postmortem template + CI structure lint | ✅ | V1 | IF-37 | [02 §12AG.2](02_STORAGE_ARCHITECTURE.md) (SR4-D1) |
| IF-37b | Blameless mechanisms (no-name rule + review gate + quarterly audit) | ✅ | V1 | IF-37a | [02 §12AG.3](02_STORAGE_ARCHITECTURE.md) (SR4-D2) |
| IF-37c | Authorship-by-severity + V1 solo-dev pattern | ✅ | V1 | IF-37, IF-35e | [02 §12AG.4](02_STORAGE_ARCHITECTURE.md) (SR4-D3) |
| IF-37d | 5-state review workflow + legal review trigger | ✅ | V1 | IF-37c | [02 §12AG.5](02_STORAGE_ARCHITECTURE.md) (SR4-D4) |
| IF-37e | Extended action item schema + lifecycle scanning | ✅ | V1 | IF-37, IF-35g | [02 §12AG.6](02_STORAGE_ARCHITECTURE.md) (SR4-D5) |
| IF-37f | Time-boxed deadlines + slip escalation + publication iteration | ✅ | V1 | IF-37d | [02 §12AG.7](02_STORAGE_ARCHITECTURE.md) (SR4-D6) |
| IF-37g | Root cause classification enum + quarterly pattern detection + auto-preventive-incident | ✅ | V1 | IF-37 | [02 §12AG.8](02_STORAGE_ARCHITECTURE.md) (SR4-D7) |
| IF-37h | Internal Full + Security-Restricted variants (V1) | ✅ | V1 | IF-37 | [02 §12AG.9](02_STORAGE_ARCHITECTURE.md) (SR4-D8) |
| IF-37h-public | Customer-Facing + Regulator-Facing variants | 📦 | V2+ | IF-37h | [02 §12AG.9](02_STORAGE_ARCHITECTURE.md) (SR4-D8 monetization+GDPR) |
| IF-37i | Sharing rituals (weekly/monthly Postmortem Hour/quarterly) + runbook back-lookup | ✅ | V1 | IF-37 | [02 §12AG.10](02_STORAGE_ARCHITECTURE.md) (SR4-D9) |
| IF-37j | Annual meta-review of postmortem process | ✅ | V1 | IF-37 | [02 §12AG.11](02_STORAGE_ARCHITECTURE.md) (SR4-D10) |
| IF-38 | Deploy safety + rollback (SR5) | ✅ | V1 | IF-34, IF-35 | [02 §12AH](02_STORAGE_ARCHITECTURE.md) (SR5-D1..D10) |
| IF-38a | Deploy class enum + CI classification lint | ✅ | V1 | IF-38 | [02 §12AH.2](02_STORAGE_ARCHITECTURE.md) (SR5-D1) |
| IF-38b | 4 deploy freeze mechanisms + break-glass-deploy override | ✅ | V1 | IF-38a, IF-34c | [02 §12AH.3](02_STORAGE_ARCHITECTURE.md) (SR5-D2) |
| IF-38c | 5-stage canary rollout + auto-abort at 2× baseline burn | ✅ | V1 | IF-38a, IF-3 | [02 §12AH.4](02_STORAGE_ARCHITECTURE.md) (SR5-D3) |
| IF-38d | Feature flags table + planned_removal_date + quarterly debt review | ✅ | V1 | IF-38 | [02 §12AH.5](02_STORAGE_ARCHITECTURE.md) (SR5-D4) |
| IF-38e | 6-phase schema migration protocol + `migration-orchestrator` + cohort rollout | ✅ | V1 | IF-38, IF-1 | [02 §12AH.6](02_STORAGE_ARCHITECTURE.md) (SR5-D5) |
| IF-38f | Config change PR requirements (diff + validation + dry-run + rollback) | ✅ | V1 | IF-38 | [02 §12AH.7](02_STORAGE_ARCHITECTURE.md) (SR5-D6) |
| IF-38f-backtest | Alert config backtest CI hook | ✅ | V1+30d | IF-38f, IF-34f | [02 §12AH.7](02_STORAGE_ARCHITECTURE.md) (SR5-D6) |
| IF-38g | Rollback decision framework + runbook + rollback-first bias | ✅ | V1 | IF-38, IF-36 | [02 §12AH.8](02_STORAGE_ARCHITECTURE.md) (SR5-D7) |
| IF-38h | `deploy_audit` table (5y) + alert/incident correlation | ✅ | V1 | IF-38, IF-35g | [02 §12AH.9](02_STORAGE_ARCHITECTURE.md) (SR5-D8) |
| IF-38i | Async change advisory for major + V1 solo-dev pattern | ✅ | V1 | IF-38a | [02 §12AH.10](02_STORAGE_ARCHITECTURE.md) (SR5-D9) |
| IF-38j | Deploy windows + CI enforcement | ✅ | V1 | IF-38a | [02 §12AH.11](02_STORAGE_ARCHITECTURE.md) (SR5-D10) |
| IF-14 | Provider-registry integration (BYOK credential resolution) | ✅ | INFRA | — | Reuse [98_CHAT_SERVICE_DESIGN §5.4](../98_CHAT_SERVICE_DESIGN.md) |
| IF-15 | LiteLLM multi-provider inference (with streaming) | ✅ | INFRA | IF-14 | Reuse [98_CHAT_SERVICE_DESIGN §6](../98_CHAT_SERVICE_DESIGN.md) |
| IF-16 | Per-reality locale primitive | ✅ | INFRA | IF-3 | [03 §8.3](03_MULTIVERSE_MODEL.md) (MV5 primitive P1) |
| IF-17 | Analytics ETL → ClickHouse (cross-reality aggregates) | 📦 | V3 | IF-1 | [02 §3 diagram](02_STORAGE_ARCHITECTURE.md) — optional |
| IF-18 | pgvector HNSW tuning + footprint monitoring | ✅ | V1 | IF-12 | [02 §12K](02_STORAGE_ARCHITECTURE.md) (R11) |
| IF-19 | Global event ordering — accepted trade-off (no mitigation; timestamp merge sufficient) | ✅ | INFRA | — | [02 §12J](02_STORAGE_ARCHITECTURE.md) (R10 ACCEPTED) |
| IF-20 | Admin command library (canonical, named, reviewed, versioned; no ad-hoc SQL) | ✅ | V1 | — | [02 §12L.1](02_STORAGE_ARCHITECTURE.md) (R13-L1) |
| IF-21 | Compensating-event pattern for admin changes | ✅ | V1 | IF-1 | [02 §12L.2](02_STORAGE_ARCHITECTURE.md) (R13-L2) |
| IF-22 | Admin action audit log (centralized, 2-year retention) | ✅ | V1 | IF-4 | [02 §12L.3](02_STORAGE_ARCHITECTURE.md) (R13-L3) |
| IF-23 | Destructive action confirmation + double-approval for dangerous commands | ✅ | V1 | IF-20 | [02 §12L.4](02_STORAGE_ARCHITECTURE.md) (R13-L4) |
| IF-24 | Admin UI guardrails (no raw DROP/UPDATE buttons, no free-form SQL in prod) | ✅ | V1 | — | [02 §12L.5](02_STORAGE_ARCHITECTURE.md) (R13-L5) |
| IF-27 | Admin rollback via compensating events | ✅ | V2 | IF-21 | [02 §12L.6](02_STORAGE_ARCHITECTURE.md) (R13-L6) |
| IF-28 | Admin Action Policy governance doc | ✅ | INFRA | — | [docs/02_governance/ADMIN_ACTION_POLICY.md](../../02_governance/ADMIN_ACTION_POLICY.md) (R13-governance) |

## WA — World Authoring

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| WA-1 | Book → glossary entity derivation (NPC pool, item pool, location pool) | 🟡 | V1 | — | Relies on glossary-service / knowledge-service (in progress) |
| WA-2 | Reality creation by author (first-reality-of-book = fresh seed) | 🟡 | V1 | IF-3 | [03 §5](03_MULTIVERSE_MODEL.md) |
| WA-3 | Canon lock level per attribute (L1 axiomatic vs L2 seeded) | ✅ | V1 | — | [03 §3](03_MULTIVERSE_MODEL.md), MV1 locked |
| WA-4 | Category-based L1 auto-assignment (magic-system, species → L1) | ✅ | V1 | WA-3 | [03 §3 "Category heuristics"](03_MULTIVERSE_MODEL.md); WA4-D1..D5 locked 2026-04-24 |
| WA-5 | Per-reality world rules (death behavior, paradox tolerance, PvP) | 📦 | V2+ | IF-1 | **DF4 — World Rule feature** |
| WA-6 | Author dashboard — canonization nominations, reality overview | 📦 | V3+ | WA-2 | Related to DF3 |
| WA-7 | Import/export books (portable format) | 📦 | V4+ | — | Marker: [100_FUTURE_FEATURE_STRUCTURED_IMPORT_EXPORT_MEDIA](../100_FUTURE_FEATURE_STRUCTURED_IMPORT_EXPORT_MEDIA.md) |

## PO — Player Onboarding

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PO-1 | User account (reuse existing auth-service + JWT) | ✅ | V1 | — | Existing M01 identity |
| PO-2 | Reality discovery UI — 7-layer: smart-funnel entry, composite ranking (friend/density/locale/canon/recency), friend-follow, flat browse with filters, create-new gating, metrics feedback | ✅ | V1 | IF-3, PO-2a, PO-2b, PO-2c | [03 §9.1](03_MULTIVERSE_MODEL.md#91-reality-discovery), M1-D1..D7 |
| PO-2a | Smart-funnel entry flow (resume-PC → friend-match → canon_attempt top → "be the first") | ✅ | V1 | PO-1 | [03 §9.1.1](03_MULTIVERSE_MODEL.md#911-entry-flow--smart-funnel-m1-d1), M1-D1 |
| PO-2b | Composite ranking engine (7 signals, config-driven weights) + metrics loop | ✅ | V1 | auth friend graph | [03 §9.1.2](03_MULTIVERSE_MODEL.md#912-composite-ranking-m1-d2), M1-D2/D7 |
| PO-2c | PC `presence_visibility` field + friend avatars on browse cards | ✅ | V1 | auth-service follow | [03 §9.1.3](03_MULTIVERSE_MODEL.md#913-friend-follow-layer-m1-d3), M1-D3 |
| PO-3 | Canonicality hint badges (canon_attempt / divergent / pure_what_if) | ✅ | V1 | PO-2 | MV3 locked |
| PO-4 | PC creation — fully custom | ✅ | V1 | IF-3 | [04 §3.1](04_PLAYER_CHARACTER_DESIGN.md), PC-A1 locked |
| PO-5 | PC creation — template-assisted | ✅ | V1 | PO-4 | [04 §3.1](04_PLAYER_CHARACTER_DESIGN.md) |
| PO-6 | PC creation — play-as-glossary-entity | ✅ | V1 | PO-4, WA-1 | [04 §3.2](04_PLAYER_CHARACTER_DESIGN.md), PC-A2 locked |
| PO-7 | PC slot quota (5 per user, configurable) | ✅ | V1 | PO-1 | [04 §5.1](04_PLAYER_CHARACTER_DESIGN.md), PC-C1 locked |
| PO-8 | PC slot purchase (buy more than 5) | 📦 | PLT | PO-7 | **DF2 — Monetization** |
| PO-9 | Reality switcher UI (one user navigates across their PCs in different realities) | 🟡 | V3 | PO-2 | Related to IF-4 |
| PO-10 | 3-tier user complexity model (Reader / Player / Author) + soft upgrade triggers | ✅ | V1 | PO-1 | [03 §9.6.2](03_MULTIVERSE_MODEL.md#962-three-tier-complexity-model-m7-d2), M7-D2 |
| PO-11 | 4-step onboarding tutorial (book page → overlay → postcard → tier-upgrade prompt); i18n EN+VI V1 | ✅ | V1 | PO-10 | [03 §9.6.3](03_MULTIVERSE_MODEL.md#963-onboarding-tutorial-m7-d3), M7-D3 |
| PO-12 | Contextual tooltips on multiverse UI elements (canonicality badges, fork CTA, friend avatar, hibernated, forked-from) | ✅ | V1 | PO-2, PO-10 | [03 §9.6.5](03_MULTIVERSE_MODEL.md#965-contextual-helpers-m7-d5), M7-D5 |
| PO-13 | User-facing terminology enforcement via copy style guide governance | ✅ | V1 | — | [UI_COPY_STYLEGUIDE.md](../../02_governance/UI_COPY_STYLEGUIDE.md), M7-D1/D4 |

## PL — Play Loop (core runtime)

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PL-1 | Session lifecycle (create, join, leave, dissolve) | 📦 | V1 | IF-1, IF-5 | **DF5 — Session feature** |
| PL-2 | Player command grammar (`/verb target [args]` MUD pattern) — deterministic dispatch, LLM narrates post-commit | ✅ | V1 | PL-1, PL-15 | [05 §3](05_LLM_SAFETY_LAYER.md#3-command-dispatch-a5), A5-D2 |
| PL-3 | Turn submission + validation | 🟡 | V1 | PL-1 | Depends on DF5 |
| PL-4 | Prompt assembly (system + canon-scoped retrieval + persona + history + sanitized user input with hard delimiters) | ✅ | V1 | NPC-2, NPC-4, PL-18, PL-19 | [05 §5.2](05_LLM_SAFETY_LAYER.md#52-layer-2--hard-delimiters-in-prompt-a6-d2), A6-D2 |
| PL-5 | LLM streaming inference | ✅ | V1 | IF-15 | Reuse [98 §6](../98_CHAT_SERVICE_DESIGN.md) |
| PL-6 | LLM tool-call allowlist (flavor-only; state mutations forbidden from LLM output) | ✅ | V1 | PL-5 | [05 §3.3](05_LLM_SAFETY_LAYER.md#33-llm-tool-calls--allowed-vs-forbidden-a5-d3), A5-D3/D4 |
| PL-15 | 3-intent classifier (command / fact question / free narrative) | ✅ | V1 | — | [05 §2](05_LLM_SAFETY_LAYER.md#2-three-intent-classifier-a5-d1), A5-D1 |
| PL-16 | World Oracle API (`oracle.query()` deterministic fact lookup) | ✅ | V1 | IF-1 | [05 §4](05_LLM_SAFETY_LAYER.md#4-world-oracle-a3), A3-D1..D4 |
| PL-17 | Oracle fact pre-computation (entity_location, entity_relation, L1_axiom, book_content, world_state_kv) + cache invalidation | ✅ | V1 | PL-16 | [05 §4.2](05_LLM_SAFETY_LAYER.md#42-pre-computed-fact-categories-a3-d2), A3-D2 |
| PL-18 | Canon-scoped retrieval (primary structural injection defense) — filter by pc_id + timeline_cutoff + reality_id BEFORE LLM | ✅ | V1 | IF-1, knowledge-service | [05 §5.3](05_LLM_SAFETY_LAYER.md#53-layer-3--canon-scoped-retrieval-a6-d3--critical), A6-D3 |
| PL-19 | Input sanitization + jailbreak-pattern detection | ✅ | V1 | — | [05 §5.1](05_LLM_SAFETY_LAYER.md#51-layer-1--input-sanitization-a6-d1), A6-D1 |
| PL-20 | Output filter (persona-break / cross-PC leak / spoiler / NSFW with soft-retry + hard-block) | ✅ | V1 | PL-5 | [05 §5.4](05_LLM_SAFETY_LAYER.md#54-layer-4--output-filter-a6-d4), A6-D4 |
| PL-21 | Per-PC retrieval isolation at DB layer (service-layer filter V1; RLS V2+) | ✅ | V1 | IF-1, knowledge-service | [05 §5.5](05_LLM_SAFETY_LAYER.md#55-layer-5--per-pc-retrieval-isolation-at-db-layer-a6-d5), A6-D5 |
| PL-22 | Player voice mode — 3 modes (terse / novel / mixed), V1 default = mixed, persisted per-book in user prefs | ✅ | V1 | PL-4, auth prefs | [01 C1](01_OPEN_PROBLEMS.md#c1-player-voice-vs-narrative-voice--partial), C1-D1/D4 |
| PL-23 | Inline voice override (`/verbatim`, `/prose`) for single turn | ✅ | V1 | PL-15, PL-22 | C1-D2 |
| PL-24 | World-Rule voice mode lock (per-reality override by author via DF4) | 📦 | V2 | PL-22, DF4 | C1-D3 |
| PL-25 | Voice mode consistency check in output filter (soft retry if terse→prose mismatch) | ✅ | V1 | PL-20, PL-22 | C1-D5; [05 §5.4](05_LLM_SAFETY_LAYER.md#54-layer-4--output-filter-a6-d4) |
| Q-1 | Quest scaffold schema (trigger / beats typed list / outcomes with rewards + world_effect) | ✅ | V1 | IF-1 | [01 F3](01_OPEN_PROBLEMS.md#f3-quest-design--emergent-or-scripted--partial), F3-D1 |
| Q-2 | Author-authored quest scaffolds via world-service admin UI | ✅ | V1 | Q-1, WA-3 | F3-D1 |
| Q-3 | LLM fill-in at runtime (scene, NPC dialogue, choice text; deterministic combat per R7/A5) | ✅ | V1 | Q-1, PL-4, PL-5 | F3-D2 |
| Q-4 | Book-canon quest seed extraction (knowledge-service surfaces tensions as candidates) | 📦 | V2 | Q-1, knowledge-service | F3-D3 |
| Q-5 | Emergent quest generation (LLM drafts from timeline) with author-review gate | 📦 | V3 | Q-1, Q-4, DF4 | F3-D4 |
| Q-6 | Quest discovery — proximity trigger (NPC in player region) | ✅ | V1 | Q-1, NPC-1 | F3-D5 |
| Q-7 | Quest discovery — rumor propagation (NPC gossip) | 📦 | V2 | Q-6, NPC-3 | F3-D5 |
| Q-8 | Quest discovery — explicit quest board (V2+ MMO) | 📦 | V2 | Q-1 | F3-D5 |
| Q-9 | Player-created quest scaffolds with canon-lock constraints (author opt-in per book) | 📦 | V3 | Q-1, DF4 | F3-D6 |
| PL-7 | Event emission + outbox publish | ✅ | V1 | IF-1, IF-6 | [02 §4.4](02_STORAGE_ARCHITECTURE.md) |
| PL-8 | Projection update (in-transaction sync) | ✅ | V1 | IF-1 | [02 §4.6](02_STORAGE_ARCHITECTURE.md) |
| PL-9 | Realtime broadcast (region subscribers see event) | 🟡 | V1 | IF-5, PL-7 | [02 §9](02_STORAGE_ARCHITECTURE.md) |
| PL-10 | Session history load (initial + pagination) | 🟡 | V1 | IF-1 | [02 §5](02_STORAGE_ARCHITECTURE.md) |
| PL-11 | Session replay (re-render past events) | 📦 | V2 | IF-1 | Available via event log; UI TBD |
| PL-12 | Swipe / regenerate variants (SillyTavern pattern) | 📦 | V2 | PL-5 | Feature comparison doc |
| PL-13 | Bookmarks / branch a session (SillyTavern pattern) | 📦 | V3 | PL-1 | Feature comparison doc |
| PL-14 | Reasoning pass-through (Claude extended thinking etc.) | 📦 | V2 | PL-5 | Feature comparison doc |

## NPC — NPC Systems

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| NPC-1 | NPC proxy derivation from glossary entity (per reality) | 🟡 | V1 | IF-3, WA-1 | [02 §5.2](02_STORAGE_ARCHITECTURE.md), [03 §2](03_MULTIVERSE_MODEL.md) |
| NPC-2 | NPC persona assembly (core_beliefs + flexible_state + per-PC memory) | 🟡 | V1 | NPC-1 | [02 §5.2](02_STORAGE_ARCHITECTURE.md); full prompt design in PL-4 |
| NPC-3 | Per-PC memory storage + retrieval | 🟡 | V1 | NPC-1, IF-12 | [01 A1](01_OPEN_PROBLEMS.md#a1-npc-memory-at-scale--partial) — infrastructure resolved by R8 ([02 §12H](02_STORAGE_ARCHITECTURE.md)); semantic layer partial |
| NPC-3a | NPC aggregate split (core + per-pair memory aggregates) | ✅ | V1 | IF-1 | [02 §12H.2](02_STORAGE_ARCHITECTURE.md) (R8-L1 locked) |
| NPC-3b | Bounded memory per pair (LRU facts + rolling summary) | ✅ | V1 | NPC-3a | [02 §12H.3](02_STORAGE_ARCHITECTURE.md) (R8-L2 locked) |
| NPC-3c | Snapshot size enforcement + auto-compaction | ✅ | V1 | NPC-3a | [02 §12H.4](02_STORAGE_ARCHITECTURE.md) (R8-L3 locked) |
| NPC-3d | Cold memory decay (30d/90d/365d) + archive/restore | ✅ | V2 | NPC-3a, IF-10 | [02 §12H.5](02_STORAGE_ARCHITECTURE.md) (R8-L4 locked) |
| NPC-3e | Lazy memory loading (session-scoped) | ✅ | V1 | NPC-3a, IF-5a | [02 §12H.6](02_STORAGE_ARCHITECTURE.md) (R8-L5 locked) |
| NPC-3f | Embedding storage separation (pgvector dedicated table) | ✅ | V1 | IF-12 | [02 §12H.7](02_STORAGE_ARCHITECTURE.md) (R8-L6 locked) |
| NPC-3g | Semantic retrieval quality (which facts to surface) | 🟡 | V1 | NPC-3a, NPC-4 | Needs V1 prototype measurement ([01 A1 semantic layer](01_OPEN_PROBLEMS.md#a1-npc-memory-at-scale--partial)) |
| NPC-3h | LLM summary rewrite prompt quality | 🟡 | V1 | NPC-3b | Needs V1 prototype measurement |
| NPC-4 | Retrieval from knowledge-service (timeline-scoped, canon-faithful) | ❓ | V1 | — | [01 A4](01_OPEN_PROBLEMS.md#a4-retrieval-quality-from-knowledge-service--partial) — needs measurement |
| NPC-5 | NPC mood / flexible_state drift (LLM output updates per-reality) | 🟡 | V1 | NPC-2 | [02 §5.2](02_STORAGE_ARCHITECTURE.md) |
| NPC-6 | Canon-drift linter — async post-response check against knowledge-service oracle, logs to `canon_drift_log` | ✅ | V1 | NPC-4, WA-3, IF-1 | [05_qa §4.1](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#41-layer-1--async-post-response-lint-g3-d1), G3-D1 |
| NPC-7 | Multi-NPC conversation turn arbitration | 🟡 | V2 | PL-1 | [01 B4](01_OPEN_PROBLEMS.md#b4-multi-user-turn-arbitration--partial), DF5 |
| NPC-8 | NPC daily routines when no player around | 📦 | V3 | NPC-1 | **DF1 — Daily Life** |
| NPC-9 | NPC memory decay / summarization (prevent unbounded growth) | 🟡 | V1 | NPC-3 | Part of A1 solution |
| NPC-10 | NPC tool calling (trigger world-state change via LLM) | 🟡 | V1 | PL-6 | [01 A5](01_OPEN_PROBLEMS.md#a5-tool-use-reliability-for-world-actions--partial) |
| NPC-11 | Classification (SillyTavern pattern — mood from last message) | 📦 | V3 | — | Feature comparison doc |

## PCS — PC Systems

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PCS-1 | PC state projection (location, status, stats, inventory) | ✅ | V1 | IF-1 | [02 §5.1](02_STORAGE_ARCHITECTURE.md), [04 §8](04_PLAYER_CHARACTER_DESIGN.md) |
| PCS-2 | PC inventory + item origin reality | ✅ | V1 | PCS-1 | [02 §5.1](02_STORAGE_ARCHITECTURE.md) (MV5 primitive P5) |
| PCS-3 | PC ↔ NPC relationship tracking | 🟡 | V1 | PCS-1 | [02 §5.1](02_STORAGE_ARCHITECTURE.md) |
| PCS-4 | PC stats model (simple state-based, no RPG mechanics) | 🟡 | V1 | PCS-1 | [04 §5.3](04_PLAYER_CHARACTER_DESIGN.md), PC-C3 locked, **DF7** concrete schema |
| PCS-5 | PC offline mode (visible + vulnerable) | 🟡 | V1 | PCS-1 | [04 §4.2](04_PLAYER_CHARACTER_DESIGN.md), PC-B2 locked |
| PCS-6 | PC `/hide` command + hidden status | 🟡 | V1 | PCS-5 | [04 §4.2](04_PLAYER_CHARACTER_DESIGN.md) |
| PCS-7 | PC-as-NPC conversion after prolonged hiding | 📦 | V2 | PCS-6, NPC-8 | **DF1 — Daily Life** |
| PCS-8 | PC death (event emission, per-reality outcome) | 🟡 | V1 | PCS-1, WA-5 | [04 §4.1](04_PLAYER_CHARACTER_DESIGN.md), PC-B1 locked; outcomes in **DF4** |
| PCS-9 | PC reclaim from NPC mode | 📦 | V2 | PCS-7 | **DF1** |
| PCS-10 | PC persona generation (LLM persona for NPC mode) | 📦 | V2 | PCS-7 | **DF8 — NPC persona from PC history** |

## SOC — Social

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| SOC-1 | Session as social unit (N PCs + M NPCs in one context) | 📦 | V1 | PL-1 | **DF5 — Session feature** |
| SOC-2 | Public session (in-region, all co-located participants join) | 📦 | V1 | SOC-1 | DF5 |
| SOC-3 | Private session (invite-only) | 📦 | V2 | SOC-1 | DF5 |
| SOC-4 | Whisper (1-to-1 private within session or across) | 📦 | V2 | SOC-1 | DF5 |
| SOC-5 | PvP within session | 📦 | V2 | SOC-1, WA-5 | DF5 + DF4 consent |
| SOC-6 | Multi-PC parties / raids / guilds | 🚫 | — | — | Explicitly rejected — sessions replace parties (PC-D1) |
| SOC-7 | Global chat | 🚫 | — | — | Explicitly rejected — session only (PC-D3) |
| SOC-8 | User reporting / content moderation UI | 📦 | PLT | SOC-1 | Standard platform feature |
| SOC-9 | Shadow-ban / sanctions | 📦 | PLT | SOC-8 | Standard |
| SOC-10 | NSFW opt-in / age verification | 📦 | PLT | — | [01 E2](01_OPEN_PROBLEMS.md) |

## NAR — Narrative / Canon

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| NAR-1 | Four-layer canon model (L1 axiomatic / L2 seeded / L3 local / L4 flexible) | ✅ | V1 | WA-3 | [03 §3](03_MULTIVERSE_MODEL.md) |
| NAR-2 | L3 event logging (every play emits durable events) | ✅ | V1 | IF-1 | [02 §4](02_STORAGE_ARCHITECTURE.md) |
| NAR-3 | L1 runtime enforcement (reject or lint output violating axiomatic canon) | 🟡 | V1 | NPC-6 | Part of NPC-6; may need DF4 integration |
| NAR-4 | L3 → L2 canonization flow (author-gated, author-only trigger, no player request queue) | 📦 | V3 | NAR-2, WA-6 | **DF3 — Canonization**; [03 §9.7.1](03_MULTIVERSE_MODEL.md#971-author-only-trigger-m3-d1), M3-D1 |
| NAR-5 | Canon-worthy action detection (eligibility flag + World-Rule defaults by category) | 📦 | V3 | NAR-2, NAR-9 | DF3; [03 §9.7.3](03_MULTIVERSE_MODEL.md#973-eligibility--consent-gates-m3-d3), M3-D3 |
| NAR-6 | Canon-diff UI for author review (5 mandatory sections + 5s delay + typed confirm) | 📦 | V3 | NAR-4 | DF3; [03 §9.7.2](03_MULTIVERSE_MODEL.md#972-diff-view-mandatory-m3-d2), M3-D2 |
| NAR-7 | IP attribution metadata for canonized content + author-controlled export | 📦 | V3 | NAR-4 | DF3 + [01 E3](01_OPEN_PROBLEMS.md); [03 §9.7.6](03_MULTIVERSE_MODEL.md#976-attribution--ip-metadata-m3-d6), M3-D6 |
| NAR-8 | L1/L2 author edit propagation — 6-layer author-safety UX (cascade preview, passive read-through default, optional force-propagate with 3-gate consent, L1 warnings, xreality channel reuse, change timeline) | ✅ | V1 | NAR-1, NAR-13..16 | [03 §9.8](03_MULTIVERSE_MODEL.md#98-canon-update-propagation--m4-resolution), M4-D1..D6 |
| NAR-13 | Cascade-impact preview modal before L1/L2 edit | ✅ | V1 | WA-3, NAR-8 | [03 §9.8.1](03_MULTIVERSE_MODEL.md#981-preview-before-l1l2-edit-m4-d1), M4-D1 |
| NAR-14 | Force-propagate L1/L2 change with 3-gate consent (edit opt-in + reality-owner consent + R13 audit) | 📦 | V3 | NAR-8, R13-L2 | [03 §9.8.3](03_MULTIVERSE_MODEL.md#983-optional-force-propagate-m4-d3), M4-D3; DF3-adjacent |
| NAR-15 | L1 axiomatic edit warnings (conflict listing + runtime canon-guardrail) | ✅ | V1 | NAR-3, NAR-8 | [03 §9.8.4](03_MULTIVERSE_MODEL.md#984-l1-axiomatic--louder-warnings-m4-d4), M4-D4 |
| NAR-16 | `xreality.canon.updated` event channel + meta-worker consumption | ✅ | V1 | R5-L2 meta-worker | [03 §9.8.5](03_MULTIVERSE_MODEL.md#985-xreality-event-channel-reuse-m4-d5), M4-D5 |
| NAR-17 | Glossary entity change timeline view with per-reality drill-down | ✅ | V1 | NAR-8, NAR-7 | [03 §9.8.6](03_MULTIVERSE_MODEL.md#986-glossary-entity-change-timeline-m4-d6), M4-D6 |
| NAR-9 | Per-PC canonization consent opt-in (default ON, sticky per PC) | ✅ | V1 | PO-4 | [03 §9.7.3](03_MULTIVERSE_MODEL.md#973-eligibility--consent-gates-m3-d3), M3-D3 |
| NAR-10 | 90-day canonization undo window + compensating-write for later reverts | 📦 | V3 | NAR-4 | DF3; [03 §9.7.5](03_MULTIVERSE_MODEL.md#975-reversibility--90-day-undo-window-m3-d5), M3-D5 |
| NAR-11 | L2 → L1 axiomatic promotion gate (R9 pattern: 7d cool + typed confirm + double approval) | 📦 | V3 | NAR-4 | DF3; [03 §9.7.4](03_MULTIVERSE_MODEL.md#974-l2--l1-promotion--harder-gate-m3-d4), M3-D4 |
| NAR-12 | Canonized content distinguishability (label + icon + export strip/footnote/appendix) | 📦 | V3 | NAR-4 | DF3; [03 §9.7.7](03_MULTIVERSE_MODEL.md#977-distinguishability-in-book-content-m3-d7), M3-D7 |

## EM — Emergent / Advanced (fork, travel, reality lifecycle)

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| EM-1 | Auto-fork on capacity (system-initiated, fresh seed) | ✅ | V1 | IF-3 | [03 §12.2](03_MULTIVERSE_MODEL.md), MV4-a locked |
| EM-2 | User-initiated fork (player creates alternate timeline) | ✅ | V1 | IF-3 | [03 §12.2](03_MULTIVERSE_MODEL.md), MV4-b locked |
| EM-3 | Auto-rebase at depth limit (flatten chain into fresh-seed) | ✅ | V1 | EM-2 | [03 §12.3](03_MULTIVERSE_MODEL.md), MV9 locked N=5 |
| EM-4 | DB subtree split at threshold (50M events or 500 players) | ✅ | V3 | IF-3 | MV8 locked |
| EM-5 | Reality freeze (no writes, reads OK) | ✅ | V2 | IF-11 | MV10 locked 30d |
| EM-6 | Reality archive (drop DB, events to MinIO) | ✅ | V2 | IF-11 | MV11 locked 90d |
| EM-7 | Reality close — safe multi-stage flow | ✅ | V1 | EM-6 | [02 §12I](02_STORAGE_ARCHITECTURE.md) (R9 locked) |
| EM-7a | 6-state close machine (active → pending_close → frozen → archived → archived_verified → soft_deleted → dropped) | ✅ | V1 | EM-7 | [02 §12I.1](02_STORAGE_ARCHITECTURE.md) (R9-L1) |
| EM-7b | Archive verification drill (checksum + sample decode + sample restore + diff) | ✅ | V1 | EM-6 | [02 §12I.3](02_STORAGE_ARCHITECTURE.md) (R9-L2) |
| EM-7c | Double-approval workflow for irreversible drop | ✅ | V1 | PO-1 | [02 §12I.4](02_STORAGE_ARCHITECTURE.md) (R9-L3) |
| EM-7d | 30-day cooling period with owner cancel | ✅ | V1 | EM-7a | [02 §12I.5](02_STORAGE_ARCHITECTURE.md) (R9-L4) |
| EM-7e | Player notification cascade (30/7/1 day) | ✅ | V2 | EM-7a | [02 §12I.6](02_STORAGE_ARCHITECTURE.md) (R9-L5) |
| EM-7f | Soft-delete via DB rename (not drop) + 90d hold | ✅ | V1 | EM-7a | [02 §12I.7](02_STORAGE_ARCHITECTURE.md) (R9-L6) |
| EM-7g | Emergency cancel at any pre-drop state | ✅ | V1 | EM-7a | [02 §12I.8](02_STORAGE_ARCHITECTURE.md) (R9-L7) |
| EM-7h | Full audit log of close state transitions | ✅ | V1 | EM-7a | [02 §12I.9](02_STORAGE_ARCHITECTURE.md) (R9-L8) |
| EM-8 | World travel — cross-reality PC movement | 📦 | V4 | IF-16, many primitives | **DF6 — World Travel** |
| EM-9 | Echo visit (read-only observation of another reality) | 📦 | V4 | IF-3 | DF6 sub-feature |
| EM-10 | Dimensional rift narrative events | 📦 | V4+ | EM-8 | DF6 |
| EM-11 | Reality "pin/protect" (prevent auto-freeze/archive) | 📦 | PLT | EM-5, EM-6 | Discussed but not locked |
| EM-12 | Freeze/archive warning notifications | 📦 | V2 | EM-5 | Discussed but not locked |
| EM-13 | Reality ancestry severance — orphan worlds (C1 resolution) | ✅ | V1 | EM-7 | [02 §12M](02_STORAGE_ARCHITECTURE.md) · [03 §9.9](03_MULTIVERSE_MODEL.md); C1-OW-1..5 locked 2026-04-24 |
| EM-13a | Auto-severance at ancestor `frozen` transition | ✅ | V1 | EM-13 | [02 §12M.2](02_STORAGE_ARCHITECTURE.md) (C1-OW-1) |
| EM-13b | Baseline snapshot + cascade-read severance logic | ✅ | V1 | EM-13 | [02 §12M.4](02_STORAGE_ARCHITECTURE.md) |
| EM-13c | `reality.ancestry_severed` in-world narrative event | ✅ | V1 | EM-13, IF-5c | [02 §12M.6](02_STORAGE_ARCHITECTURE.md) (C1-OW-3) |
| EM-13d | `ancestry_fragment_trail` lore display | ✅ | V2 | EM-13 | [02 §12M.7](02_STORAGE_ARCHITECTURE.md) (C1-OW-5) |
| EM-13e | Player notification cascade pre-severance | ✅ | V2 | EM-13, CC-1 | [02 §12M.5](02_STORAGE_ARCHITECTURE.md) |
| EM-14 | Vanish Reality Mystery System — pre-severance breadcrumbs for player discovery | 📦 | V3+ | EM-13 | **DF14** — [03 §9.9.6](03_MULTIVERSE_MODEL.md); short track registered 2026-04-24 |

## PLT — Platform / Business

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PLT-1 | Tier system — 3 tiers (Free BYOK / Paid platform-LLM / Premium) with feature gating mapped to B3/M1/M7/PC-C1/G3 | ✅ | PLT | PO-1 | [01 §D2](01_OPEN_PROBLEMS.md#d2-tier-viability--partial), D2-D1/D4; [103_PLATFORM_MODE_PLAN](../103_PLATFORM_MODE_PLAN.md) |
| PLT-2 | Usage metering (LLM tokens, cost tracking per user, per-session) + V1 measurement protocol feeding D1 | ✅ | PLT | IF-15 | D2-D5; reuse usage-billing-service |
| PLT-3 | PC slot purchase | 📦 | PLT | PO-8 | **DF2** |
| PLT-4 | Free tier = BYOK-only (user supplies LLM keys, zero platform marginal cost) | ✅ | V1 | PO-1, provider-registry | D2-D2 |
| PLT-5 | Per-tier monthly LLM budget cap with 1.5x margin target (exact numbers TBD post-V1) | 🟡 | PLT | PLT-2 | D2-D3/D6 |
| PLT-6 | Scheduled event hosting (author/platform timed events in popular realities) | 📦 | V2 | DF5, PL-1 | [01 §C3](01_OPEN_PROBLEMS.md#c3-cold-start-empty-world-problem--partial), C3-D4 |
| PLT-4 | Fork quota + cost calculation | 📦 | PLT | EM-2 | Related to DF2 |
| PLT-5 | Admin panel (users, realities, content) | 📦 | PLT | — | [103_PLATFORM_MODE_PLAN §7](../103_PLATFORM_MODE_PLAN.md) |
| PLT-6 | Billing integration (Stripe) | 📦 | PLT | PLT-1 | [103_PLATFORM_MODE_PLAN §5](../103_PLATFORM_MODE_PLAN.md) |
| PLT-7 | IP / ToS / DMCA workflow | ❓ | PLT | — | [01 E3/E4](01_OPEN_PROBLEMS.md) |
| PLT-8 | Self-hosted mode (BYOK only, no platform features) | ✅ | INFRA | IF-14 | [103 §1](../103_PLATFORM_MODE_PLAN.md) |

## CC — Cross-cutting

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| CC-1 | Chat GUI extension — region sidebar, player list, NPC panel, action bar, dual stream | 🟡 | V1 | PL-1 | [03 §9.1, feature comparison doc](03_MULTIVERSE_MODEL.md) |
| CC-2 | Multi-language support per reality (display + input) | 🟡 | V1 | IF-16 | Locale per reality; reuse translation-service |
| CC-3 | In-reality cross-language translation (user types Vietnamese, NPC replies English then auto-translates) | 📦 | V2 | CC-2 | Reuse translation-service |
| CC-4 | Reality browser / map view | 📦 | V2 | PO-2 | UI detail TBD |
| CC-5 | Observability — per-reality health dashboard, event lag metrics | 🟡 | INFRA | IF-3 | Standard ops |
| CC-6 | Accessibility — WCAG 2.2 AA compliance, ARIA live batched streaming, multi-stream semantic markup + per-stream mute, color-independent signaling, 44×44 tap targets, a11y mode toggle, axe-core CI gate + SR walkthrough | ✅ | V1 | — | [A11Y_POLICY.md](../../02_governance/A11Y_POLICY.md), CC-6-D1..D7 |
| CC-7 | Author dashboard (cross-reality view of their book's play) | 📦 | V3 | WA-6 | DF3 |
| CC-8 | Macros / variables in prompts (`{{pc}}`, `{{scene}}`, `{{entity.alice}}`) | 🟡 | V1 | PL-4 | SillyTavern pattern |
| CC-9 | User preferences / settings (per-device + per-account) | 🟡 | V1 | PO-1 | Reuse existing pattern |
| CC-10 | Tier 1 — unit tests with frozen mock LLM (prompt-hash keyed fixtures, <1s, per-PR) | ✅ | V1 | — | [05_qa §2.1](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#21-tier-1--unit-tests-with-frozen-mock-llm-g1-d1), G1-D1 |
| CC-11 | Tier 2 — nightly integration on cheap real LLM (~30 scenarios, 85% pass-rate threshold) | ✅ | V1 | CC-10 | [05_qa §2.2](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#22-tier-2--nightly-integration-on-real-llm-g1-d2), G1-D2 |
| CC-12 | Tier 3 — weekly LLM-as-judge scorecard (Sonnet/GPT-4.1 rubric) | ✅ | V1 | CC-10, CC-11 | [05_qa §2.3](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#23-tier-3--weekly-llm-as-judge-evaluation-g1-d3), G1-D3 |
| CC-13 | `admin-cli regen-fixtures` + scenario library at `docs/05_qa/LLM_TEST_SCENARIOS.md` | ✅ | V1 | admin-cli, CC-10 | [05_qa §2.4–2.5](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#24-fixture-maintenance-g1-d4), G1-D4/D5 |
| CC-14 | `loadtest-service` — synthetic user simulator with script library (casual/combat/fact/jailbreak) | 📦 | V1 | — | [05_qa §3.4](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#34-synthetic-user-simulator--loadtest-service-g2-d4), G2-D4 |
| CC-15 | Tiered load-test matrix — mocked high-conc V1 / real low-conc staging / full-stack pre-prod (V1 50/$50 → V3 1000/$1000) | ✅ | V1 | CC-14 | [05_qa §3.1–3.3](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#31-tier-1--mocked-llm-high-concurrency-g2-d1), G2-D1/D2/D3 |
| CC-16 | Load-test authorization + hard budget kill-switch (admin `loadtest.execute` token, 2h max, 80% alert, 100% stop) | ✅ | V1 | admin-cli, R13 | [05_qa §3.5](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#35-authorization--kill-switch-g2-d5), G2-D5 |
| CC-17 | User "that's not right" report button on NPC responses (4 categories + free text, creates review ticket) | ✅ | V1 | NPC-6 | [05_qa §4.2](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#42-layer-2--user-thats-not-right-button-g3-d2), G3-D2 |
| CC-18 | Per-reality drift metrics dashboard (DF9 surface) with alert thresholds | 📦 | V2 | NPC-6, DF9 | [05_qa §4.3](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#43-layer-3--drift-metrics-dashboard-g3-d3), G3-D3 |
| CC-19 | Auto-remediation on drift (memory regen, persona rotation, NPC suspension on severe drift) | 📦 | V2 | NPC-6, R8-L2 | [05_qa §4.4](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#44-layer-4--auto-remediation-g3-d4), G3-D4 |
| CC-20 | Production drift → G1 fixtures feedback loop (`admin-cli promote-drift-to-fixture`) | ✅ | V1 | NPC-6, CC-13 | [05_qa §4.5](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#45-layer-5--feedback-loop-to-test-fixtures-g3-d5), G3-D5 |
| CC-21 | Canon-drift SLOs per platform tier (free <5%, paid <2%, premium <0.5%) | 📦 | PLT | CC-18, 103_PLATFORM_MODE_PLAN | [05_qa §4.6](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#46-canon-drift-slos-per-platform-tier-g3-d6), G3-D6 |

## DL — Daily Life (DF1 umbrella)

Scoped for clarity. Everything here is `📦 Deferred` under DF1.

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| DL-1 | NPC daily routines (sleep, work, travel, socialize) | 📦 | V3 | NPC-1 | DF1 |
| DL-2 | Converted PC behavior (when PC becomes NPC) | 📦 | V2 | PCS-7 | DF1 |
| DL-3 | NPC memory decay / periodic summarization | 📦 | V1/V2 | NPC-3 | Partially required for V1 (bounded memory) — design in DF1 |
| DL-4 | PC reclaim UX | 📦 | V2 | PCS-7 | DF1 |
| DL-5 | World simulation tick — 3-mode framework (frozen V1 default / lazy-when-visited V2 / scheduled V3), per-reality World Rule configurable, daily budget cap, platform-tier aware | ✅ | V1 (frozen) · V2 (lazy) · V3 (scheduled) | DF4 World Rules | [01 B3](01_OPEN_PROBLEMS.md#b3-world-simulation-tick--partial), B3-D1..D5 |
| DL-5a | Reality clock (`reality_registry.reality_time`, 1:5 real-to-in-world ratio default) | ✅ | V1 | IF-3 | B3-D4 |
| DL-5b | Lazy-when-visited summary (LLM 1-call per region visit after gap threshold) | 📦 | V2 | DL-5, roleplay-service | B3-D2 |
| DL-5c | Scheduled-tick cron with daily budget cap + idle-skip | 📦 | V3 | DL-5, meta-worker | B3-D3 |
| DL-6 | NPC persona generation from PC history | 📦 | V2 | PCS-10 | DF8, part of DF1 |

---

## Status summary

| Category | ✅ Designed | 🟡 Partial | 📦 Deferred | ❓ Open | 🚫 OOS | Total |
|---|---|---|---|---|---|---|
| IF | 248 | 4 | 21 | 0 | 0 | 273 |
| WA | 2 | 2 | 3 | 0 | 0 | 7 |
| PO | 6 | 2 | 1 | 0 | 0 | 9 |
| PL | 4 | 7 | 3 | 0 | 0 | 14 |
| NPC | 6 | 10 | 2 | 0 | 0 | 18 |
| PCS | 2 | 5 | 3 | 0 | 0 | 10 |
| SOC | 0 | 0 | 8 | 0 | 2 | 10 |
| NAR | 2 | 1 | 4 | 1 | 0 | 8 |
| EM | 20 | 0 | 6 | 0 | 0 | 26 |
| PLT | 1 | 2 | 4 | 1 | 0 | 8 |
| CC | 0 | 5 | 3 | 1 | 0 | 9 |
| DL | 0 | 0 | 5 | 1 | 0 | 6 |
| **Total** | **291** | **38** | **63** | **3** | **2** | **397** |

### Interpretation

- **246 Designed** (green): concrete decisions in locked docs — storage, fork, canon model, PC mechanics, R1-R13, M1-M7, WA-4, C1-C5, H1-H6 + M-REV-1..6 + P1-P4, S1-S13, plus **SR1 SLOs + Error Budget Policy (2026-04-24) — 8 decisions, 7 user-journey SLIs (session-availability, turn-completion, event-delivery, realtime-freshness, auth-success, admin-action, cross-reality-propagation), tiered SLO targets (free/paid/premium), error budget policy with 4-tier burn-rate response including feature freeze at ≥90%, multi-tenant isolation SLO (noisy-neighbor + meta 99.99%), reliability review cadence (daily→annual), alert-to-SLO derivation with CI lint, public status page V2+, cardinality + retention cost controls**.

**All 21 SA+DE adversarial + 13 Security (S1-S13) resolved.** Storage + multiverse design fully locked pending external-dependent V1 prototype data. **SRE / Incident Response review in progress (5/12 done)**: SR1 SLOs + SR2 Incident Classification + SR3 Runbook Library + SR4 Postmortem Process + **SR5 Deploy Safety + Rollback (2026-04-24) — 12 decisions, deploy class enum (patch/minor/major/emergency) with CI classification lint, 4 freeze mechanisms (SLO burn + scheduled + incident + security) with break-glass override, 5-stage canary rollout (internal → 1% → 10% → 50% → 100%) with auto-abort at 2× baseline burn, feature flags table with mandatory planned_removal_date + quarterly debt review, 6-phase schema migration protocol (pre-flight → additive → deploy code → backfill → cutover → remove) with migration-orchestrator + cohort rollout, config change PR requirements (diff + validation + dry-run + rollback), rollback decision framework per change type with rollback-first bias, `deploy_audit` table (5y) with alert/incident auto-correlation, async change advisory for major with V1 solo-dev pattern, deploy windows Mon-Thu 10-16 with CI enforcement; `reality_registry.deploy_cohort` + `feature_flags` + `deploy_audit` tables** — SR6-SR12 pending.

**All 13 storage risks (R1–R13) resolved + C1 from SA+DE adversarial review resolved via orphan-worlds reframe. Storage + multiverse design design-complete** (residual items external-data-dependent: A4 benchmark, D1 cost, E3 legal).
- **38 Partial** (yellow): broad strokes designed, concrete detail pending (prompt assembly, retrieval quality, realtime).
- **44 Deferred** (blue): explicitly pushed to DF1–DF14 (DF12 withdrawn) future design docs or platform mode. Known but not gating V1.
- **3 Open** (red): identified but no approach — NPC-4 (retrieval quality), NAR-8 (L1/L2 propagation), CC-6 (a11y). A1 moved to PARTIAL with R8 infrastructure resolution.
- **2 Out of scope**: no parties (SOC-6), no global chat (SOC-7) — deliberate anti-MMO choices.

## V1 scope (solo RP, single reality)

Features marked `V1` (33 items) + required `INFRA` (17 items) = 50 total features to build for a working solo RP prototype.

Critical-path `❓ Open` blocking V1:
- **NPC-3** (per-PC memory) — needs [01 A1](01_OPEN_PROBLEMS.md#a1-npc-memory-at-scale--open) solution
- **NPC-4** (retrieval quality) — needs [01 A4](01_OPEN_PROBLEMS.md#a4-retrieval-quality-from-knowledge-service--partial) measurement

Non-blocking but must address:
- **PL-4** (prompt assembly) — concrete recipe needed
- **CC-6** (accessibility) — must not be afterthought

## V2 scope (coop, 2–4 players per reality)

Add `V2` items (18 items): session features (DF5), PvP, PC-as-NPC conversion (DF1 core), reality freeze/archive, swipe/regenerate, session replay, cross-language, freeze warnings.

## V3 scope (persistent multiverse)

Add `V3` items (14 items): DB subtree split, reality resurrect, author dashboard, canonization (DF3), L1/L2 propagation, NPC daily routines (DF1 full), world simulation tick, cross-reality browser.

## V4+ scope (vision, far-future)

Add `V4` items (4 items): world travel (DF6), echo visit, dimensional rifts, rich media (book import/export).

---

## Relationships visualized

```
                     FEATURE DEPENDENCY CLUSTERS

    ┌─────────────── INFRA (IF-*) ───────────────┐
    │ Storage → Registry → Realtime → LLM gateway │
    └───────────────────────┬─────────────────────┘
                            │
              ┌─────────────┼──────────────┐
              ▼             ▼              ▼
    ┌─────────────┐  ┌────────────┐  ┌──────────┐
    │ WORLD AUTH  │  │ PLAY LOOP  │  │ PLATFORM │
    │ (WA)        │  │ (PL)       │  │ (PLT)    │
    └──────┬──────┘  └──────┬─────┘  └────┬─────┘
           │                │             │
           ▼                ▼             ▼
    ┌──────────┐     ┌──────────┐    ┌──────────┐
    │ PO + PCS │     │ NPC      │    │ SOC      │
    │ (players)│     │ (AI chars)│   │ (groups) │
    └─────┬────┘     └────┬─────┘    └────┬─────┘
          │               │               │
          └───────┬───────┴───────────────┘
                  ▼
          ┌───────────────┐
          │ NAR (canon)   │
          │ EM (advanced) │
          │ DL (daily life│
          │ CC (UI/i18n)  │
          └───────────────┘
```

## References

- [00_VISION.md](00_VISION.md) — why this exists
- [01_OPEN_PROBLEMS.md](01_OPEN_PROBLEMS.md) — risks indexed by category
- [02_STORAGE_ARCHITECTURE.md](02_STORAGE_ARCHITECTURE.md) — IF-* detail
- [03_MULTIVERSE_MODEL.md](03_MULTIVERSE_MODEL.md) — WA-3, EM-1 to EM-6 detail
- [04_PLAYER_CHARACTER_DESIGN.md](04_PLAYER_CHARACTER_DESIGN.md) — PO, PCS, SOC detail; DF1–DF8 registry
- [OPEN_DECISIONS.md](OPEN_DECISIONS.md) — all locked + pending decisions
- [../References/SillyTavern_Feature_Comparison.md](../References/SillyTavern_Feature_Comparison.md) — inspirations for PL-*, NPC-*, CC-8
