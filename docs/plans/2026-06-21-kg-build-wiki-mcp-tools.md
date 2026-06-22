# Plan — `kg_build_graph` + `kg_build_wiki` MCP tools (cost-gated, confirm-spine)

> **Date:** 2026-06-21 · **Branch:** `feat/knowledge-graph-ontology` (PR #40)
> **Size:** L (2 cost-gated class-C tools on the existing KM6 confirm spine)
> **Clears:** `D-KG-LF-BUILDKG-MCP`, `D-KG-LF-WIKI-MCP`
> **Goal:** let an agent trigger "build the knowledge graph" and "build the wiki" for a
> book's project — the last two agent-driven gaps in the create→research→ontology→
> extract→KG→wiki→write scenario.

## Why confirm-spine (not a direct tool)

Both ops are **expensive + irreversible spend** (LLM extraction over chapters / wiki
generation over entities). The established pattern for that is **propose→confirm** (cf.
`translation_start_job`): the MCP tool **mints** a confirm-token carrying a cost
estimate; the **human** redeems it via `POST /v1/kg/actions/confirm` (browser-JWT,
unreachable from the MCP path → INV-T3 holds). The heavy job-start lives in the
**confirm-route effect**, which has full FastAPI DI — so the MCP tool stays light
(it only resolves + estimates + mints).

## Design decisions (validated against the code)

1. **Model resolution (the gap that made these "not clean shims"):**
   - `embedding_model` = `project.embedding_model` (canonical stored column; the exact
     precedent is `internal_dispatch.py` — campaign extraction starts with no UI form).
     Missing → tool error "this project has no embedding model configured (run extraction
     setup once in the UI)".
   - `llm_model` = an **explicit tool arg** (a provider-registry model ref). The agent
     finds one via `settings_list_models`. No reliable project-stored LLM default exists
     (the campaign path also supplies `model_ref` per request), so we require it rather
     than guess. Cheap arg, clear description.
2. **Benchmark gate pre-check at mint:** `_start_extraction_job_core` 409s unless a
   passing `project_embedding_benchmark_runs` row exists for `embedding_model`. The mint
   handler **pre-checks** this (via `BenchmarkRunsRepo`) and fails early with an actionable
   message ("run the embedding benchmark in extraction setup first") instead of minting a
   card that 409s at confirm.
3. **Cost in the card:** the mint handler computes the estimate by calling the **estimate
   core** (items × tokens × `cost_per_token(llm_model)`), and the preview rows show
   items_total + a $low–$high range. Stored in the token params so preview re-renders.
4. **Grant:** EDIT to start extraction (mirrors `start_extraction_job`); the confirm
   re-check uses the spine's MANAGE gate (`_authorize_action`) — MANAGE ⊇ EDIT, so a
   MANAGE holder (incl. owner) can redeem. (Documented: confirm requires MANAGE; an
   EDIT-only collaborator can propose but a MANAGE/owner confirms — acceptable for v1.)
5. **Wiki entity scope:** `kg_build_wiki` resolves `entity_ids` = the book's glossary
   entities (via the glossary client `count`/list) unless an explicit subset is given.
   Empty → tool error ("extract the glossary first"). Cost scales with entity count.

## Tool 1 — `kg_build_graph`

**Mint (MCP tool, `app/tools/build_tools.py`):**
- args: `llm_model: str` (required), `scope: "all"|"chapters"|"chat"|"glossary_sync"` (default `all`), `chapter_from?/chapter_to?: int`.
- resolve project owner via `_resolve_project_owner(ctx, EDIT)`; load project; require `project.embedding_model`.
- pre-check benchmark via `BenchmarkRunsRepo.latest_passing(project_id, embedding_model)` (or equivalent).
- estimate cost (reuse `estimate` math; or call a small shared estimate helper).
- `mint_action_token(DESC_BUILD_GRAPH, params={scope, scope_range, llm_model, embedding_model, items_total, cost_low, cost_high})`.

**Effect (`app/ontology/build_graph_effect.py` → `apply_build_graph` / `preview_build_graph`):**
- `apply`: build `StartJobRequest(scope, scope_range, llm_model, embedding_model)` → `_start_extraction_job_core(project_id, body, owner, projects_repo, jobs_repo, benchmark_repo, book_client=…, extraction_wake=…)` → `{job_id, status}`. Map 409 (benchmark/active-job)/422 to clean errors.
- `preview`: re-render rows (items + cost) from current state.

**Confirm wiring (`kg_actions.py`):** add `DESC_BUILD_GRAPH` branch in `confirm_action` + `preview_action`; inject `jobs_repo`, `benchmark_repo`, `book_client`, `extraction_wake` (existing `deps.py` factories).

## Tool 2 — `kg_build_wiki`

**Mint:** args `model_ref: str` (required LLM), optional `entity_ids: list[str]`. Resolve owner (EDIT); resolve entity_ids (given subset, else all book entities); empty → error. Estimate cost (entities × per-entity tokens). Mint `DESC_BUILD_WIKI` with params.

**Effect (`app/ontology/build_wiki_effect.py`):** `apply` → call the wiki-generate core (`internal_wiki` generate path, refactored to a callable core) with `entity_ids` + `model_ref` → `{job_id}`. `preview` → entity count + cost.

**Confirm wiring:** `DESC_BUILD_WIKI` branch + wiki deps.

## Shared plumbing
- `confirm.py`: add `DESC_BUILD_GRAPH = "kg_build_graph"`, `DESC_BUILD_WIKI = "kg_build_wiki"` to constants + `_LIVE_DESCRIPTORS` + `__all__`.
- `definitions.py` / `executor.py`: register the two arg models + handlers + OpenAI tool defs (mirrors `project_tools` wiring) — count 23→25.
- `mcp/server.py`: two propose→confirm shims (mirror the class-C shims).

## Tests
- `test_build_tools.py` (unit, fakes): build_graph mint — missing embedding_model → error; missing benchmark → error; happy → confirm_token + cost rows; smuggled scope arg rejected. build_wiki mint — no entities → error; happy → token. Effect drift/maps.
- `test_mcp_server` catalog auto-covers (25 tools); inputSchema-mirror auto-covers.
- confirm/preview dispatch: extend `test_kg_actions_router` / a new effect test with a fake `_start_extraction_job_core` to assert the DESC_BUILD_GRAPH branch calls it.

## Live-smoke (rebuilt image)
- `tools/list` → both present (25 tools).
- `kg_build_graph` mint with a real project (embedding_model set + benchmark) → confirm_token + cost; missing-benchmark project → clean error. (If no benchmarked project handy: assert the error path live, defer the full confirm→job to a documented row.)
- `kg_build_wiki` mint → token or "extract glossary first".

## Sequencing (commit at each tool = risk boundary)
1. `confirm.py` descriptors + `build_graph_effect.py` + `kg_build_graph` mint + confirm wiring + shims + wiring + tests → VERIFY → commit.
2. `build_wiki_effect.py` + `kg_build_wiki` + wiring + tests → VERIFY → commit.
3. Rebuild knowledge-service → live-smoke both → SESSION + commit.
