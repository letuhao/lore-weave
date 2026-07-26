# Spec/Plan: project-scope the KG↔glossary FK (`D-KG-GLOSSARY-FK-GLOBAL-UNIQUE`)

**Date:** 2026-07-10 · **Branch:** `feat/context-budget-law` · **Size:** L (schema constraint + a live
event path + 3 lookup sites) · **Origin:** found by the WS-4B live smoke (Track B), 2026-07-09.

---

## 1. The bug

Neo4j constraint `entity_glossary_id_unique` (`app/db/neo4j_schema.cypher`) makes
`Entity.glossary_entity_id` **globally unique — across every user and every project**:

```cypher
CREATE CONSTRAINT entity_glossary_id_unique IF NOT EXISTS
FOR (e:Entity) REQUIRE e.glossary_entity_id IS UNIQUE;
```

So **exactly one `:Entity` node in the whole database may point at a given glossary entity.**

Reproduced live: projecting a 100-entity book into a *new* knowledge project anchored only **20**
entities — the other 80 raised `Neo.ClientError.Schema.ConstraintValidationFailed` because that book's
*existing* project already owned their FKs. It hits `kg_project_entities_to_nodes` (WS-4B) **and the
shipped extraction Pass-0 anchor pre-load** (`load_glossary_anchors`) equally.

## 2. Root cause — two anchor-writers with contradictory identity models

| Writer | MERGE key | Implied identity |
|---|---|---|
| `upsert_glossary_anchor` (Pass-0, WS-4B) | `Entity.id` = `hash(user_id, project_id, name, kind)` | **one node per (user, project, entity)** |
| `sync_glossary_entity_to_neo4j` | `(user_id, glossary_entity_id)` | **one node per (user, entity)**, shared across the user's projects |

`glossary_sync.py`'s own header admits the consequence of its model: *"a user with two projects sharing a
book sees `project_id` reflect whichever project last synced the entity"* — i.e. `project_id` becomes
meaningless on a shared node (latest-sync-wins). The global constraint exists to protect the single-row
assumption in `get_entity_by_glossary_id` (`result.single()`), and it silently enforces the *shared* model
while the primary writer produces the *per-project* model.

**Decision: adopt the per-project model (`Entity.id`'s model).** Rationale:
- `Entity.id` — the MERGE key for extraction *and* anchors — already encodes `project_id`.
- Essentially every read filters by `project_id` (`salience.py`, `coref_detect.py`, graph views, relations).
- "latest-sync wins `project_id`" is an acknowledged hack that corrupts the field it overwrites.
- The shared model makes a second project over a book structurally unable to build a graph.

## 3. Blast radius (audited)

| Site | Keyed on | After the change |
|---|---|---|
| `neo4j_schema.cypher` | global unique on FK | composite `(user_id, project_id, glossary_entity_id)` |
| `entities.get_entity_by_glossary_id` | `user_id` only | **+ required `project_id`** |
| `entities.get_neighborhood_by_glossary_id` | `user_id` only | **+ optional `project_id`** (read-only; see §5) |
| `glossary_sync.sync_glossary_entity_to_neo4j` | MERGE `(user_id, gid)` | MERGE `(user_id, project_id, gid)` |
| `events.handlers` `glossary.entity_merged` | one project (`LIMIT 1`) | **iterate every project of the book** |
| `fact_for_check.py` | `user_id` + optional `project_id` | unchanged (already conditional) |
| `salience.py`, `coref_detect.py` | already `project_id`-scoped | unchanged |
| `link_to_glossary` / `unlink_from_glossary` | matched by `Entity.id` | unchanged (id encodes project) |

## 4. Data safety

- Existing data satisfies the **stricter** global constraint, so the composite constraint is guaranteed to
  create cleanly. **No backfill / data migration.**
- Verified on the dev graph: `5023` anchored nodes, each in exactly one project; `0` books with >1
  knowledge project; `0` derivative projects. So no flip-flopped `project_id` rows exist today.
- Neo4j composite **uniqueness** constraints are Community-supported (only NODE KEY is Enterprise) —
  verified live on `Neo4j Kernel 2026.03.1, community`.
- Composite uniqueness **exempts rows where any keyed property is NULL**, so `discovered` entities
  (`glossary_entity_id IS NULL`) are unaffected, exactly as before.

## 5. Decisions / trade-offs

- **`get_neighborhood_by_glossary_id` takes `project_id` as OPTIONAL.** Its only caller is glossary-service's
  Go `knowledge_client.go` → `POST /internal/knowledge/wiki-neighborhood`, which knows a *book*, not a
  project. Requiring it would be a cross-service contract change for a read-only wiki panel. When omitted we
  match the user's nodes, order deterministically by `project_id`, take the first, and **log a warning if
  more than one matched** — behaviour is identical today (one node per FK) and becomes explicit later.
- **`MERGE` cannot take a NULL property** (`Cannot merge node using null property value`). `sync_glossary_entity_to_neo4j`
  accepts `project_id: str | None`, so it keeps a **legacy no-project MERGE variant** on `(user_id, gid)`
  for `project_id=None` callers, and logs that it is running unscoped.
- **`kg_project_entities_to_nodes` keeps its `conflicted` counter** (added as the honesty mitigation). It
  should now be 0 in practice; it stays as a defensive, self-explaining guard rather than a silent skip.

## 6. Plan

1. `neo4j_schema.cypher`: `DROP CONSTRAINT entity_glossary_id_unique IF EXISTS;` then create the composite
   `entity_glossary_fk_unique`. (The runner executes file-ordered, idempotent statements at startup.)
2. `entities.py`: project-scope `get_entity_by_glossary_id` (required) and `get_neighborhood_by_glossary_id`
   (optional + multi-match warning).
3. `glossary_sync.py`: project-scoped MERGE key; drop the latest-sync-wins `project_id` overwrite (it is now
   part of the key); keep a legacy unscoped variant for `project_id=None`.
4. `events/handlers.py`: `glossary.entity_merged` loops over **all** `knowledge_projects` for the book and
   consolidates per project. This also fixes the pre-existing `LIMIT 1` project drift the code comments flag.
5. Tests: unit coverage for each scoping change + the per-project merge loop.
6. **Live verification** (the bug was only visible live): two projects anchor the same book's entities into
   distinct nodes; re-run the WS-4B smoke on the previously-conflicting 100-entity book and expect
   `nodes_created=100, nodes_conflicted=0`.

## 7. Acceptance — **ALL MET (2026-07-10)**

- [x] Two distinct knowledge projects can each anchor the same glossary entity, as two nodes.
      *(`test_fk_unique_is_per_project_not_global`, run against live Neo4j.)*
- [x] A single project's projection is still idempotent (re-run ⇒ `created=0, existing=N`).
- [x] `glossary.entity_merged` consolidates in every project of the book, not just the `LIMIT 1` one.
      *(`test_consolidates_in_every_project_of_the_book` + `test_absent_nodes_in_one_project_does_not_block_the_other`.)*
- [x] `get_entity_by_glossary_id` cannot return another project's node (`project_id` now required).
- [x] knowledge-service unit suite **3753 passed**; Neo4j integration `test_entities_repo_k11_5b.py` +
      `test_neo4j_schema.py` **34 passed** against the live graph; `ai-provider-gate` OK.

### Live verification (the bug was only ever visible live)

- The composite constraint **created cleanly against the real dev graph** (5023 anchored nodes) after
  dropping the global one — confirming §4's "no backfill" claim.
- Re-ran the WS-4B projection on the **exact book that previously conflicted** (100 entities, 80 already
  anchored by that book's other project):

  | | before | after |
  |---|---|---|
  | `nodes_created` | 20 | **100** |
  | `nodes_conflicted` | 80 | **0** |

  Re-run was idempotent (`created=0, existing=100`), the other project's nodes were untouched, and the
  test tenant's 100 nodes were cleaned up.

### Notes for a future reader

- Two pre-existing, unrelated integration failures surfaced while running the suite and were **not** caused
  by this change: `test_entities_browse_repo.py` (its `update_entity_fields` call omits a now-required
  `expected_version` kwarg — API drift from another branch) and `test_passages_repo.py` (leftover `:Passage`
  nodes polluting the shared dev graph).
- `kg_project_entities_to_nodes` keeps its `nodes_conflicted` counter. It should now be 0; it stays as a
  self-explaining guard so a future constraint regression can never present a partial projection as success.
