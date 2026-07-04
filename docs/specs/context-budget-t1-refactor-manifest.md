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
| `composition_get_prose` | composition | ✅ refactored 2026-07-05 | `detail=summary` drops the heavy `body`, keeps `draft_version`+metadata+`body_omitted` marker (`_project_prose`); `test_prose_response_contract.py`; MCP wire test green |
| `story_search` | knowledge | ✅ refactored | `detail`+`limit`+`STORY_SEARCH_REF_FIELDS`; `apply_response_contract` `executor.py:342`; all 3 schema sources in lockstep (`_DETAIL_ARG` + `StorySearchArgs` + handler); snapshot-pinned |
| `memory_search` | knowledge | ✅ refactored | `detail`+`limit`+`MEMORY_SEARCH_REF_FIELDS`; `executor.py:426`; snippet preview + full `text` dropped at summary; snapshot-pinned |
| `memory_timeline` | knowledge | ✅ refactored | `MEMORY_TIMELINE_REF_FIELDS`; `executor.py:531`. `memory_recall_entity` → 🟢 single-object read (exempt, `executor.py:435`) |
| `kg_graph_query` / `kg_world_query` / `kg_multi_query` | knowledge | ✅ refactored | shared subgraph projection (`GRAPH_NODE/EDGE_REF_FIELDS`, `graph_schema_tools.py:170`) — bounded node+edge refs, not the full tree |
| `kg_entity_edge_timeline` / `kg_triage_list` | knowledge | ✅ refactored | `TIMELINE_INSTANCE_REF_FIELDS` (`:1294`) / `TRIAGE_GROUP_REF_FIELDS` (`:1397`); snapshot-pinned |
| `kg_schema_read` / `kg_list_templates` / `kg_view_read` / `kg_project_list` | knowledge | ⏳ verify-at-pickup | no `apply_response_contract` — inherently small (a schema / template list / view def / project list). Confirm each is genuinely bounded → mark 🟢, else add `detail`. Not a dump risk. |
| `composition_motif_search` / `_motif_book_list` / `_motif_suggest_for_chapter` / `_arc_suggest` | composition | ✅ refactored | `_MOTIF_REF_FIELDS`/`_MOTIF_BOOK_REF_FIELDS`/`_ARC_REF_FIELDS`; calls at `server.py:1245,1339,1396,1455`; `test_motif_response_contract.py` |
| `composition_motif_link_list` | composition | ⏳ verify-at-pickup | a link LIST — confirm it's bounded / add `detail`+`limit` if it can be large (`server.py:1750`) |
| `_motif_get` / `_motif_mine` / `_arc_import_analyze` | composition | 🟢 single-read / propose | single-object read or a propose→confirm op (returns a token + estimate, not a SET) — exempt from the summary default |
| `composition_list_canon_rules` | composition | 🟢 `@small_return` | inherently small (status/rule list); exempt, honesty-checked by snapshot |
| `composition_get_generation_job` | composition | 🟢 single-read | `get_by_id`, exempt from summary default |
| `translation_list_versions` / `translation_job_status` | translation | ✅ refactored | `apply_response_contract` `mcp/server.py:278,351`; snapshot-pinned |
| `translation_coverage` / `translation_segment_status` | translation | ⏳ verify-at-pickup | not contracted — `coverage` is per-language stats (likely small → 🟢); `segment_status` is per-segment and CAN be large → add `detail`+`limit` (reference-first, no full translated bodies). The one genuine translation gap. |
| `jobs_get` | jobs | 🟢 single-read | `get_by_id`, exempt |

Legend: ✅ done+proven · ⏳ tracked (worst-first backlog) · 🟢 exempt (`@small_return` / single-object read).

> **Status table RECONCILED against code 2026-07-05** (was heavily stale — the [[debt-batches-list-is-stale-verify-first]] pattern). Verified every row by grepping the actual `apply_response_contract` call sites + `*_REF_FIELDS` constants across all 4 services. **~90 % of the "⏳ tracked" backlog was already ✅** (Family-B + the grounding tools shipped it); the manifest header table simply never got updated. **`composition_get_prose` refactored this pass** (the one clear remaining dump — a full chapter body single-read). **The genuine remaining gaps are small:** `translation_segment_status` (per-segment, can be large — the real one), plus a handful of inherently-small `kg_*`/`motif_link_list` reads to confirm-as-exempt-or-bound. No hot-path grounding tool is un-refactored.

## Deferred infrastructure (tracked, not forgotten)

- **A5 per-tool byte histograms** (composition/translation/jobs — knowledge already emits
  `knowledge_tool_call_result_size_bytes`). The production ranking + T2-meter telemetry
  source. **Folded into T2** (budget meter + GUI-monitor telemetry) since that is where
  per-turn/per-tool telemetry lives. Until then, ranking uses the persisted-corpus script.
- ~~**Response-shape contract-snapshot harness** (§13b)~~ ✅ **SHIPPED 2026-07-04.**
  `contracts/mcp-response-shapes/<service>.json` (4 services) + per-service regen-gated drift
  tests (`test_response_shape_snapshot.py`) via the shared kit helper
  `loreweave_mcp.assert_or_write_shape_snapshot` (regen: `WRITE_MCP_SHAPES=1 pytest …`).
  Pins the EXACT ref set for all 15 ref-field constants → catches drift in BOTH directions
  (dropped ref OR silent re-bloat), which the per-tool semantic guards miss. Guard proven to
  BITE (kit test: write→identical-passes→drift-raises). Coverage audited: all 15
  `apply_response_contract` call sites reference a snapshotted named constant (no inline
  literal escapes). **§13 coverage meta-check SHIPPED 2026-07-04**
  (`assert_or_write_shape_snapshot(…, scan_modules=[…])`): each snapshot test introspects its
  tool module(s) for every `*_REF_FIELDS` name and asserts it is pinned, so a NEW un-pinned
  constant + tool turns the test RED ("checklist → test, not self-report"). Bite-proven in the
  kit test; runs in each service's pytest suite = CI-wired.

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
