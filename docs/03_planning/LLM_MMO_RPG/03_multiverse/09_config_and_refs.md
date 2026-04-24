<!-- CHUNK-META
source: 03_MULTIVERSE_MODEL.ARCHIVED.md
chunk: 09_config_and_refs.md
byte_range: 50972-56329
sha256: e28d862d55820c116115f943985ea6bbb788dfcfbf68ef4f852448219f5d6ee6
generated_by: scripts/chunk_doc.py
-->

## 12. Configuration & decisions status

### 12.1 Tunable configuration values

All thresholds are **configuration-driven, not hardcoded**. Platform-wide defaults ship in service config; per-book overrides may be supported later (platform-mode feature). Suggested config namespace: `multiverse.*`

| Config key | Locked value | Scope |
|---|---|---|
| `multiverse.reality.player_cap` | 100 | Per-reality max concurrent PCs |
| `multiverse.subtree_split.max_events` | 50,000,000 | Trigger DB subtree split |
| `multiverse.subtree_split.max_concurrent_players` | 500 | Trigger DB subtree split |
| `multiverse.fork.depth_limit` | 5 | Before auto-rebase triggers |
| `multiverse.fork.auto_rebase` | true | At depth limit, flatten chain into fresh-seeded reality with snapshot |
| `multiverse.freeze.inactive_days` | 30 | Days of no activity → freeze |
| `multiverse.archive.frozen_days` | 90 | Days frozen → archive to MinIO |

Env vars or config file. Changes require service restart in V1; dynamic reload in V3+.

### 12.2 Fork policy (locked)

| Fork type | Seed mode | Who triggers | Storage amplification |
|---|---|---|---|
| **Auto-fork** (capacity sharding) | **Fresh from book** | System, at `player_cap` overflow | None — fresh reality = empty projection |
| **User-fork** (narrative) | User chooses: fresh OR snapshot from any reality at any event | Any user | Snapshot = projection populated lazily as child diverges |
| **Author-first-reality** | Fresh from book | Author, first time book opens for play | None |

**Why auto-fork = fresh (not snapshot from parent):** snapshot-fork does not copy events physically, but it does force child-reality projection tables to populate from ancestor chain on first read. For capacity-driven sharding where narrative continuity between parent and child is not needed, fresh seed avoids this amplification entirely. Each auto-forked sibling is a "new WoW server" — clean start, independent evolution.

**Why user-fork allows snapshot:** the whole point of a user-initiated fork is "branch from THIS reality at THIS moment to explore an alternative." Inheritance is the feature, not a cost.

**Load balancing:** players are NOT moved between auto-forked siblings. Once joined, a player stays in their reality until they explicitly leave (via future world-travel feature). Parent reality does not drain.

**User fork policy (V1):** no quota, no gate, user is world creator. Quota / cost / review are a future feature. Default: anyone can fork anything.

### 12.3 Fork depth — auto-rebase

When a new fork would exceed depth limit N (default 5):

1. System computes a **flattened snapshot** of the ancestor chain at the requested fork point
2. New reality is created as **fresh-seeded with that snapshot as its initial state**
3. New reality's `parent_reality_id = NULL`, `seeded_from = 'rebase_snapshot'`, `rebase_source_reality_id = X` (audit trail)
4. New reality's ancestry is collapsed — no further cascading read needed

User does not lose state; they only lose "lineage visibility." The new reality looks like a fresh one that happens to have a non-empty initial state.

This makes depth limit non-blocking: user can always fork, but at depth N+1 the system transparently rebases.

### 12.4 Decisions status

| Decision | Answer | Status |
|---|---|---|
| Fork semantics | Snapshot fork | **LOCKED** |
| Model name | Multiverse | **LOCKED** |
| L1 axiomatic definition | Manual + category-based | **LOCKED** |
| Canonization allowed | Yes, author-gated explicit action | **LOCKED** |
| Canonicality badge in UI | Yes, discovery hint only | **LOCKED** |
| Player cap per reality | 100 (configurable) | **LOCKED** |
| DB subtree split threshold | 50M events OR 500 players (configurable) | **LOCKED** |
| Fork policy (auto + user) | Both; auto=fresh, user=choice; no drain, no quota | **LOCKED** |
| Seed mode | Resolved by MV4 (auto=fresh, user=choice, first-of-book=fresh) | **LOCKED** |
| Auto-freeze inactive reality | 30 days (configurable) | **LOCKED** |
| Auto-archive frozen reality | 90 days (configurable) | **LOCKED** |
| Fork depth strategy | Auto-rebase at N=5 (configurable) | **LOCKED** |
| Cross-reality travel | Deferred to future world-travel feature | **LOCKED (as deferred)** |

**MV5 primitives locked now** — see [OPEN_DECISIONS.md §"MV5 primitives"](OPEN_DECISIONS.md). Schema must accommodate future travel:
- P1: Reality has `locale` field
- P4: Event metadata reserves `travel_origin_reality_id` + `travel_origin_event_id` (nullable, unused in V1)
- P5: Inventory items have `origin_reality_id` (nullable)

Incorporated into §8 schema below.

See [OPEN_DECISIONS.md](OPEN_DECISIONS.md) for complete decision history.

## 13. References

- [00_VISION.md](00_VISION.md)
- [01_OPEN_PROBLEMS.md](01_OPEN_PROBLEMS.md) — A2, C4, F1 moved to PARTIAL; M1–M7 added
- [02_STORAGE_ARCHITECTURE.md](02_STORAGE_ARCHITECTURE.md) — engineering baseline, receives schema adjustments in §8
- [OPEN_DECISIONS.md](OPEN_DECISIONS.md) — all pending decisions including defaults above
- SCP Foundation canon structure (hubs, alternate canons, reality-bender SCPs) — conceptual inspiration
- Copy-on-write branching patterns: Git, Dolt (OLTP branchable DB), Prolly trees, Datomic as-of queries
