# ADR — Entity-merge canonical-alias mapping

> **Status:** Accepted (2026-04-25, session 51 cycle 48 / C17 🏗 DESIGN+BUILD bundle).
> **Decision:** Postgres `entity_alias_map` table consulted by the extraction resolver before SHA-hash; populated by `merge_entities` surgery + one-shot backfill; merge refuses (error) on alias-vs-live-entity collision.
> **Closes-on-BUILD:** D-K19d-γb-03.
> **BUILD cycle:** **same cycle** (C17 — DESIGN+BUILD bundle per user approval, vs C16's DESIGN-only split).
> **Related plan row:** [Track 2/3 Gap Closure §4 C17](./KNOWLEDGE_SERVICE_TRACK2_3_GAP_CLOSURE_PLAN.md#c17--entity-merge-canonical-alias-mapping-p5-xl-design-first).
> **KSA amendment:** §5.0 (Entity Resolution) gains a new "Alias-redirect-on-merge" subsection.

---

## 1. Context — what D-K19d-γb-03 represents

K19d Cycle γ-b shipped `merge_entities(source, target)` — the user-facing operation that says "Alice and Captain Brave are the same person." The Cypher surgery rewires every `RELATES_TO` + `EVIDENCED_BY` edge from source to target, unions aliases/source_types, then `DETACH DELETE`s source.

But entity creation in extraction is **deterministic by name hash**:

```python
# canonical.py
def entity_canonical_id(user_id, project_id, name, kind, canonical_version=1) -> str:
    canonical = canonicalize_entity_name(name)
    key = f"v{canonical_version}:{user_id}:{project_id or 'global'}:{kind}:{canonical}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]
```

So once "Alice" was merged into "Captain Brave", the source node was deleted but its **canonical_id slot is now free again**. Next time the extractor processes a chapter mentioning "Alice", it computes the same SHA hash, finds no node at that id, and the `MERGE (e:Entity {id: $id}) ON CREATE` branch fires — a brand-new entity "Alice" appears in the graph, disconnected from Captain Brave. The user's merge intent didn't stick from the extractor's perspective.

**Concrete failure trace** (reproduces on hobby data):

1. User reads chapter 5, sees Alice; extraction creates `Entity{id: a3f2..., name: "Alice"}`.
2. User reads chapter 12, learns Alice is actually Captain Brave; clicks Merge.
3. `merge_entities` rewires Alice's edges to Captain Brave; aliases on Captain Brave become `["Captain Brave", "Alice"]`; Alice node is `DETACH DELETE`d.
4. User triggers re-extraction on chapter 5 (or processes chapter 30 which also mentions Alice).
5. Extractor sees "Alice" → `merge_entity(name="Alice", kind="person")` → SHA hash → `a3f2...` → `MERGE` finds no node → **`ON CREATE` fires → new Alice entity exists alongside Captain Brave**.

Captain Brave's aliases array is **not consulted by the canonical-id derivation**. Aliases are display denormalization, not a resolution index.

---

## 2. Existing surface (audited 2026-04-25)

### 2.1 canonicalize_entity_name + entity_canonical_id

[`services/knowledge-service/app/db/neo4j_repos/canonical.py`](../../services/knowledge-service/app/db/neo4j_repos/canonical.py) — pure functions, no I/O. Honorifics tuple (longest-first), lowercase, strip punctuation, collapse whitespace. Hash key shape `v{ver}:{user_id}:{project_id||'global'}:{kind}:{canonical}` truncated to 32 hex chars.

### 2.2 merge_entity (extraction-side upsert)

[`entities.py:181-220`](../../services/knowledge-service/app/db/neo4j_repos/entities.py#L181-L220). `MERGE (e:Entity {id: $id}) ON CREATE/ON MATCH`. The `$id` is computed by the caller from `entity_canonical_id`. **One direct caller**: `resolve_or_merge_entity` in [`app/extraction/entity_resolver.py:125+`](../../services/knowledge-service/app/extraction/entity_resolver.py#L125).

### 2.3 resolve_or_merge_entity

[`entity_resolver.py:125-175`](../../services/knowledge-service/app/extraction/entity_resolver.py#L125-L175) — extraction's "create-or-find" entry point. Currently:

1. Try glossary-linked lookup via `glossary_entity_id`.
2. If miss → call `merge_entity(...)` which delegates to the SHA-hash canonical_id.

**Two callers**: [`pattern_writer.py:214`](../../services/knowledge-service/app/extraction/pattern_writer.py#L214) (K15 pattern extractor) + [`pass2_writer.py:150`](../../services/knowledge-service/app/extraction/pass2_writer.py#L150) (K17 LLM Pass-2 refinement).

### 2.4 merge_entities (surgery)

[`entities.py:1819+`](../../services/knowledge-service/app/db/neo4j_repos/entities.py#L1819). Multi-step Cypher: collect source's edges → batch-rewire to target → glossary anchor pre-clear → `DETACH DELETE` source. Returns a target Entity model. Source's aliases become `target.aliases + source.aliases` via the existing union logic. **One direct caller**: [`routers/public/entities.py:459`](../../services/knowledge-service/app/routers/public/entities.py#L459) (the user-facing `POST /merge-into/{other_id}` endpoint).

### 2.5 What the audit confirms

- `merge_entity` itself doesn't need a Postgres pool — keep it Neo4j-only.
- Alias-redirect logic belongs in `resolve_or_merge_entity` (the layer that decides "find vs create").
- Alias-map writes belong in the merge router endpoint (single call site, has both pools available via DI).
- Plumbing scope: 2 writers thread a pool through to the resolver = 2 small touch-up edits.

---

## 3. Decision — Postgres `entity_alias_map` with mirror-scope key + error-on-conflict + one-shot backfill

### 3.1 Storage: Postgres

`entity_alias_map` table in the knowledge-service Postgres DB. Keyed by the same scope shape as `entity_canonical_id` so the lookup is O(1) on a covering index and the resolver doesn't have to translate scope semantics.

### 3.2 Scope: mirror entity_canonical_id

Lookup key: `(user_id, project_scope, kind, canonical_alias)` where `project_scope = project_id::text` for project-scoped extractions or the literal string `'global'` for global-scope. **Same shape as the SHA hash key minus the version prefix.** A "Phoenix" merge in Project A doesn't redirect "Phoenix" extractions in Project B; "Phoenix the person" merge doesn't redirect "Phoenix the place".

Project_scope is `TEXT` not `UUID NOT NULL` so `'global'` fits without a sentinel-UUID hack.

### 3.3 Conflict policy: error-on-merge

Before `merge_entities` surgery runs, the router pre-checks: for each alias on source (including source's own canonical_name), does any **other live** entity (not source, not target) exist with `canonical_name = canonicalize(alias)` AND same scope AND same kind? If yes → return HTTP 409 with `error_code: "alias_collision"` and the colliding entity's id+name in the body. The user must resolve the third entity first (merge it into target separately, or rename it) before retrying.

This is the "user is asserting these are the same; if a third entity already claims that identity the merge is ambiguous and should fail loud" semantic.

### 3.4 Backfill: one-shot at C17-BUILD ship

A migration helper walks every existing `:Entity` node (per user, per scope, per kind), reads its `aliases[]` array, and writes `entity_alias_map` rows for each alias EXCEPT the entity's own canonical_name (that's already implicit via the entity's id). Idempotent — re-runs are no-ops via `ON CONFLICT DO NOTHING`. Runs in seconds at hobby scale (≤10k entities/user × ≤8 aliases avg = ≤80k rows). Triggered manually post-deploy via a CLI helper, not via lifespan task — backfill is a one-time migration, not a recurring job.

### 3.5 Why this combination

| Decision | Why this | Why not alternatives |
|---|---|---|
| Postgres table | Matches K16.11 / C16 / C14b precedent — non-graph state lives in Postgres. Pool is already available in the resolver path via DI. | Neo4j relationship/property: pollutes graph with denormalized lookup data; Cypher reads add round-trip per extraction without index parity. Neo4j fulltext index on aliases: would catch the case but doesn't lock identity (different node id ≠ same entity). |
| Mirror-scope key | Avoids cross-project leak; respects multi-tenant isolation already encoded in the SHA hash. | Simpler `(user_id, canonical_alias)` key: violates project isolation; "Phoenix" in Project A could redirect "Phoenix" in unrelated Project B. |
| Error-on-conflict | Honest semantic — surface ambiguity to the user; cheap pre-check. | Lookup-wins: silently abandons the existing entity Y, surprising data loss. Existing-wins: makes the alias-map row a stale lie ("alice → X" but extraction goes to Y). |
| One-shot backfill | Closes the bug for existing zombies; ≤1 minute runtime; idempotent. | Lazy-only: leaves permanent orphan state for any pre-C17 merges; users would need to re-merge by hand. |

---

## 4. Rejected alternatives

### 4.1 Storage: Neo4j edge `(:Alias)-[:REDIRECTS_TO]->(:Entity)`

**Pro**: keeps all entity-resolution state in the graph; one store to query.

**Con**: extraction's hot path already does Postgres lookups (glossary_entity_id, project ownership) before Neo4j contact. Adding a Neo4j round-trip BEFORE the SHA-hash decision adds latency on every extraction. Postgres is the correct boundary for "lookup → decide which Cypher MERGE id to use."

### 4.2 Storage: Aliases-array search via Cypher `WHERE $alias IN e.aliases`

**Pro**: zero new schema.

**Con**: `aliases` array isn't indexed; lookup is O(n) full scan over user's entities. At 10k entities/user this is 10k×O(array-scan) per extraction. Adding a fulltext index on aliases doesn't fix the determinism problem (multiple matches possible) and still scans more than a Postgres b-tree.

### 4.3 Conflict policy: lookup-wins (silently merge the third entity into target)

**Pro**: best UX — user clicks merge once, extraction always lands at target.

**Con**: silent destructive behavior. "Alice + Captain Brave" merge silently absorbs an unrelated entity Y named "Alice" if Y exists. Real data loss; no audit trail. Violates the "merge surgery is an explicit user act" principle.

### 4.4 Conflict policy: existing-entity-wins (alias-map row goes stale)

**Pro**: no destructive merge; existing entity untouched.

**Con**: alias-map row is a lie — says "alice → X" but extraction lands at Y. Future merge calls would compound the inconsistency. The whole point of the alias-map is determinism; allowing stale rows defeats it.

### 4.5 Backfill: lazy-only

**Pro**: zero migration risk; smaller cycle scope.

**Con**: every pre-C17 merge stays broken — those zombie entities will keep reappearing for the lifetime of the project. Migration is cheap (one-pass walk of `:Entity` nodes); skipping it leaves permanent orphan state.

---

## 5. Implementation sketch (BUILD-ready)

### 5.1 DDL — `entity_alias_map`

Append to `services/knowledge-service/app/db/migrate.py` (tail-of-DDL convention):

```sql
CREATE TABLE IF NOT EXISTS entity_alias_map (
  user_id           UUID NOT NULL,
  project_scope     TEXT NOT NULL,                  -- project_id::text OR literal 'global'
  kind              TEXT NOT NULL,
  canonical_alias   TEXT NOT NULL,                  -- canonicalize_entity_name() output
  target_entity_id  TEXT NOT NULL,                  -- :Entity.id (32-hex)
  source_entity_id  TEXT,                           -- nullable for backfill rows
  reason            TEXT NOT NULL,                  -- 'merge' | 'backfill'
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, project_scope, kind, canonical_alias),
  CHECK (reason IN ('merge', 'backfill'))
);

CREATE INDEX IF NOT EXISTS idx_entity_alias_map_target
  ON entity_alias_map(target_entity_id);
```

- Composite PK = covering index for the lookup hot path. No separate user-only index needed.
- `target_entity_id` index supports reverse queries (e.g., "what aliases redirect to this entity?" — useful for FE display + backfill audit).
- No FK to `:Entity.id` because the entity lives in Neo4j, not Postgres (cross-store FK forbidden by convention — same as K16 user_id non-FK).
- `reason` discriminator distinguishes merge-driven rows (authoritative) from backfill rows (best-effort reconstruction). FE/audit can show different UI for each.
- `source_entity_id` nullable because backfill can't reconstruct the deleted source's id; merge writes it for forensics.

### 5.2 `EntityAliasMapRepo`

NEW `services/knowledge-service/app/db/repositories/entity_alias_map.py`:

```python
class EntityAliasMapRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def lookup(
        self,
        user_id: UUID,
        project_scope: str,         # 'global' or project_id::str
        kind: str,
        canonical_alias: str,
    ) -> str | None:
        """Return target_entity_id if alias is registered, else None."""

    async def record_merge(
        self,
        user_id: UUID,
        project_scope: str,
        kind: str,
        canonical_alias: str,
        target_entity_id: str,
        source_entity_id: str | None,
    ) -> None:
        """Idempotent INSERT ... ON CONFLICT DO NOTHING.
        ON CONFLICT explicitly DO NOTHING (not UPDATE) — once an alias
        is mapped, second-merge attempts must not silently overwrite."""

    async def list_for_entity(
        self,
        target_entity_id: str,
    ) -> list[dict]:
        """Reverse lookup — every alias redirecting to this entity.
        For FE display + backfill audit."""

    async def bulk_backfill(
        self,
        rows: list[tuple[UUID, str, str, str, str]],
    ) -> int:
        """Bulk INSERT with reason='backfill', ON CONFLICT DO NOTHING.
        Returns count of inserted rows."""

    async def repoint_target(
        self,
        user_id: UUID,
        old_target_entity_id: str,
        new_target_entity_id: str,
    ) -> int:
        """REVIEW-DESIGN: re-point every redirect that pointed at
        ``old_target`` onto ``new_target``. Called by ``merge_entities``
        after surgery so multi-step merge chains (A→B today, B→C
        tomorrow) keep A redirecting to C — not B which was deleted.
        Returns rowcount for logging."""
```

### 5.3 `resolve_or_merge_entity` — lookup before hash

Extend [`entity_resolver.py:resolve_or_merge_entity`](../../services/knowledge-service/app/extraction/entity_resolver.py#L125):

```python
async def resolve_or_merge_entity(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    name: str,
    kind: str,
    source_type: str,
    confidence: float = 0.0,
    canonical_version: int = 1,
    glossary_entity_id: str | None = None,
    alias_map_repo: EntityAliasMapRepo | None = None,  # NEW
) -> Entity:
    # ── existing glossary-linked lookup ─────────────────
    if glossary_entity_id:
        existing = await find_by_glossary_id(...)
        if existing:
            return existing

    # ── NEW: alias-map redirect lookup ──────────────────
    # Gated on alias_map_repo is not None for back-compat
    # with the ~6 test sites that don't yet wire it
    # (see ADR §5.6 wire-through).
    if alias_map_repo is not None:
        canonical_alias = canonicalize_entity_name(name)
        project_scope = project_id or "global"
        target_id = await alias_map_repo.lookup(
            UUID(user_id), project_scope, kind, canonical_alias,
        )
        if target_id is not None:
            # Use the target's id directly — skip the SHA hash.
            # merge_entity's MERGE on $id will hit the existing
            # target node + ON MATCH branch updates aliases/sources.
            existing_target = await get_entity_by_id(session, user_id, target_id)
            if existing_target is not None:
                # Append source_type + name-as-alias via existing
                # ON MATCH semantics — re-use merge_entity to keep
                # one upsert path.
                return await merge_entity_at_id(
                    session, user_id=user_id, id=target_id,
                    project_id=project_id, name=name, kind=kind,
                    source_type=source_type, confidence=confidence,
                )
            # Target id in alias-map but not in graph = stale row.
            # Log + fall through to SHA hash so extraction proceeds.
            logger.warning(
                "C17 alias_map points to deleted entity user=%s "
                "alias=%s target=%s — falling through",
                user_id, canonical_alias, target_id,
            )

    # ── existing fall-through: SHA-hash MERGE ───────────
    return await merge_entity(
        session,
        user_id=user_id,
        project_id=project_id,
        name=name,
        kind=kind,
        source_type=source_type,
        confidence=confidence,
        canonical_version=canonical_version,
    )
```

`merge_entity_at_id` is a new sibling helper that's identical to `merge_entity` but takes `id` directly (skips the SHA derivation). Implementation: ~10 LOC + reuses `_MERGE_ENTITY_CYPHER` Cypher.

### 5.4 `merge_entities` — collision pre-check + alias-map writes (router-level)

The Cypher in `entities.py:merge_entities` returns the source's `aliases` array as part of the response (small Cypher RETURN extension). The public router endpoint then:

1. **Collision pre-check** (before calling `merge_entities`): for each alias in source.aliases, run a single Cypher `MATCH (e:Entity) WHERE e.user_id = $u AND e.project_id = $p AND e.kind = $k AND e.canonical_name = $canonical AND e.id <> $source_id AND e.id <> $target_id AND e.archived_at IS NULL RETURN e.id, e.name`. Any hit → return 409 `alias_collision` with `{colliding_entity_id, colliding_entity_name}`.

2. **Run `merge_entities`** as today.

3. **Post-merge alias-map writes**: for each alias in `source.aliases` UNION `[source.canonical_name]`, write `record_merge(user_id, project_scope, kind, canonical_alias=canonicalize(alias), target_entity_id=target.id, source_entity_id=source.id)`. ON CONFLICT DO NOTHING handles "user already merged something else with the same alias into the same target" — idempotent.

4. **Re-point existing redirects from source to target** (REVIEW-DESIGN catch — multi-row merge chains). If user previously merged X→source, the alias-map already has rows with `target_entity_id = source.id`. After merging source into target, those rows would point to the now-deleted source. Run a single UPDATE atomically:

   ```sql
   UPDATE entity_alias_map
      SET target_entity_id = $target_id
    WHERE target_entity_id = $source_id
      AND user_id = $user_id;
   ```

   This re-points every prior redirect onto the new target in one statement. **Why not recursive lookup at read time**: chasing a chain on every extraction read multiplies Postgres round-trips and risks infinite loops if a cycle ever appears (data-corruption defense). One UPDATE on the rare write path is cheaper and self-healing.

5. Response JSON gains an `aliases_redirected` count for FE display.

### 5.5 Backfill helper

NEW CLI script `services/knowledge-service/scripts/backfill_entity_alias_map.py`:

```python
async def run_backfill(pool: asyncpg.Pool, neo4j_session_factory):
    """One-shot. Walks every :Entity node, writes alias-map rows
    for each alias != canonical_name. Idempotent ON CONFLICT.
    Logs (count_inserted, count_skipped, count_canonical_only)."""
    async with neo4j_session_factory() as session:
        result = await session.run(
            "MATCH (e:Entity) WHERE e.archived_at IS NULL "
            "RETURN e.user_id AS user_id, e.project_id AS project_id, "
            "       e.kind AS kind, e.canonical_name AS canonical_name, "
            "       e.aliases AS aliases, e.id AS target_entity_id"
        )
        rows = []
        async for record in result:
            project_scope = record["project_id"] or "global"
            for alias in record["aliases"]:
                ca = canonicalize_entity_name(alias)
                if ca == record["canonical_name"]:
                    continue  # entity's own name — implicit via id
                rows.append((
                    UUID(record["user_id"]), project_scope,
                    record["kind"], ca, record["target_entity_id"],
                ))
    repo = EntityAliasMapRepo(pool)
    inserted = await repo.bulk_backfill(rows)
    print(f"Inserted {inserted} alias-map rows from {len(rows)} candidates")
```

Run-once via `python -m scripts.backfill_entity_alias_map`. Out-of-band — NOT a lifespan task. README in scripts/ documents the post-deploy invocation.

### 5.6 Wire-through

| File | Change |
|---|---|
| `app/db/migrate.py` | Append §5.1 DDL |
| `app/db/repositories/entity_alias_map.py` | NEW (§5.2) |
| `app/extraction/entity_resolver.py` | Add `alias_map_repo` kwarg; insert lookup-before-hash branch (§5.3) |
| `app/extraction/pattern_writer.py` | Pass `alias_map_repo` through to resolver |
| `app/extraction/pass2_writer.py` | Pass `alias_map_repo` through to resolver |
| `app/db/neo4j_repos/entities.py` | `merge_entities` Cypher returns source.aliases; new collision-precheck Cypher constant |
| `app/routers/public/entities.py` | Collision pre-check; post-merge alias-map writes; new 409 error_code |
| `app/deps.py` | NEW `get_entity_alias_map_repo` factory |
| `scripts/backfill_entity_alias_map.py` | NEW (§5.5) |
| `tests/unit/test_entity_alias_map_repo.py` | NEW — 9 tests (lookup miss, lookup hit, record_merge happy/idempotent, list_for_entity, bulk_backfill, scope isolation, kind isolation, **repoint_target chain re-point — REVIEW-DESIGN catch**) |
| `tests/unit/test_migrate_ddl.py` | NEW DDL regression block (table_present + schema_shape + no-cross-db-FK + CHECK constraint) |
| `tests/unit/test_entity_resolver.py` | NEW: alias-map redirect path + stale-row fall-through + None-default back-compat |
| `tests/unit/test_pass2_writer.py` | NEW: alias_map_repo plumbing assertion (sentinel forwarded to resolver) |
| `tests/unit/test_entities_browse_api.py` | NEW: collision-409 + post-merge alias-map writes assertion |
| `tests/unit/test_alias_backfill.py` | NEW: backfill happy + idempotent re-run + canonical-name-skip |

Audit-all-callsites lesson applied: review-impl will verify every site that calls `resolve_or_merge_entity` threads the new dep, every `merge_entities` caller (only the router, but verify) writes alias-map rows. **Audit reaches**: `pattern_writer.py`, `pass2_writer.py`, `routers/public/entities.py`, plus all 8 test files that mock these — each must be updated.

### 5.7 Test plan summary

~25 new tests covering: repo CRUD + chain re-point (9) + DDL regression (4-5) + resolver redirect path + stale-row fall-through (3) + writer plumbing (2) + router collision-409 + post-merge writes + chain re-point (4) + backfill (3-4). Target: all 1523 existing tests still green; +25 ≈ 1548 total.

---

## 6. Open questions for BUILD cycle (CLARIFY pre-checks)

These are points the implementer should re-confirm at BUILD-CLARIFY (or in this same cycle since C17 is bundled). Leaving them explicit so a future reader knows they were considered, not forgotten.

1. **Honorific re-canonicalization on merge**: when source has alias `"Master Kai"`, do we record `canonical_alias = "kai"` (post-honorific-strip) or `"master kai"` (pre-strip)? **Recommend**: post-strip (matches `entity_canonical_id`'s shape — same input that produced source's hash). The lookup on the extraction side ALSO calls `canonicalize_entity_name`, so both ends agree on the normalization.

2. **Cross-project merges**: `merge_entities` requires source and target to be in the same project (router validates via `same_user`). The alias-map's `project_scope` follows. No question to defer.

3. **Glossary-anchored entities**: if target has `glossary_entity_id` set, future extractions of source's aliases should still hit target (which keeps its glossary anchor). Existing `glossary_entity_id` lookup runs FIRST in `resolve_or_merge_entity` so glossary anchoring takes priority over alias-map; alias-map only fires when glossary lookup misses. Already correct in §5.3 ordering.

4. **Backfill re-run safety**: the helper uses `ON CONFLICT DO NOTHING`, so re-running mid-failure is safe. If a backfill is half-done and then a user merges new entities post-backfill but pre-finish, the merge writes its rows independently (different reason='merge') — no conflict, no overwrite. Verified by the `record_merge` ON CONFLICT semantic.

5. **Stale-row fall-through** (REVIEW-DESIGN catch): if `entity_alias_map` says "alice → X" but X has been deleted from Neo4j (e.g., manual archive cascade, future ops cleanup), the resolver should log a warning and fall through to the SHA-hash MERGE path so extraction still produces an entity. The fall-through resurrects "Alice" as a fresh node — same behavior as today's broken code, but at least it's consistent. **Recommend logging at WARNING + emitting a metric** so ops can find stale rows and clean them up. Implementation: `merge_entity_at_id` returns None when `MERGE` finds no matching node post-WHERE filter (no `ON CREATE` because we passed an explicit id without scope/name); resolver checks the None and falls through. **Note**: archived (not deleted) target is OK — the redirect fires anyway, ON MATCH branch updates timestamps without resurrecting.

6. **Performance — alias-map lookup per extracted entity**: at 100 entities/chapter × 1000 chapters = 100k Postgres seeks per book. Each is a single PK index lookup (sub-millisecond) so total ≈ 5-10s of overhead per book at hobby scale. Acceptable today. **Mitigation if profiling shows pain**: batch lookups per chapter into one `WHERE (canonical_alias, kind) IN (...)` query. Defer until pain is observed.

7. **Race window — collision pre-check vs surgery**: another extraction running concurrently could create a colliding entity between the precheck and the `merge_entities` Cypher write. At hobby scale (single user, low-rate extraction) this is theoretical. **Mitigation if needed**: Postgres advisory lock per `(user_id, target_entity_id)` for the merge transaction. Defer.

---

## 7. Closing checklist for C17 (DESIGN+BUILD bundle)

D-K19d-γb-03 is fully cleared **only** when ALL of the following ship in this cycle:

- [ ] DDL appended to `migrate.py` per §5.1; CREATE TABLE + index + CHECK
- [ ] `EntityAliasMapRepo` per §5.2 with 8 unit tests
- [ ] `merge_entity_at_id` sibling helper added to `entities.py`
- [ ] `resolve_or_merge_entity` lookup-before-hash branch per §5.3
- [ ] `pattern_writer.py` + `pass2_writer.py` thread `alias_map_repo` through (with regression-lock tests asserting the kwarg is forwarded — audit-all-callsites lesson)
- [ ] `merge_entities` Cypher returns source.aliases
- [ ] Router collision pre-check (409 `alias_collision`) + post-merge alias-map writes per §5.4 (steps 1+3)
- [ ] Router re-points existing redirects via `repoint_target` after surgery (§5.4 step 4 — REVIEW-DESIGN catch)
- [ ] `EntityAliasMapRepo.repoint_target` shipped + unit-tested for chain semantics (X→A then A→B leaves X→B)
- [ ] `get_entity_alias_map_repo` dep factory in `app/deps.py`; wired into router endpoint with regression-lock test
- [ ] Backfill CLI script per §5.5; unit tests (happy + idempotent + canonical-skip)
- [ ] DDL regression tests in `test_migrate_ddl.py`
- [ ] FE / API contract: response of `merge-into` gains `aliases_redirected: int` field; existing FE merge dialog adds a one-line success-toast tail "+N aliases now redirect" (low-touch FE delta — out of pure-BE scope OR included as one i18n key + one prop pass-through; defer to BUILD-CLARIFY)
- [ ] `/review-impl` 0 unresolved HIGH/MED on the BE surface
- [ ] KSA §5.0 amended with the alias-redirect-on-merge subsection
- [ ] Plan row C17 flipped `[ ]` → `[x]` with cycle detail
- [ ] SESSION_PATCH cycle 48 entry; D-K19d-γb-03 marked cleared

When all rows above are checked, this ADR's status changes to "Accepted + shipped (commit hash)".
