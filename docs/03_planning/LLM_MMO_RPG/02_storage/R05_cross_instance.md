<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: R05_cross_instance.md
byte_range: 72787-80681
sha256: 7dd1082731c207b350feb3954bfdc6017754ced100e404c98682102d3b073a26
generated_by: scripts/chunk_doc.py
-->

## 12E. Cross-Instance Data Access (R5 mitigation)

Cross-reality queries across N reality DBs are rejected as an API pattern. This section locks the alternative: a tight 3-layer model for every legitimate cross-instance need, plus an explicit anti-pattern rule.

### 12E.1 Core insight — no product feature requires live cross-instance query

Review of every candidate "cross-reality query" reveals:

| Candidate use case | Classification |
|---|---|
| User "my PCs" dashboard | Meta-level lookup (`player_character_index`) |
| Reality discovery / browser | Meta-level lookup (`reality_registry`) |
| All realities of a book | Meta-level lookup |
| Reality population stats | Meta-level field |
| Canon update propagation | Event-driven push, not query |
| User deletion cascade | Event-driven push |
| Top NPCs / leaderboards | **Not a product feature** (rejected by ethos SOC-6/7) |
| Analytics (retention, cohort) | Admin/business, **defer indefinitely** |
| Moderation ("all content by user") | Admin, slow ad-hoc acceptable |
| Admin "find realities matching X" | Admin, rare |
| Cross-book entity search | **Not a confirmed feature** |
| World travel | **Import/export** (DF6), not query |

**The only cross-reality feature** is world travel (DF6), handled as atomic import/export between two specific reality DBs + meta registry update. Not a query.

No product feature in V1–V4 roadmap requires live cross-instance query. Design accordingly.

### 12E.2 Layer 1 — Meta registry lookups (minimal)

Existing meta registry tables cover current needs:

- `reality_registry` — book_id, locale, status, current_player_count, canonicality_hint, etc.
- `player_character_index` — user_id → pc_id → reality_id → name → last_seen → status

**Extension policy:** add fields lazily when a feature demands them, not speculatively.

**Near-term additions (locked):**
```sql
ALTER TABLE reality_registry
  ADD COLUMN trending_score FLOAT DEFAULT 0,       -- V2+: discovery sort by popularity
  ADD COLUMN last_stats_updated_at TIMESTAMPTZ;    -- heartbeat for reality→meta sync
```

**Rejected (not building):**
- `user_reality_activity_index` — no justifying use case (PC count is user-scope, not reality-scope)
- `reality_popularity_index` — a single field on `reality_registry` suffices
- Separate entity search index — no confirmed feature

Discipline: every new meta field requires a mapped feature. No premature indexes.

### 12E.3 Layer 2 — Event-driven propagation (dedicated service)

Push, not pull. Narrow scope — only the cross-instance state that actually needs to cross boundaries.

**Topics (locked):**

| Topic | Producer | Consumer | Purpose |
|---|---|---|---|
| `xreality.book.canon.updated` | book-service, glossary-service | Each reality subscribed to book_id | L1/L2 canon sync ([M4](01_OPEN_PROBLEMS.md#m4-inconsistent-l1l2-updates-across-reality-lifetimes--open) resolved) |
| `xreality.user.deleted` | auth-service | All realities where user has PC | GDPR purge; convert PC to orphan NPC |
| `xreality.reality.stats` | Each reality | meta-worker | Update registry fields (`current_player_count`, etc.) |

**Dedicated service: `meta-worker` (Go, small, narrow-scope).** Reasons:
- Clear boundary (consumes xreality.* topics, writes to meta registry)
- Reusable across future propagation needs
- Easier to reason about restart/retry state

**Transport:** Redis Streams (reuse IF-5). Separate namespace `xreality.*` to distinguish from intra-reality streams.

**Consumer protocol:**
- At-least-once delivery (dedupe via correlation_id)
- Retry with exponential backoff (3 attempts default)
- Poison-pill queue for persistent failures → manual review

**Config:**
```
xreality.topics.book_canon_updated = "xreality.book.canon.updated"
xreality.topics.user_deleted = "xreality.user.deleted"
xreality.topics.reality_stats = "xreality.reality.stats"
xreality.meta_worker.concurrency = 10
xreality.meta_worker.retry_attempts = 3
xreality.index_update_lag_warn_seconds = 60
```

**Service registration:** `services/meta-worker/` — Go service skeleton, follows existing service patterns (auth middleware, Prometheus metrics, health check).

### 12E.4 Layer 3 — Admin/analytics (deferred indefinitely)

**Not V1. Not V2 locked. Explicitly deferred until a specific feature demands.**

When that day comes (if ever):
- Evaluate data volume (do we need OLAP, or is Postgres batch enough?)
- Evaluate latency tolerance (realtime vs minutes vs hours)
- Evaluate query shape (point lookup vs aggregate vs search)

Candidate tools at that future decision: ClickHouse, Elasticsearch, BigQuery, Snowflake, or plain Postgres replica. None locked now.

**DF12 (Cross-Reality Analytics & Search) — NOT registered.** If demand emerges, new DF to be created at that time with specific scope.

### 12E.5 Ad-hoc admin queries (tool, not feature)

For rare admin operations (incident response, legal discovery, deep debugging), app-level fan-out is acceptable:

```go
func adminFindRealities(criteria Criteria) []Reality {
    // Rate-limited, timeout-bounded, audit-logged
    shards := listActiveShards()
    results := []Reality{}
    for _, shard := range shards {
        for _, realityID := range shardRealitiesIn(shard) {
            if criteria.CheapMetaFilter(realityID) {
                dbResult := queryReality(realityID, criteria)
                results = append(results, dbResult...)
            }
        }
    }
    return results
}
```

**Rules:**
- Rate limit: max 1 such query per minute per admin
- Timeout: 30 seconds total
- Audit log: every invocation
- Never in user-facing request path

**Config:**
```
admin.federated_query.rate_limit_per_min = 1
admin.federated_query.timeout_seconds = 30
```

### 12E.6 Anti-pattern — reject cross-instance live query as API design

Formal governance rule. When a feature seems to need "query across realities," the contributor MUST redesign as one of:

1. **Meta-level lookup** — promote the needed field to `reality_registry` or `player_character_index` (with justification)
2. **Event-driven propagation** — emit event from producer, local cache in consumers
3. **Import/export** — atomic hand-off between specific realities (like world travel DF6)
4. **Ad-hoc admin query** — rate-limited, slow, audit-logged

**Never acceptable:**
- `postgres_fdw` to federate reality DBs
- App-level fan-out in user-facing code path
- Ad-hoc direct connections to multiple reality DBs in realtime path

This is codified as governance policy: see [`docs/02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md`](../../02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md).

**Code review enforcement:**
- PR touching realtime code must not import multiple reality DB drivers
- Any new `multi_db_query` function must reference this policy in its doc string
- Deviations require explicit ADR

### 12E.7 Accepted trade-offs

| Layer | Cost |
|---|---|
| L1 meta lookups | Field proliferation risk — mitigated by "feature-justified" discipline |
| L2 event propagation | Meta-worker service to maintain (narrow but real) |
| L3 analytics defer | Future demand may require infrastructure addition then |
| Anti-pattern discipline | Code review must catch violations |

The biggest cost is L2 meta-worker — but narrow scope keeps it manageable.

### 12E.8 Implementation ordering

- **V1 launch**: L1 (existing registry + field additions as features land), L2 (meta-worker service with 3 topics), governance doc published
- **V1 + 60 days**: L2 canon propagation activates on first author canon edit
- **V2**: Add `trending_score` if reality discovery sort demands
- **V3+**: Re-evaluate L3 only if specific admin/business feature surfaces

