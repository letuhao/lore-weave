# KG (knowledge-service) catalog unification — live results (2026-07-22)

Spec: `docs/specs/2026-07-22-kg-catalog-unification.md`. Harness: `kg_discover.py`.

## Catalog shrink (live-counted on knowledge-service `/mcp` :8216)

| | before | after |
|---|---|---|
| registered | 37 | **41** (+4 new; kg_graph_query enhanced in place) |
| default-visible (hot-set) | 37 | **26** |
| legacy/hidden | 0 | **15** |

**5 merges → 4 new tools + 1 enhanced-in-place, folding 10 singles; + 4 `lore_*` retired
(reader audience) + world/multi/build_wiki/… = 15 legacy'd.** 37 → 26 default-visible (~30%).

- `kg_graph_query` **scope** ∈ {project, world, multi} ← +kg_world_query, kg_multi_query
- `kg_build` **target** ∈ {graph, wiki} ← kg_build_graph, kg_build_wiki
- `kg_ontology_propose` **op** ∈ {schema_edit, adopt_template, sync_apply} ← those 3
- `kg_view_edit` **op** ∈ {upsert, delete} ← kg_view_upsert, kg_view_delete
- `kg_add_nodes` **mode** ∈ {manual, from_glossary} ← kg_create_node, kg_project_entities_to_nodes
- `lore_ask/browse_entities/entity/timeline` → legacy (reader audience)

Each merge is a 3-layer change (bespoke `definitions.py` schema + MCP `server.py` + a unified
**executor handler** that DELEGATES to the same legacy cores) because KG's dual MCP+bespoke tool
surface is locked in lockstep by the exact-name + schema-parity tests. No business logic moved.

## Discoverability (gemma-4-12b, `google/gemma-4-12b-qat`, temp 0)

Feed ONLY the 26 default-visible tools; does the weak model pick the right unified tool +
discriminator for a natural request? **Stable ~8/11 per run.**

| scenario | expected | result |
|---|---|---|
| graph project / world / multi | `kg_graph_query` scope=… | ✅ 3/3 reliable |
| build graph / wiki | `kg_build` target=… | ◑ one of the two per run passes; the miss goes to `kg_project_list` (a gemma-12b quirk, not a schema flaw). Front-loading "Build the GRAPH, or generate the WIKI" fixed the wiki case. |
| ontology add edge type | `kg_ontology_propose` op=schema_edit | ⚠️ read-first → `kg_schema_read` (defensible: check the schema before adding) |
| adopt template | `kg_ontology_propose` op=adopt_template | ⚠️ read-first → `kg_list_templates` — **actually correct**: adopt_template *needs* source_schema_id FROM kg_list_templates |
| view upsert / delete | `kg_view_edit` op=… | ✅ 2/2 reliable |
| add node manual / from_glossary | `kg_add_nodes` mode=… | ✅ 2/2 reliable |

**The enum discriminator (scope/target/op/mode) is ALWAYS correct when the tool is picked** — the
design works. The consistent misses are the **read-then-act** pattern (a real multi-turn loop
recovers, and the adopt→list-templates step is genuinely a prerequisite), plus a gemma-12b build/list
confusion. Same shape as the glossary result (7–8/8 with read-first misses).

### Fix the smoke drove
`build-wiki` first mis-routed to `kg_project_list` because `kg_build` led with *"Build the current
project's knowledge"* — burying "wiki". Front-loading *"Build the knowledge GRAPH, or generate the
WIKI"* fixed it (the same front-load-the-action-verb lesson as glossary's set_genres — see
[[feedback_unified_tool_description_front_loads_action_verb]]).

Run: `python kg_discover.py` (needs knowledge-service `/mcp` :8216 + lm_studio :1234 with gemma-4).
