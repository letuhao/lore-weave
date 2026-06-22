# Spec — KG-branch deferred clearance (8 rows → fan-out + batched, live-E2E at the end)

**Branch:** `feat/knowledge-graph-ontology`
**Date:** 2026-06-21
**Author:** Architect/Lead (default v2.2)
**Status:** DESIGN — awaiting go for fan-out

## 0. Scope

Clear the remaining **design/feature** deferred rows on this branch. These are the
items the prior sweeps left because they need real code (not just a verify-and-tick),
but are NOT blocked on infra (those are the separate live-smoke set) and are NOT owned
by another branch.

| ID | Sev | One-line | Lane |
|---|---|---|---|
| `D-KG-L7-CARDINALITY` | dormant | `single_active` edge auto-close in `create_relation` | **A** |
| `D-KG-LB-CACHE-SCHEMA-KEY` | low | extraction cache key omits schema → cross-schema collision | **B** |
| `D-KG-LD-GRANTEE-TIMELINE` | med | grantee cross-owner entity timeline read (grant-gated) | **C** |
| `D-KG-L7B-EXTRACT-ITEM` | med | `/extract-item` lacks the schema split (NOT dormant — composition calls it) | **D** |
| `D-KG-LH-NEO4J-REAPPLY` | med | real `ReapplyWriter` (triage resolve → Neo4j write) | **E** |
| `D-KG-LF-PROPOSE-EDGE-INBOX` | med | confirm descriptor + effect to place a `proposed_edge` into Neo4j | **E** |
| `D-KG-LH-LC-SCHEMA-WRITE` | med | triage schema-mutating resolve → `ontology_mutations` via confirm spine | **E** |
| `D-KG-LC-REVADOPT-LOSS` | med | preview "what you'll lose" on re-adopt + FE warning | **F** |

**Out of scope (NOT ours):** `D-KG-LG-REAL` — glossary-branch internal-read dependency.
**Out of scope (infra, separate effort):** all `*-LIVE-SMOKE` / `*-NEO4J-SMOKE` /
`*-BROWSER-SMOKE` / `*-ROUTE-LIVE-TEST` rows — these are consumed by §6 (the final E2E).

**Invariants in force (all lanes):** multi-tenant scope keys + grant-gated cross-tenant
(INV-T*); MCP-first (any new agent capability is an MCP tool, never raw HTTP); class-C
writes go through the KM6 confirm-token spine (LLM/MCP **mints**, never writes — INV-K1);
provider-gateway (no direct SDK; local backends only via provider-registry BYOK); no
hardcoded model names. **Do NOT touch `services/glossary-service`** (read-only reference).

---

## 1. Lane A — `D-KG-L7-CARDINALITY` (single_active auto-close)

**Problem.** Edge types carry `cardinality ∈ {single_active, multi_active}`
(`app/db/ontology_models.py:27,89`; PG CHECK `app/db/migrate.py:1035-1036`). When a new
edge of a `single_active` type is created between the same endpoints, the prior active
edge should auto-close (`valid_until = now()`). Today `create_relation` never consults
cardinality — the path is dormant only because every seeded edge is `multi_active`.

**Current state.**
- `create_relation` — `app/db/neo4j_repos/relations.py:232-300`; cypher
  `_CREATE_RELATION_CYPHER:176-229`. No cardinality input, no close-prior step.
- Closure primitive already exists — `invalidate_relation` sets
  `r.valid_until = coalesce($valid_until, datetime())` (`relations.py:1201-1248`); reads
  filter `valid_until IS NULL`.
- Writer call site — `app/extraction/pass2_writer.py:661` (schema in scope at `:324`).
- SDK projection — `loreweave_extraction.schema_projection.ExtractionSchema` (does NOT
  expose per-predicate cardinality yet).

**Fix.**
1. SDK: add `edge_cardinalities: dict[str, str]` (predicate→cardinality) to
   `ExtractionSchema` projection + populate it in `build_extraction_schema`. Default empty
   ⇒ legacy/`schema=None` behaves exactly as today (no auto-close). **Update BOTH the
   projection builder and any mirror; keep `schema=None` byte-identical** (lane-LB rule).
2. `create_relation`: add optional `cardinality: str | None = None`. When
   `cardinality == "single_active"`, prepend a guarded close of the prior active edge in
   the MERGE cypher:
   ```cypher
   OPTIONAL MATCH (s:Entity {id:$subject_id})-[rp:RELATES_TO]->(o:Entity {id:$object_id})
   WHERE rp.user_id=$user_id AND rp.predicate=$predicate AND rp.valid_until IS NULL
     AND $cardinality = 'single_active'
   SET rp.valid_until = datetime(), rp.updated_at = datetime()
   // … existing MERGE of the new edge …
   ```
   Same `$user_id` partition only (no cross-tenant). `multi_active`/NULL ⇒ no-op.
3. Writer: look up the predicate's cardinality from `schema.edge_cardinalities` at
   `pass2_writer.py:661` and pass it to `create_relation`.

**Tests (live PG+Neo4j integration is the proof; unit for the projection).**
- two `single_active` relations, same (subj,pred,obj) → first edge gets `valid_until`,
  second is the only `valid_until IS NULL`.
- `multi_active` → both stay open (regression).
- `schema=None` → no auto-close, prompt snapshot unchanged.

**Files:** `relations.py`, `pass2_writer.py`, `sdks/python/loreweave_extraction/schema_projection.py` (+builder), tests.

---

## 2. Lane B — `D-KG-LB-CACHE-SCHEMA-KEY`

**Problem.** `compute_task_id(normalized_text, op, extractor_version, model_ref)`
(`app/jobs/task_id.py:25-46`) omits the schema. Two extractions of the same text under
**different** schemas collide on a cache hit. Safe today (cache is per-book/project) but
a latent correctness bug once schema varies within a project.

**Current state.** Cache wrap `app/extraction/pass2_orchestrator.py:585` (`_p2_cache_wrap`)
builds `task_id` without schema; the resolved `schema` IS in scope at the call sites
(e.g. `:876-890`) but only passed into `extractor_kwargs`, not the cache key.

**Fix.**
1. `compute_task_id` — add `schema_key: str = ""` appended to the hashed payload.
   Empty default ⇒ **legacy hash byte-identical** (no cache invalidation for `schema=None`).
2. `_p2_cache_wrap` — accept `schema_key` and pass it through. Derive at the call site as
   `str(schema.schema_version)` joined with `schema.graph_id` (or `""` when `schema is None`).
   Use a stable canonical string (e.g. `f"{graph_id}:{schema_version}"`).

**Tests:** same text, two schema_versions → distinct task_ids; `schema=None` → identical
to the pre-change hash (snapshot). Pure unit.

**Files:** `task_id.py`, `pass2_orchestrator.py`, tests.

---

## 3. Lane C — `D-KG-LD-GRANTEE-TIMELINE`

**Problem.** The edge-timeline read
(`GET /v1/kg/entities/{entity_id}/edges/{edge_type}/timeline`,
`app/routers/public/graph_views.py:564-592`) binds `_TIMELINE_CYPHER` to the **caller's**
`$user_id` (`:586`; cypher `:270-279`), and the entity lookup is caller-scoped
(`_resolve_entity_project_grant:346-401`, `get_entity(... user_id=caller ...)` →
`entities.py:559`). A grantee with a valid VIEW grant on the owner's book gets a 404.

**Pattern to mirror.** Graph-read (`graph_views.py:513-561`) already does it right:
`owner = Depends(require_project_grant(VIEW))` (`grant_deps.py:108-122`, `_resolve_owner:91-105`)
then runs cypher with `user_id=str(owner)`.

**Fix.**
1. `entities.py`: add `get_entity_by_id_any_owner(session, canonical_id)` — `MATCH (e:Entity {id:$id})`
   with NO `user_id` filter (safe: `Entity.id` is globally unique, schema constraint).
   Returns the entity incl. its `user_id` (owner) + `project_id`.
2. `_resolve_entity_project_grant`: look the entity up via the any-owner helper, then
   apply the **same** gate as `_resolve_owner`: `caller==owner`→ok; else resolve the book
   grant (`gc.resolve_grant(book_id, caller)`), non-grantee→404, under-VIEW→403. Return the
   **owner** user_id.
3. Timeline handler: bind `_TIMELINE_CYPHER` to the resolved **owner**, not caller.

**Tenancy tests (the proof — this is a cross-tenant boundary, `/review-impl` mandatory):**
owner self-read ok; grantee(VIEW) of book A reads owner's timeline; grantee under VIEW→403;
non-grantee→404 (no existence leak); grantee of book A cannot read an entity in book B.

**Files:** `graph_views.py`, `neo4j_repos/entities.py`, tests. **`/review-impl` required.**

---

## 4. Lane D — `D-KG-L7B-EXTRACT-ITEM` (schema split for the live endpoint)

**Correction to the deferred note:** `/extract-item` is **NOT dormant**. worker-ai stopped
calling it (4b-γ), but **composition-service C27 delta flywheel actively calls it**
(`services/composition-service/app/routers/approve.py:178-186` →
`clients/knowledge_client.py:158-213`). So removal is wrong; the clear = give it the L7
schema split that `/persist-pass2` has.

**Current state.** `app/routers/internal_extraction.py:369-493` — `ExtractItemRequest`
has no schema field; calls `extract_pass2_chapter(...)` with `schema` defaulting to `None`
⇒ static prompts, no ontology customization, and no off-schema park.

**Fix (knowledge-service-local; composition-service unchanged).** The endpoint already
has `user_id`+`project_id`, so resolve the schema **internally** (don't make composition
pass it):
1. In `extract_item`, call the existing resolver to build the **advisory** `ExtractionSchema`
   projection for `(user_id, project_id)` (same path `/persist-pass2` / worker use), then
   thread it into the SDK extraction call (advisory: forces `allow_free_edges=True`).
2. Thread the **authoritative** schema + a `triage_repo` into `write_pass2_extraction`
   (closed-edge enforce + off-schema park), matching `/persist-pass2`.
3. Stamp `schema_version`/`graph_id` on writes (already done by `create_relation` once
   schema is passed). When no schema resolves → `general` fallback (today's behavior).

**Tests:** unit — `extract_item` resolves + passes schema to both SDK and writer (spy);
off-schema edge parks. Cross-service contract unchanged (composition still sends no
schema field). Live half folds into §6 (the C27 path is in the E2E set).

**Files:** `internal_extraction.py`, tests.

---

## 5. Lane E — triage cluster (3 rows, ONE lane — shared files)

These three share `triage_apply.py`, `kg_actions.py`, `confirm.py`, `triage.py` →
**one agent owns the lane** (fan-out at file granularity would conflict on the descriptor
enum + dispatch). Build order within the lane: **E1 → E2 → E3** (E2 reuses E1's writer).

**Shared substrate that already exists:**
- `app/ontology/triage_apply.py` — `ReapplyWriter` Protocol + `NotWiredReapplyWriter`
  (raises) default; `requires_reapply(action)` True for `{map, re_target, close_previous}`;
  `apply_resolved()` delegates to the injected writer.
- KM6 confirm spine — `app/ontology/confirm.py` (descriptor enum `_LIVE_DESCRIPTORS`,
  `mint_action_token`/`verify_action_token`), `app/routers/public/kg_actions.py`
  (`confirm_action`/`preview_action` dispatch on `claims.descriptor`),
  reference effect `app/ontology/schema_edit_effect.py`.
- Central write path — `create_relation` (`relations.py:232`). **D5 exists** (the
  investigation's "blocked on D5" is stale — the writer is there).

### E1 — `D-KG-LH-NEO4J-REAPPLY`
Implement a real `ReapplyWriter` over `create_relation` and inject it where
`apply_resolved()` is called (`triage.py` resolve route). For `map`/`re_target`/
`close_previous`: reconstruct the corrected edge from the resolved item payload and write
it (re-using Lane-A cardinality close for `close_previous`). Replace the
`NotWiredReapplyWriter` default at the call site. Owner-scoped (resolve-to-owner) +
fail-soft on a single item (never break the batch).
**Tests:** live PG+Neo4j — resolve a `map` item → corrected edge appears in Neo4j;
`close_previous` closes the prior; dismiss still writes nothing.

### E2 — `D-KG-LF-PROPOSE-EDGE-INBOX`
A `proposed_edge` triage item (parked by `kg_propose_edge`,
`graph_schema_tools.py:903-967`; payload carries src/dst/predicate/kinds/valid_from/to)
currently only offers `dismiss` (`triage.py SUGGESTED_ACTIONS["proposed_edge"]`). Add the
**apply** path as a class-C confirm descriptor (so the LLM/MCP can never write directly):
1. `confirm.py`: add `DESC_TRIAGE_PROPOSED_EDGE` to `_LIVE_DESCRIPTORS`.
2. New `app/ontology/triage_proposed_edge_effect.py` — `apply_*`/`preview_*` mirroring
   `schema_edit_effect.py`: re-fetch the triage item (drift→422 if already resolved),
   validate it's a pending `proposed_edge`, write the edge via E1's writer/`create_relation`,
   then mark the item resolved.
3. `kg_actions.py`: dispatch the new descriptor in `confirm_action` + `preview_action`.
4. `triage.py`: `SUGGESTED_ACTIONS["proposed_edge"] += ["place_edge"]` (the action that
   mints the confirm token). The MCP tool **mints**, the browser redeems at
   `/v1/kg/actions/confirm` (INV-K1/INV-T3).
**Tests:** preview renders the edge; confirm writes it to Neo4j + resolves the item;
replay→422; wrong-user→403; unit asserts the MCP surface still cannot write directly.

### E3 — `D-KG-LH-LC-SCHEMA-WRITE`
Schema-mutating triage actions (`SCHEMA_MUTATING_ACTIONS = {add_to_vocab, add_to_schema,
widen_target_kinds, set_multi_active}`, `triage.py`) currently record intent but never
mutate schema (`new_schema_version=None`). Route them through `ontology_mutations` via a
class-C confirm descriptor (Manage-gated, bumps `schema_version`):
1. Define the param mapping per action (e.g. `add_to_vocab`→`(schema_id, vocab_set_code,
   value_code, label)`; `set_multi_active`→`(edge_type_id)`).
2. `confirm.py`: add `DESC_TRIAGE_SCHEMA_WRITE`; new effect module calls the matching
   `OntologyMutationsRepo` method (re-validate `schema_version` drift→422) and returns the
   new version; `kg_actions.py` dispatch; `triage.py` writes the returned version onto the
   resolved item.
**Tests:** live PG — `add_to_vocab` confirm bumps schema_version + the value appears;
drift→422; under-Manage→403.

**Files:** `triage_apply.py`, `triage.py`, `confirm.py`, `kg_actions.py`,
`ontology_mutations.py` (E3 read/use only — additive methods if missing),
new `triage_proposed_edge_effect.py` + `triage_schema_write_effect.py`, tests.
**`/review-impl` required (class-C auth surface).**

---

## 6. Lane F — `D-KG-LC-REVADOPT-LOSS` (FS: BE preview + FE warning)

**Problem.** `adopt` (`ontology_mutations.py:253-348`) deprecates ALL prior active project
schemas (`:308-315`) before deep-copying the new one. Re-adopting silently hides a user's
customizations (soft-deleted, unreachable). No preview exists.

**Fix.**
1. BE: `compute_adopt_preview(current_schema_id, incoming_source_id)` in
   `ontology_mutations.py` — reuse `_tree_surface` (`:128-213`) + `_diff_trees`/`_diff_list`/
   `_diff_vocab` (`:877+`); return items present-in-current-only (`removed_upstream`) +
   `modified` = "what you'll lose".
2. BE route `POST /v1/kg/projects/{project_id}/adopt/preview` (`ontology.py`, beside
   `adopt_schema:318-373`; reuse `_active_project_schema_id:426-437`) → `{has_current,
   would_lose:[{node_type,code,change}]}`. Read-only, Manage/owner-scoped (no new write).
3. FE: `adoptPreview` in `api/ontology.ts`; extend `useOntologyAdopt` with preview state +
   auto-fetch on template select; `AdoptPicker.tsx` renders a loss warning (model the
   existing M1 glossary-gate blocker `:79-116`) + "I understand, proceed" gate before
   enabling adopt. i18n keys ×4 locales under `kgOntology`.

**Tests:** BE unit (diff: user-only additions surface as losses; no-current → empty);
FE vitest (warning renders when `has_current`, adopt blocked until confirm). Browser smoke
folds into §6.

**Files:** `ontology_mutations.py`, `routers/public/ontology.py`,
`frontend/src/features/knowledge/{api,hooks,components}/*`, i18n, tests.

---

## 7. Fan-out plan + dependency graph

**Parallel worktree-isolated lanes** (each its own git worktree to avoid file clobber):

```
A cardinality ─┐ (A delivers ExtractionSchema.edge_cardinalities + create_relation(cardinality))
B cache-key    │  independent
C grantee-tl   │  independent
D extract-item │  independent (uses ExtractionSchema; no A dep — only reads existing fields)
E triage(E1→E2→E3) ── E1's writer reuses create_relation; E2 reuses E1 ── single agent, serial inside
F revadopt-loss (BE+FE) independent
```

- **A, B, C, D, F** run **fully parallel** (disjoint files).
- **E** runs parallel to all of them BUT its E1 `close_previous` reuses Lane-A's
  cardinality close. To avoid a cross-lane code dep, **E1 calls `create_relation` with
  `cardinality="single_active"` directly** — that param lands in A. **Sequence: merge A
  first, then E** (or have E's agent branch off A's worktree). Practically: run A+B+C+D+F
  in wave 1; merge; run E in wave 2 on the merged base.
- **Conflict watch:** A & D both import `ExtractionSchema` (different files, no clobber).
  E3 & F both touch `ontology_mutations.py` — E is wave 2 so F (wave 1) merges first;
  E3 adds methods on the merged file.

**Per-lane gate (every lane):** TDD → VERIFY (run the suite, paste evidence) → 2-stage
REVIEW → `/review-impl` on C and E (auth/tenant boundaries). Knowledge unit suite via HOST
pytest `PYTHONPATH=sdks/python`, do NOT export `INTERNAL_SERVICE_TOKEN`. Gateway lanes
(none here) would use jest. provider-gate clean before each merge.

**Merge order:** wave1 (A,B,C,D,F) → compose-verify (full KG suite green) → wave2 (E) →
compose-verify again.

---

## 8. Final live E2E (the "gom lại" step — §6 of the request)

After all lanes merge, bring up the stack
(`infra/docker-compose.yml`: postgres+neo4j+rabbitmq+provider-registry+ai-gateway+
knowledge+worker-ai; **rebuild touched images first** — stale-image trap) and run ONE
consolidated cross-service E2E that also clears the deferred **live-smoke** rows it covers:

1. **Extraction + cardinality + cache (A,B,D + `D-KG-L7-LIVE-SMOKE` residual,
   `D-LB-LIVE-SMOKE`):** seed a project CLOSED schema with a `single_active` edge type →
   run a real extraction (BYOK LM Studio) → assert on-schema edge written + stamped, a
   second `single_active` edge auto-closes the first, off-schema parks to triage, and a
   re-run with a *different* schema_version does NOT cache-collide.
2. **`/extract-item` C27 path (D):** drive composition-service approve → `/extract-item` →
   assert ontology-aware extraction into the delta project.
3. **Grantee timeline (C + `D-KG-LD-NEO4J-SMOKE`, `D-KG-LD-GRANTEE-TIMELINE`):** owner +
   a VIEW-grantee read the same entity's edge timeline; non-grantee 404.
4. **Triage apply (E + `D-KG-LH-NEO4J-REAPPLY`):** park → resolve `map`/`place_edge` via
   the confirm spine → edge appears in Neo4j; schema-write confirm bumps schema_version.
5. **Adopt loss + UI (F + `D-KG-LE-BROWSER-SMOKE`, `D-KG-LC-ROUTE-LIVE-TEST`):** Playwright
   — customize a schema, re-adopt, assert the loss warning lists the customizations and
   gates the button.

Each passing E2E assertion ticks its live-smoke deferred row. Record the recipe (seeds,
driver) in SESSION_HANDOFF; remove seeds after the run.

---

## 9. Deliverables / done-definition

- 8 deferred rows cleared with code + tests + an entry in
  `docs/plans/2026-06-20-knowledge-graph-ontology-build.md §10`.
- `/review-impl` clean on lanes C and E.
- Final E2E green; the live-smoke rows it covers ticked.
- SESSION_HANDOFF updated; one commit per lane (stage only changed files).
- `D-KG-LG-REAL` explicitly left for the glossary branch (documented, not actioned).
