# Glossary ↔ LLM flow migration review

- **Date:** 2026-06-10
- **Why:** `ai-gateway` + glossary MCP arrive *after* the glossary pipeline. The user asked to review existing flows that drive LLMs **via prompt** over glossary data (token-wasteful, unoptimized) and plan a migration to MCP tools once the glossary MCP exists (P1+).
- **Companion:** `2026-06-10-glossary-assistant-architecture.md` · DEFERRED 066.
- **Status:** review (read-only survey + critical filter). Migration is a **post-P1** follow-on, not v1.

## Honest premise check

The premise is **partly right**. A full survey found ~21 glossary↔LLM touchpoints across 6 services, but most are **legitimate RAG grounding that must stay in-prompt** — the LLM genuinely needs the terms inline to translate / co-write / generate. **Tool-ifying grounding does NOT save tokens** (the data still enters the prompt; tool schemas + round-trips can add tokens) and can hurt quality/recall. So the migration is **narrower** than a raw inventory suggests.

The real wins come from exactly two shapes:
1. **Pre-stuffed → on-demand:** glossary packed into *every* prompt even when unused → fetch only when the LLM needs it (a tool call). Saves tokens on turns that don't touch glossary.
2. **LLM-side filtering → deterministic tool:** the LLM is handed a big slice and asked to find/select within it → a targeted tool returns just the needed item.

Everything else is either keep-as-grounding or already deterministic (non-LLM) code mis-flagged by a naive scan.

## Filtered inventory (4 buckets)

### Bucket A — MIGRATE: pre-stuffed grounding → on-demand tool (the real win)
| Flow | Today | Migration |
|---|---|---|
| **chat glossary context** — knowledge `app/context/selectors/glossary.py` + `modes/static.py`(Mode 2)/`full.py`(Mode 3) | Packs a `<glossary>` block (top-20, ~800 tok) into **every** chat turn via `build_context`, even when the turn never references an entity | The glossary **read tools** we build in glossary-assistant **P1** (`glossary_search`/`glossary_get_entity`) let the model fetch on demand. Keep a small **pinned** set pre-stuffed (recall safety); drop the always-on top-20. **This is the flagship target and it's already on the roadmap.** |

*Caveat:* on-demand trades latency + recall (model must decide to call the tool) for token savings. Hybrid (pin a few + tool for the rest) is the right shape, not pure on-demand.

### Bucket B — CONSOLIDATE: duplicated glossary→prompt formatters (mui#3 grounding port)
Three separate "entity → prompt block" formatters exist:
- knowledge `modes/static.py` `_render_entity` → XML
- composition `app/packer/` lenses → prose blocks
- translation `app/workers/glossary_client.py` → JSONL

→ Consolidate behind the **shared grounding port** (mui#3) that `ai-gateway` absorbs at **P6**. Not a token win — a **maintainability/consistency** win (one selection+format+sanitize path). Already planned; this review just confirms the 3 call-sites.

### Bucket C — KEEP: legitimate in-prompt grounding (do NOT tool-ify)
- **translation** `glossary_client.build_glossary_context` (JSONL term map, 1500-tok cap) + v3 `knowledge_context` brief — the translator needs source→target term mappings **inline** to enforce consistency. Tool-ifying would add round-trips without removing the in-prompt data. Optimize *selection/budget* only.
- **composition** packer canon/present/lore lenses — co-writer needs character context inline to write prose. Keep; lazy per-entity lookup would stall generation.
- **lore-enrichment** `generation/generate.py` grounding-cited generation — the cited excerpts ARE the feature (source-faithful generation). Keep.
- **translation extraction** `extraction_prompt.build_known_entities_context` — prior canonical names are **grounding for dedup**; the LLM needs them inline to reuse names. (Alternative: extract-raw-then-resolve-via-tool post-hoc — that's the knowledge entity-resolution path, a *different* architecture, not a drop-in tool swap. Track separately, don't force.)

### Bucket D — NON-ISSUE: already deterministic (a naive scan mis-flags these)
Not LLM-prompt flows at all — no migration: translation v3 `verifier.verify_rules` (rule checks), lore-enrichment `canon_lookup.extract_canon_terms` (jieba), glossary `shortdesc/generator.go` (string truncation), glossary `enrichment_handler`/`canon_content_handler` sanitize (deterministic write-path). Listed only to pre-empt re-flagging.

## Token-reality note

A raw inventory claimed "~30–50K tokens saved." **Discount that.** Grounding flows (Buckets B/C) save ~0 tokens from tool-ification. The genuine savings is **Bucket A only** — turns/jobs that currently pre-stuff glossary but don't use it. Real but bounded; measure before/after, don't assume.

## Sequenced plan (post-P1)

1. **After glossary MCP P1 ships** (read tools exist): migrate **Bucket A** — chat glossary grounding from always-pre-stuff to **pin-few + tool-on-demand**. Measure token delta on real sessions. *(This is essentially glossary-assistant P5/P6 grounding work — the migration and the build converge here.)*
2. **At P6 grounding port** (mui#3): fold **Bucket B**'s three formatters into the shared port behind `ai-gateway`.
3. **Leave Bucket C** as grounding; only revisit selection/budget if profiling shows pain.
4. **Bucket D**: nothing.

## Outcome

The migration is **real but smaller and already largely inside the glossary-assistant roadmap** (Bucket A ≈ P5/P6 grounding; Bucket B ≈ P6/mui#3). It is **not** a separate large workstream and **not** a 30–50K-token windfall. Tracked under DEFERRED 066; execute Bucket A right after P1 with a before/after token measurement.
