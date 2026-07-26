# KG (knowledge-service) MCP Catalog Unification — Design Spec

**Status:** DESIGN (checkpoint) · **Date:** 2026-07-22 · **Branch:** `feat/frontend-tools-mcp-migration`
**Precedents:** book redesign (`8f0e40d4e`…), glossary unification (`docs/specs/2026-07-22-glossary-catalog-unification.md` → Parts A–F, live-proven 42→25, gemma 7–8/8). Same playbook, KG domain (Python/FastMCP).

---

## 1. Problem

knowledge-service `/mcp` registers **37 tools, ALL default-visible (0 legacy)** — live-counted on
`:8216`. Bigger than glossary's pre-shrink 42. Same bloat pattern: several near-identical *shapes*
differing only by a scope/target/op, which a mid-tier model juggling 37 tools mis-picks between.

**Goal:** collapse the same-shape clusters behind enum-discriminated tools + retire an off-audience
surface, the way glossary went 42→25. Python `require_meta(visibility="legacy")` is supported
(`sdks/python/loreweave_mcp/meta.py:90,133`), so deprecation works here too.

## 2. Governing tension — shrink vs weak-model discoverability (READ FIRST)

Same rule as glossary (proven by the gemma smoke): **merge only tools that are near-identical in
SHAPE and that a model would mis-pick between**; KEEP a "duplicate" that is a genuine discovery
affordance or a distinct *purpose*. Corollaries locked from the glossary run:
- A unified tool's **description must front-load the plain user action verb** — `_meta` synonyms are
  NOT shown to the model, so the description carries discovery (the `set_genres` miss).
- Closed-set discriminator ⇒ **`enum`** in the schema (Literal in Python) — the model keys on it.
- Do **not** merge across a **safety-tier boundary** (A/direct vs W/confirm) into one arg-selected
  behavior — that's the CAT-2 footgun (kept `kg_triage_resolve` A vs `kg_triage_schema_write` W split).
- **Reuse the legacy cores** (here: the `_dispatch(ctx, "<name>", args)` executor path is already the
  single source of truth — every MCP tool is a thin wrapper over `app/tools/` executors, so a unified
  tool just dispatches to the same underlying `tool_name`s; no business logic is duplicated or moved).

## 3. Cluster decisions

### 3.1 Graph query by scope — 3 → 1  ✅ (strong)

`kg_graph_query` (one project) · `kg_world_query` (a whole world) · `kg_multi_query` (an arbitrary set
of projects) all **read the KG as nodes + edges** — identical output, same verb, differing only by
*scope*. → **`kg_graph_query`** with `scope ∈ {project (default), world, multi}`:
- `project` → the current project (ambient `project_id`), `view`/`as_of_chapter` as today.
- `world` → requires `world_id`; `unify` option.
- `multi` → requires `project_ids[]` (1–16); `unify` option.
Flat superset (a weak model sees which field each scope needs). `project` is the default so the common
case is a no-op discriminator. Legacy-tag `kg_world_query` + `kg_multi_query`. Dispatches to the same 3
executors. NOTE the `unify` clustering (by_name/semantic) applies to world+multi only — validate per-scope.

### 3.2 Build jobs — 2 → 1  ✅ (strong)

`kg_build_graph` (extraction) · `kg_build_wiki` (wiki articles) are identical in shape — an EXPENSIVE
async job that mints a confirm-token + cost summary (both `W`, `async_job=True`), differing only by
target. → **`kg_build`** with `target ∈ {graph, wiki}` + the target's params (llm_model/scope/chapter
range for graph; model_ref/entity_ids for wiki). `kg_run_benchmark` stays separate (it's the cheap
*prerequisite* gate, different lifecycle). Legacy-tag `kg_build_wiki` (fold into `kg_build`).

### 3.3 Ontology proposes — 3 → 1  ◑ (moderate)

`kg_schema_edit` (add/deprecate edge/fact type) · `kg_adopt_template` (copy an ontology template) ·
`kg_sync_apply` (pull upstream template changes) are all **`W`/confirm-minting ontology-change
proposals** — same shape (mint confirm_token + summary; human redeems on the review surface). →
**`kg_ontology_propose`** with `op ∈ {schema_edit, adopt_template, sync_apply}` + per-op params. No
safety-boundary crossing (all W/confirm). Legacy-tag the 3. Mirrors glossary's `propose_batch`
absorbing the singleton ontology proposals. The 3 *reads* (`kg_schema_read` / `kg_list_templates` /
`kg_sync_available`) stay SEPARATE — different purposes (current schema / adoptable templates / pending
diff), merging would hurt discovery (the glossary "ontology reads" non-merge).

### 3.4 View CRUD — 2 → 1  ◑ (moderate)

`kg_view_upsert` (create/replace) · `kg_view_delete` (both `A`, per-user saved lenses) → **`kg_view_edit`**
with `op ∈ {upsert, delete}`. `kg_view_read` stays (the read). Legacy-tag the 2. (Both Tier-A, so no
safety-boundary issue; delete is reversible via upsert.)

### 3.5 Node creation — 2 → 1  ◑ (moderate)

`kg_create_node` (one manual node) · `kg_project_entities_to_nodes` (bulk seed nodes from the book's
glossary) are both **`A` "add nodes to the graph"**, differing by source. → **`kg_add_nodes`** with
`mode ∈ {manual, from_glossary}`: manual needs name+kind; from_glossary takes optional entity_ids[]
(omit = whole glossary). Legacy-tag the 2. (Both idempotent, both Tier-A.)

### 3.6 `lore_*` reader surface — LEGACY (audience), verified

`lore_ask` / `lore_browse_entities` / `lore_entity` / `lore_timeline` are a **reader's spoiler-safe
agent** (server-enforced window from the reader's furthest-read chapter — W11-M2), a different audience
than the author co-writer. → **legacy-tag all 4.**

**Federation VERIFIED (Explore, 2026-07-22):** `lore_*` genuinely reaches the author catalog — ai-gateway
whitelists the `lore_` prefix (`services/ai-gateway/src/config/config.ts:110-115`, `EXTRA_PREFIX_MAP.knowledge
= ['kg_','story_','lore_']`), chat-service aliases `lore_→glossary` domain
(`tool_discovery.py:724-737`), and it is **hot-seeded** on the `book`/`editor` co-writer surfaces
(`skill_registry.py:105-112` glossary skill `hot_domains={glossary}`; `hot_tool_names` returns every
non-legacy glossary-domain tool). So legacy-tagging is a REAL removal from the author hot-set + fuzzy
discovery; `tool_load` still loads them (labeled deprecated — `tool_discovery.py:911-968`), the escape
hatch for the reader context. There is currently **no reader surface** in chat-service (surfaces are
book/editor/studio/chat/admin), which is exactly why the reader tools bleed into the author catalog.

**Justification is AUDIENCE, not "a unified search covers it".** VERIFIED (Explore): **no unified
cross-store search tool exists** — `memory_search` spans chapter/chat/glossary but not KG graph or the
lore spoiler-window; `story_search` is manuscript-only; `book_read/list/search` is single-book content
nav; the only thing literally "unified" (`mcp_tools_unified.go`) is book cat/ls/grep. So the search
cluster (§3.7) stays split, and `lore_*` is retired because it's the wrong audience for the author
catalog — NOT because its capability is consolidated elsewhere. (A real unified cross-store search would
be a separate feature; noted, not in scope.)

### 3.7 Explicit NON-targets (keep — distinct purpose or safety boundary)

| Tool(s) | Why kept |
|---|---|
| `kg_schema_read` / `kg_list_templates` / `kg_sync_available` | 3 distinct ontology READS — merging hurts discovery |
| `kg_triage_resolve` (A) vs `kg_triage_schema_write` (W) | CAT-2 safety-tier boundary (direct vs confirm) |
| `kg_triage_place_edge` | writes a real edge (distinct effect from a schema resolve) |
| `memory_remember` vs `kg_propose_fact` | different destinations (memory store vs graph review inbox) — flagged, kept |
| `story_search` vs `memory_search` | manuscript prose find vs stored-knowledge find — deliberately cross-referenced (pending §3.6 unified-search check) |
| `kg_project_create/list/set_embedding_model` | distinct lifecycle (glossary kept its project lifecycle too) |
| `kg_entity_edge_timeline`, `memory_timeline`, `memory_recall_entity` | distinct entity/temporal reads |

## 4. Target catalog

`kg_graph_query` is enhanced **in place** (gains `scope`); the other 4 are new names
(`kg_build` · `kg_ontology_propose` · `kg_view_edit` · `kg_add_nodes`). **15 tools legacy'd** —
world_query, multi_query, build_graph, build_wiki, schema_edit, adopt_template, sync_apply,
view_upsert, view_delete, create_node, project_entities_to_nodes, + the 4 `lore_*`.

**37 registered → 41 (with 4 new) → 26 default-visible** (15 legacy). ~30% shrink.

## 5. Envelope

Most KG tools are ALREADY functionally ambient on `project_id` (backend resolves `X-Project-Id`; only
`story_search`/`memory_search` carry the `ambient_project=True` tag today). Each NEW unified tool is
born `ambient_project=True` where project-scoped. The broader survivor `ambient_project` tagging is the
same **parked long-tail** (functionally-ambient-already via injection/backend) — not this pass.

## 6. Migration atomicity

Each legacy-tag + its unified replacement land in the SAME change; every unified tool dispatches to the
SAME `_dispatch(ctx, "<legacy_tool_name>", args)` executors (single source of truth — no logic moved).
The KG contract/drift guards (`services/knowledge-service/tests/`) regen in the same commit. Verify
the ai-gateway/chat-service federation excludes `visibility:legacy` from the hot-set (the Python CAT-4
consumer side).

## 7. Build plan (parts)

- **Part A** — the 2 strong merges: `kg_graph_query` scope-enum (absorb world+multi) + `kg_build`
  target-enum (absorb build_wiki). Legacy-tag 3.
- **Part B** — `kg_ontology_propose` op-enum (absorb schema_edit/adopt_template/sync_apply). Legacy 3.
- **Part C** — `kg_view_edit` + `kg_add_nodes`. Legacy 4.
- **Part D** — `lore_*` legacy (after §3.6 federation verify) + any unified-search reconciliation.
- **Part E** — live: catalog count + gemma discoverability smoke (real test, per user) + handoff.

Each part: build + KG test suite + contract/drift + commit. VERIFY: real cross-service call
(chat-service ↔ ai-gateway ↔ knowledge-service) + the discoverability smoke.
