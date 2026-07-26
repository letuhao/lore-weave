# Plan: unify the agent's search tools (grep/glob minimalism) + chapter body read

**Date:** 2026-07-05 · **Branch:** `feat/context-budget-law` · **Origin:** the continue-writing
measurement (`docs/eval/context-budget/measurement-continue-writing-2026-07-05.md` §7) — the agent
punts on chapter-text recall because it has two overlapping search tools and picks the empty one.

## Problem (measured)
`story_search` (lexical-inclusive hybrid over the manuscript — works with **zero embeddings**) and
`memory_search` (semantic-only over Neo4j passages — **empty** until passages are ingested) are two
"greps." A weak model reaches for `memory_search`, gets nothing, and punts — even though the raw
chapter text is right there. Claude-Code's grep/glob teaches the fix: **one obvious tool per job.**

## Design (user-approved 2026-07-05: full engine + surface unify + chapter body)

**Canonical search tool = `story_search`** (the superset engine: lexical FTS/trigram + CJK +
semantic vectors + RRF + rerank). Already federated (fix `8ca703915`) + hot-seeded on book surfaces.

1. **Engine-unify (`_handle_memory_search` → the hybrid engine).** `memory_search` delegates to
   `run_hybrid_search(mode="hybrid", granularity="block")` over the linked book when the manuscript
   engine is available (`book_client` + `reranker_client` present), mapping hits to its existing
   `{snippet, source_type, score}` shape (`source_type="chapter"`). Falls back to the current
   semantic-passage path (`find_passages_by_vector`) when the manuscript engine is unavailable or
   the book link is absent. Net: **whichever search tool the agent picks now includes the lexical
   leg → never empty when the chapter text matches.** This subsumes the separate "degrade-to-lexical"
   fix. Back-compat: same response shape; a previously-empty result becomes a real one (strictly
   better for every caller).

2. **Surface-unify.** `story_search` is THE hot/canonical search tool. `memory_search` stays
   registered (wide blast radius — FE i18n/labels, public-gateway policy, many tests — so NOT
   removed) but is (a) already find_tools-lazy, and (b) its description updated to point at
   `story_search` as the primary manuscript search, so the agent's effective search surface is one
   tool. A hard removal/alias of `memory_search` is a separate, later cleanup.

3. **Chapter body read (`book_get_chapter`, book-service Go).** Add an opt-in `include_body`
   (default false — token-safe) that returns the chapter's plain-text prose, extracted from the
   draft/published tiptap body via the existing `jsonb_path_query(body,'$.content[*]._text')`
   pattern (see the publish path in `mcp_actions.go`). Enables the grep→read loop
   (`story_search` locate → `book_get_chapter include_body` read) for continue-writing.

## Touch list
- **knowledge-service (Py):** `app/tools/executor.py` `_handle_memory_search` (delegate); the
  `memory_search` description in `app/mcp/server.py` + `app/tools/definitions.py` (3-schema-source
  rule — signature + ARG model/OpenAI schema must move together; `WRITE_MCP_SHAPES=1` if the
  response shape changes — it does NOT here, so the snapshot stays); tests
  `tests/unit/test_tool_executor.py`.
- **book-service (Go):** `internal/api/mcp_actions.go` `book_get_chapter` tool (+ its input struct +
  the prose SQL) + `mcp_actions_db_test.go`.
- **chat-service (Py):** hot-seed already covers `story` (done). Confirm `test_agent_surface.py`
  still green; update any description assertion.
- **FE:** no removal — `memory_search` label stays; only its meaning narrows. Verify
  `agentSurface`/`AgentContextRack` tests unaffected.

## Verify (per piece, then cross-service)
- knowledge: unit test that `memory_search` returns manuscript hits (lexical) with a spy/live PG;
  live-smoke `memory_search "Hawkins"` on the Dracula project → returns the chapter snippet.
- book-service: unit + live `book_get_chapter include_body=true` → returns real prose.
- cross-service live-smoke: re-run the continue-writing scenario → the agent's `memory_search` no
  longer returns empty; the firm-name / chapter-recall punts resolve.
- Re-run the grounded A/B (baseline + T5) → confirm the eval is now objective (no tool-surface
  confound) and re-judge.

## Out of scope (consciously)
Hard removal/alias of `memory_search`; adding chat/glossary as first-class `story_search` sources
(chapters is the 90% case; glossary has `glossary_search`, chat is in-context); passage ingestion
(`D-KG-PASSAGES-NOT-INGESTED` — separate); find_tools name-vs-description ranking (mitigated by
hot-seeding).
