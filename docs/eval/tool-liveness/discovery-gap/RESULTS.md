# Tool-discovery gap — does a weak model reach LAZY tools? (2026-07-22)

**Foundational question:** the hot-set + lazy-tail catalog-shrink strategy (book/glossary/KG
unification) assumes a chat model can reach tools that aren't in the per-surface hot-set — via
`tool_list(category)` → `tool_load(name)` → call. A recurring handoff note claimed *"gemma won't
tool_load a lazy tool — needed pinning."* If true, the shrinks help less than hoped. Verified against
reality (gemma-4-12b), NOT the handoff.

Harness: `probe.py` — faithfully replicates the discovery advertisement (only `tool_list`/`tool_load`
core + the group directory, a "universal" surface where every domain tool is LAZY), drives the
multi-turn loop, and services `tool_list`/`tool_load` from the LIVE glossary catalog (:8211).

## Findings

**1. Discovery WORKS — the "won't tool_load" claim is stale/false.**
gemma reliably `tool_list(glossary)` → `tool_load(name)` → **calls** the lazy tool:
- `glossary_search` — REACHED
- `glossary_curation_list` — REACHED
- (`glossary_propose_entities` — see #2)

The claim predates **F17**, which replaced the fuzzy `find_tools` with the deterministic
`tool_list`/`tool_load` pair. With the current mechanism, a weak model discovers + loads + calls a lazy
READ tool.

**2. The residual "loop" is READ-THEN-ACT, not a discovery bug — and it recovers.**
`glossary_propose_entities` (a structured WRITE) first sends gemma to read the ontology (to find the
valid `kind`) — this happens whether the tool is LAZY or already HOT (with the write tool directly
advertised, gemma still picks `glossary_book_ontology_read` first). Serviced with the ontology result,
gemma **recovers**: `glossary_book_ontology_read` → `glossary_propose_entities`
`{items:[{kind:"character",name:"Mara"}]}` — the correct payload. Same defensible pattern as the
catalog-shrink discoverability "misses" (glossary reassign, KG ontology adopt).

**3. Loop-breaking is already built (F18) — and the naive fix backfires.**
`stream_service.py`: `MAX_TOOL_ITERATIONS=5`, the **F18 tool_list loop breaker**
(`TOOL_LIST_CATEGORY_CAP=1` — 2nd list of a category = a loop; on repeat it AUTO-LOADS the category +
STEERS, never errors), a repeated-read breaker, `ReasoningLoopDetector`. The comment records that a
naive explicit ERROR **backfires** (gemma retried harder, measured 28→311 calls) — the working lever is
*auto-load + steer to forward progress*. The probe over-reported the loop precisely because it did NOT
replicate F18.

## Conclusion

The foundational concern is **resolved**: the model reaches lazy tools, loops are bounded, writes
recover. The hot-set + lazy-tail + catalog-unification strategy is **validated**. The stale
"won't tool_load" note should be corrected wherever it appears (it made us worry about a non-problem).

When verifying discovery, replicate F18's auto-load-and-steer (or test through the real chat-service
run-loop) — a bare harness over-reports the loop. Run: `python probe.py` (needs glossary `/mcp` :8211 +
lm_studio :1234 with gemma-4). Toggles: `EXPLICIT=1` (explicit tool_load directive), `LOOPBREAK=1`
(steer on a detected repeat).
