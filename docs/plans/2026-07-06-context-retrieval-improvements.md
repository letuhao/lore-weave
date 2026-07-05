# Context Retrieval Improvements — plan

**Date:** 2026-07-06 · **Branch:** `feat/context-budget-law` · **Status:** PLAN (not yet built).

**Source:** the comparative research in [`docs/research/context-management/`](../research/context-management/)
(loreweave audit `01` + Continue/Zed/Aider/Cline architecture studies `02`–`05` + the synthesized
recommendation set `06`, all dated 2026-07-04). This plan **reconciles** those six recommendations
(R1–R6) against the **current** code and against what shipped in the Context Budget Law closeout
this session — then sequences the genuinely-new work.

---

## Headline (the honest conclusion, re-verified against code 2026-07-06)

The research and my own closeout agree: **the budget / compiler / planner / compaction layer is
mature — done or deliberately parked.** The remaining leverage is **one layer down, in KG
*retrieval*.** The single highest-value gap is that the automatic per-turn grounding path
(`passages.py`) is still *"vector search wearing a graph label"*: it does vector → hub/recency
penalty → MMR and **never traverses the graph**, even though the real traversal primitives
(`find_relations_2hop` at [`relations.py:731`](../../services/knowledge-service/app/db/neo4j_repos/relations.py),
`get_project_subgraph` at `relations.py:1028`) already exist and are unused by retrieval. That is the
self-identified `AW-2` gap, and it's assembly — not invention.

**Guiding principle (from research `06` §Nguyên tắc):** *augment, don't replace.* Nothing here
touches the Budget Law, the Compiler ladder, the Planner, or the KG-RAG-vs-ATS decision. Every item
reuses a primitive already in the repo. We do **not** drop vector RAG for pure graph-centrality
(novels need semantic match for aliases / pronouns / translation variants — the reason KG RAG was
chosen over ATS), and we do **not** add agent-writable core memory (the deterministic `story_state` +
KG extraction pipeline is a more trustworthy source of truth than self-reported writes).

---

## Reconciliation — 2 of the 6 recommendations already shipped this session

| R | Research recommendation | Current status (verified 2026-07-06) |
|---|---|---|
| **R2** | Unconditional hard cap on every tool-result (Cline `buildForApi` — runs every turn, independent of compaction) | **✅ MOSTLY DONE — shipped as T6/D7 this track.** [`tool_result_wire.tool_result_content_capped`](../../services/chat-service/app/services/tool_result_wire.py) caps any single tool result over `settings.tool_result_token_cap` (default **8000**, ON) at the generic dispatch site — and **withholds + returns a self-correcting notice** (model re-calls at a smaller scope), which is *better than* Cline's middle-truncation for a re-requestable dump (no lossy mid-cut). This session also **de-silenced** the trip (WARN log). **Residual (small, optional):** a *cross-turn total-byte* counter (Cline's 6MB transcript ceiling) — D7 is per-item, not sum-of-all-results-this-turn. Fold into R-meter below only if a real multi-tool pileup is observed. |
| **R3** | §13 CI meta-check: parse the Law's §11a checklist, fail build on any item without a proof-bound test | **🟡 PARTIALLY DONE.** [`scripts/context-inspector-checklist-gate.py`](../../scripts/context-inspector-checklist-gate.py) already parses a §11a checklist + fails on unproven boxes + runs the referenced suites, wired to pre-commit + CI — but it is scoped to the **Inspector** spec. **Residual:** generalize/point it at `2026-07-03-context-budget-law.md` §11a (or add a sibling gate) so the *whole Law* checklist is proof-bound, not just the Inspector slice. |

So the six-item set reduces to **four genuinely-new efforts (R1, R4, R5) + one now-unblocked measurement (R6)**, plus the two small residuals above.

---

## The plan — ordered by leverage-per-risk

### M1 — [highest leverage] 1-hop graph expansion + working-scope boost in eager grounding
*(research R1 / audit gap-2 + gap “AW-2”)*

**Problem:** `passages.py` never expands through the graph. Multi-hop relational questions ("where
did the feud between house X and kingdom Y begin", "who is behind the traitor the protagonist
trusts") are exactly where vector-only RAG is weakest — vector finds passages that *name* two
entities but can't connect them if they never co-occur in one short passage.

**Two parts, one edit site (do together — same pipeline point):**

| Part | Work | Files / functions |
|---|---|---|
| **1a. Graph expansion** | After MMR in the `passages.py` pipeline, take the top-K entity/passage hits, run a **1-hop** lookup (a trimmed `find_relations_2hop`, capped to 1 hop) to pull directly-related facts/relations. **Hard caps:** per-anchor degree cap + a few-hundred-token budget (a relation list, NOT the whole subgraph). | `services/knowledge-service/app/context/selectors/passages.py`; `db/neo4j_repos/relations.py` (`find_relations_2hop`) |
| **1b. Working-scope boost** | When `editor_context.book_id/chapter_id` is present (already threaded via ARCH-1 C6), boost the `anchor_score` / lower the hub-penalty of entities in the *currently-open* scene/chapter — the Aider "open-file boosts the entities it references ×50" idea (research `04` §2), i.e. prioritize by **current working scope**, not just recency. | `_HUB_PENALTY`/scoring in `passages.py`; `anchor_score` in `entities.py` |

**Why together:** both answer "what context relates to what I'm *doing right now*, not just to the
*question I typed*" — 1a expands by graph edges, 1b by open-editor scope. One pipeline pass.

**Verify:** an eval on a richly-extracted book (Dracula now qualifies — see M4) comparing
answer-correctness on multi-hop relational questions, baseline vs +expansion, with the
`docs/eval/context-budget/` harness. Guard the token cap (expansion must never blow the grounding
budget) with a unit test on the capped expansion helper. **Impact:** High · **Effort:** Low–Medium
(every piece already exists).

### M2 — [cheap, do early] finish the two research residuals
- **R3 residual:** point the checklist gate at `context-budget-law.md` §11a (generalize the parser or
  add a sibling invocation). Low effort; closes the doc/code-drift class that already bit once
  (Inspector GUI marked "missing" while shipped).
- **R2 residual (optional):** add a per-turn total-tool-byte counter at the `tool_result_wire` funnel
  that WARNs when the *sum* of tool results in a turn crosses a larger ceiling — a defense-in-depth
  complement to the per-item D7 cap. Only if a real pileup is seen; otherwise skip (don't build for a
  hypothetical).

### M3 — pull-mode pilot with the reasoning models we already run
*(research R4 / audit gap-3)*

`retrieval_mode` is hardcoded `"prepend"` ([`config.py:167`](../../services/chat-service/app/config.py));
true `pull`/JIT was deferred to a "future strong-model capability." But the pull-mode tools
(`story_search`, `memory_search`, `kg_graph_query`, `kg_entity_edge_timeline`, …) **already exist**
(T1 Family-B). Pilot with a reasoning model we run today (Qwen 3.5/3.6): prepend only a tiny stub
(glossary badge / one-liner) and let the model pull details via tools on demand. This also turns
`retrieval_mode` from flat config into a real **Planner-owned decision** (the D8 "Planner owns the
SEED" intent the spec set but never implemented). **Verify:** A/B on the same harness used for T5/T2
(token savings + no answer-quality regression). **Impact:** Medium–High (token savings, no new infra)
· **Effort:** Medium (needs an A/B measurement plan, like T5).

### M4 — re-measure T5 (and now M1) on a richly-extracted book
*(research R6 / audit gap-4 — NEWLY UNBLOCKED this session)*

The "T5 saves ~0%" conclusion was measured on **thin** books (sparse KG). The blocker was
`D-EVAL-BOOK` (no book had gone through full extraction *with summaries*). **That is now unblocked:**
the summaries live-smoke this session proved Dracula produces real chapter/part/book summaries end to
end. So: run Dracula (or a larger book) through full extraction, then re-measure T5's intent-gate
savings **and** use the same richly-grounded book as the M1 graph-expansion eval corpus. **Impact:**
Low until measured (it's an opportunity, not a fix) · **Effort:** Low.

### M5 — [research] clarify who answers "big-picture" questions; consider offline theme/faction summaries
*(research R5 / audit gap-2b — GraphRAG community-summary idea)*

Confirm explicitly whether `story_state` / L0–L1 summaries answer "summarize character X's arc so
far" / "the main factions in the book." Likely **no** (`passages.py` is entity/passage-scoped, not
theme-clustered). If confirmed a real gap, consider a light **theme/faction cluster summary** (the
GraphRAG community-summary shape) computed **offline per large extraction run** — never per-turn, so
it never touches the tightly-managed per-turn budget. Run as parallel research; blocks nothing.
**Impact:** Medium (pending confirmation) · **Effort:** Medium–High.

---

## Sequencing

1. **M2** (residuals) — cheap, low-risk, this week; parallel to everything.
2. **M1** (graph expansion + working-scope boost) — highest impact; the headline build.
3. **M4** (re-measure on Dracula) — provides the eval corpus M1 needs to prove itself; do alongside M1.
4. **M3** (pull-mode pilot) — after M1 stabilizes (needs an A/B plan like T2/T5).
5. **M5** (global-query research) — parallel research track, non-blocking.

## Explicitly NOT doing (research `06` §Không nên làm)
- Drop vector RAG for pure PageRank centrality (Aider) — novels need semantic alias/pronoun/
  translation match; take only the *personalization* half (M1b), not "drop vector."
- Agent-writable core memory (MemGPT/Letta `core_memory_append`) — deterministic `story_state` + KG
  extraction is a more reliable structured source of truth.
- Glob-path rule-files / tag-based mention re-org (Continue/Zed) — a code-domain concept with no
  natural novel-entity equivalent.
- Fully reactive/post-hoc token accounting (Zed) — loreweave must decide *before* the call whether to
  pull grounding (T5 gate) + set a task-elastic target (Planner); don't regress to reactive-only.
