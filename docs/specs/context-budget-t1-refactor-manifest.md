# T1 — SET-tool response-contract refactor manifest

**Spec:** [`2026-07-03-context-budget-law.md`](2026-07-03-context-budget-law.md) §14b/§14c.
**Rule (silent-cap, CLAUDE.md):** a SET-returning MCP tool not yet refactored is TRACKED
here, never silently "done". Refactor **worst-first** by measured bytes×frequency; add a
`✓live` row when a tool is picked up (§14c). Ranking source until the A5 byte histograms
land: `scripts/context-budget-t0-measure.py` over persisted `chat_messages.tool_calls`.

The pattern every refactor uses: `loreweave_mcp.apply_response_contract(items,
ref_fields=…, detail=…, limit=…)` — `detail` defaults to **`full`** (versioned migration,
§6b/D2: federated/legacy callers unchanged; the chat-compiler opts into `summary`),
never a silent truncation (`{total,returned,truncated}` meta).

## Status

| Tool | Service | Status | Evidence |
|---|---|---|---|
| `composition_list_outline` | composition | ✅ refactored | `detail`+`limit`; live −74.3% (`context-budget-t1-live-e2e.py`) |
| `composition_get_outline_node` | composition | ✅ NEW cheap read | live 538 B vs 53 KB forced dump (−99%); kills the 146K root cause |
| `jobs_list` | jobs | ✅ refactored | `detail` drops params/error; `test_jobs_list_summary_drops_heavy_params` |
| `composition_get_prose` | composition | ⏳ tracked | single-object read (L2-exempt from summary default); add `detail=summary` = metadata+`draft_version` only (drop chapter body). Book-draft body key TBD at pickup. |
| `story_search` | knowledge | ⏳ tracked | grounding hot-path; reference-first snippets + `limit`. 3-schema-source tool (see [[knowledge-mcp-three-schema-sources-fastmcp-strips]]) |
| `memory_search` | knowledge | ⏳ tracked | grounding hot-path; reference-first + `limit` |
| `memory_timeline` / `memory_recall_entity` | knowledge | ⏳ tracked | reference-first |
| `kg_graph_query` / `kg_world_query` / `kg_multi_query` | knowledge | ⏳ tracked | bounded node+edge refs, not full tree; `get_by_id` for a node's full body |
| `kg_entity_edge_timeline` / `kg_schema_read` / `kg_list_templates` / `kg_view_read` / `kg_triage_list` / `kg_project_list` | knowledge | ⏳ tracked | reference-first / already partly bounded |
| `composition_motif_search` / `_motif_get` / `_motif_book_list` / `_motif_link_list` / `_motif_suggest_for_chapter` / `_arc_suggest` / `_arc_import_analyze` / `_motif_mine` | composition | ⏳ tracked | reference-first + `limit` |
| `composition_list_canon_rules` | composition | 🟢 `@small_return` | inherently small (status/rule list); exempt, honesty-checked by snapshot |
| `composition_get_generation_job` | composition | 🟢 single-read | `get_by_id`, exempt from summary default |
| `translation_coverage` / `translation_list_versions` / `translation_segment_status` / `translation_job_status` | translation | ⏳ tracked | no full translated bodies at summary; reference-first |
| `jobs_get` | jobs | 🟢 single-read | `get_by_id`, exempt |

Legend: ✅ done+proven · ⏳ tracked (worst-first backlog) · 🟢 exempt (`@small_return` / single-object read).

## Deferred infrastructure (tracked, not forgotten)

- **A5 per-tool byte histograms** (composition/translation/jobs — knowledge already emits
  `knowledge_tool_call_result_size_bytes`). The production ranking + T2-meter telemetry
  source. **Folded into T2** (budget meter + GUI-monitor telemetry) since that is where
  per-turn/per-tool telemetry lives. Until then, ranking uses the persisted-corpus script.
- **Response-shape contract-snapshot harness** (§13b — mirror `frontend-tools.contract.json`):
  a committed `contracts/mcp-response-shapes.contract.json` + a `_normalize`-style test that
  records each SET tool's `detail=summary` shape and fails on drift. Built alongside the §13
  CI meta-check (todo: Inspector/enforcement). Until then each refactor carries its own
  deterministic guard test (e.g. `test_outline_response_contract.py`).

## Family-B completion (2026-07-04) — parallel refactor, 18 SET tools

Refactored via 3 disjoint-service subagents (fan-out build / serial integrate),
each **review-gated** (cold-start diff review: default=`full` preserved, no
security/gate line removed, meta surfaced) + independently re-verified:

- **jobs** (`b…`): `jobs_list` ✅
- **composition** (`60bd…`, `d856…`): `list_outline`✅ `get_outline_node`✅(new) `list_canon_rules`🟢
  `motif_search`✅ `motif_book_list`✅ `motif_suggest_for_chapter`✅ `arc_suggest`✅ ·
  🟢 `motif_get` `motif_link_list` `motif_mine` `arc_import_analyze` `get_prose` `get_generation_job`
- **translation** (`d856…`): `list_versions`✅ `job_status`✅ · 🟢 `coverage` `segment_status`
- **knowledge** (`b458…`): `story_search`✅ `memory_search`✅ `memory_timeline`✅ `kg_graph_query`✅
  `kg_world_query`✅ `kg_multi_query`✅ `kg_entity_edge_timeline`✅ `kg_triage_list`✅ ·
  🟢 `memory_recall_entity`(get-by-id) `kg_schema_read` `kg_list_templates` `kg_view_read`
  `kg_sync_available` `kg_project_list`

Each service added contract-guard tests (summary drops heavy body / keeps refs /
materially smaller / default=full). Suites green: translation 1039 · composition
1490 · knowledge 3496. **Remaining B:** (1) the response-shape contract-snapshot
harness (§13b), (2) live-e2e per tool through ai-gateway federation — the
composition/outline live drop is proven (−74%); knowledge/translation live-e2e is
partly gated on **D-EVAL-BOOK** (need seeded data to show a real drop), tracked.
A5 byte histograms remain deferred (production ranking; the persisted-corpus
script + this manifest are the interim ranking).

## GATE (T1)

Met when the worst offender's cut is proven live with zero consumer regression — **DONE**
for the flagship (`composition_list_outline` −74.3%, `get_outline_node` −99%) and confirmed
to generalize cross-service (`jobs_list`). Remaining rows are picked up worst-first; this
manifest is the standing backlog so no SET tool is silently skipped.
