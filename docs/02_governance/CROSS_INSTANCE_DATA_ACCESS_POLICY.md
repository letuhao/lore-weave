# Cross-Instance Data Access Policy

> **Status:** Policy — enforced at code review and architecture review
> **Applies to:** All services that touch reality DBs (world-service, roleplay-service, meta-worker, api-gateway-bff, any future service)
> **Source:** Derived from [docs/03_planning/LLM_MMO_RPG/02_STORAGE_ARCHITECTURE.md §12E](../03_planning/LLM_MMO_RPG/02_STORAGE_ARCHITECTURE.md)
> **Created:** 2026-04-23
> **Owner:** Tech Lead

---

## 1. Policy

**Cross-instance live queries across reality DBs are not a supported API pattern.**

The LoreWeave platform runs a DB-per-reality architecture (up to thousands of Postgres DBs). Federation across these DBs at query time — via `postgres_fdw`, application-level fan-out, or ad-hoc parallel connections — is rejected as a runtime mechanism for feature code.

## 2. Why

- Postgres federation tools do not scale to thousands of shards
- App-level fan-out in user-facing code paths produces unpredictable latency and fragile error surfaces
- Every cross-instance query adds to blast radius during incidents
- No confirmed product feature requires live cross-instance queries — every candidate use case maps cleanly to one of the approved alternatives below

## 3. Approved alternatives

When a feature appears to require cross-instance data, redesign as one of:

### 3.1 Meta-level lookup

Promote the needed field to the meta registry:
- `reality_registry` for reality-scoped attributes
- `player_character_index` for user↔PC↔reality mappings
- Additional meta tables only with feature-specific justification

Updated via event-driven push from reality DBs (§3.2), not polled.

**Use for:**
- User dashboard "my PCs" — meta lookup on `player_character_index`
- Reality discovery / browser — meta lookup on `reality_registry`
- Reality population / stats — field on `reality_registry`

### 3.2 Event-driven propagation

Producer emits an event; consumers listen and update their local state (meta registry or in-reality projection).

Transport: Redis Streams on `xreality.*` namespace (or successor bus).

Consumer pattern: at-least-once delivery with dedup, retry with backoff, poison-pill queue for persistent failures.

**Use for:**
- Author canon updates → realities need L1/L2 sync
- User deletion → realities where user has PC
- Reality stats heartbeat → meta registry

### 3.3 Import/export between specific realities

Atomic hand-off between two named realities, via meta event queue. Not a query — a transfer.

Pattern:
1. Freeze source data
2. Export bundle
3. Transfer via queue
4. Import to target
5. Tombstone source / update meta

**Use for:**
- World travel (DF6) — PC moves between realities
- Future: content migration between realities (e.g., authorized canonical transfer)

### 3.4 Admin ad-hoc federated query

**ONLY** for admin/operational tasks. Strict rules:

- Rate-limited: max 1 per minute per admin
- Timeout-bounded: max 30 seconds total
- Audit-logged: every invocation
- Never in user-facing request path
- Never called from automated feature code

**Use for:**
- Incident response
- Legal discovery
- Deep debugging of cross-reality bug patterns

## 4. Rejected patterns

The following are **not acceptable** in any feature code:

| Pattern | Why rejected |
|---|---|
| `postgres_fdw` federation across reality DBs | Query planner chokes at N=1000; full cross-shard scans |
| App-level fan-out in user request path | Latency explosion; fragile error handling |
| Ad-hoc direct connections to multiple reality DBs in realtime | Blast-radius expansion; connection pool exhaustion |
| Shared tables across reality DBs via replication | Contradicts blast-radius-per-reality invariant |
| Polling multiple realities for "is anyone there" checks | Use event-driven presence signals instead |

## 5. Enforcement

### 5.1 Code review

Reviewers must reject PRs that:
- Import multiple reality DB connection drivers in realtime code paths
- Add `postgres_fdw` configuration for reality DBs
- Introduce functions that iterate over all reality DBs in user-facing paths

When a feature appears to need cross-instance data, the contributor must:
1. Document the feature's actual data need
2. Map to §3 (Meta / Event / Import-Export / Admin)
3. If none fit, file an ADR proposing a new approved pattern

### 5.2 Architecture review

Any proposal for a new cross-instance mechanism requires:
- Written ADR referencing this policy
- Tech Lead approval
- Update to this policy document if approved

### 5.3 Deviation ADR

If an exception is required (extremely rare), file ADR documenting:
- Specific use case
- Why §3 alternatives do not fit
- Mitigations for performance / blast-radius concerns
- Expected review date (default 6 months)

No exceptions are currently active.

## 6. Codified decisions

| Decision | Source |
|---|---|
| No DF12 (Cross-Reality Analytics & Search) registered | R5-DF12 locked as WITHDRAWN on 2026-04-23 |
| Meta-worker service is the dedicated consumer for `xreality.*` events | R5-L2-service locked 2026-04-23 |
| ClickHouse / OLAP tooling deferred indefinitely | R5-L3 locked 2026-04-23 |
| Admin federated query config: 1/min, 30s timeout | R5-impl-order 2026-04-23 |

## 7. References

- [docs/03_planning/LLM_MMO_RPG/02_STORAGE_ARCHITECTURE.md §12E](../03_planning/LLM_MMO_RPG/02_STORAGE_ARCHITECTURE.md) — full R5 mitigation
- [docs/03_planning/LLM_MMO_RPG/03_MULTIVERSE_MODEL.md](../03_planning/LLM_MMO_RPG/03_MULTIVERSE_MODEL.md) — reality isolation invariants
- [docs/03_planning/LLM_MMO_RPG/OPEN_DECISIONS.md](../03_planning/LLM_MMO_RPG/OPEN_DECISIONS.md) — R5-* decision log
- World travel design (DF6, future) — the only sanctioned cross-reality feature
