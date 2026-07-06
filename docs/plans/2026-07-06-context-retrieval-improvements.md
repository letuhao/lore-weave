# Context Retrieval Improvements — plan

> **UPDATE 2026-07-06 (M4 multilingual robustness check — done):** M1a shipped
> (`31eefb2dc`) and was then re-measured on a **second, independent, Vietnamese** corpus
> (`019f1783`, 30 ent / 95 rel / 181 pass) —
> [`docs/eval/context-budget/M4-multilingual-bridge-remeasure-2026-07-06.md`](../eval/context-budget/M4-multilingual-bridge-remeasure-2026-07-06.md).
> Result: the bridge is **cross-lingually safe** (no genuine answer regression) and the
> Dracula "weak-but-positive" GO replicates — BUT shipped M1a was **materially degraded on
> Vietnamese** (junk from `extract_candidates` over prose starved the anchor cap: 1/6 real).
> **Fixed this run** (sentence-junk filter + resolve-then-cap → 2× mechanism yield, 3 unit
> tests). A **2nd multilingual defect (`D-BRIDGE-NAME-FRAGMENT`)** — Sino-Vietnamese names
> fragmented by the shared extractor — is tracked (shared-extractor blast radius). The
> answer-quality *magnitude* is still bounded by one small book + local judge; the genuine
> `D-EVAL-BOOK` (large-book full extraction) remains the follow-on. **M1b/M3 stay gated on
> that measurement, not built speculatively.**
>
> **UPDATE 2 — `D-EVAL-BOOK` CLOSED (2026-07-06):** built a larger, **Chinese** corpus
> (万古神帝, 158 ent / 402 rel, extracted this session) and re-ran the A/B —
> [`docs/eval/context-budget/M4-wangu-largecorpus-2026-07-06.md`](../eval/context-budget/M4-wangu-largecorpus-2026-07-06.md).
> Result: **+19% overall / +17% bridge-class (→2.0) / 0 regressions.** M1a is now sized across
> **three independent corpora / three languages** (EN +14%, VI +36%, ZH +19% overall; bridge-class
> +50/67/17%; **0 of 31 questions regressed anywhere**). Verdict: a **safe, reliably-positive**
> recall aid — modest magnitude, decisive *safety* + cross-lingual consistency. Building the corpus
> surfaced two pipeline fixes (`D-BACKFILL-NO-SCOPE-LIMIT`, committed) + an over-extraction cost
> analysis ([`../plans/2026-07-06-extraction-cost-and-tiering.md`](2026-07-06-extraction-cost-and-tiering.md)).
>
> **UPDATE 3 — M1b SHIPPED (2026-07-06):** the D-EVAL-BOOK measurement gate lifted, so M1b (the
> working-scope boost) was built as its own cross-service slice per edge-case #1. When the editor
> `<Chat>` panel is open on a chapter, chat-service now forwards `current_chapter_id` on the grounding
> request; knowledge-service resolves it to a `chapter_index` from the chapter's own `:Passage` nodes
> (`get_chapter_index_for_source` — owner+project scoped, no extra cross-service hop) and the L3 ranker
> multiplicatively boosts passages **within ±window chapters** of it (linear falloff, `_apply_post_filters`).
> Config `context_working_scope_boost=0.30` / `context_working_scope_window=2` (kill-switch `0.0` skips
> the resolution query entirely; a per-turn Mode-3 tuning constant, not a per-user setting — mirrors M1a).
> Inert on every non-editor turn (reader/glossary chat send no chapter) and when the chapter has no
> ingested passages. Bounded so a materially-more-relevant distant passage still wins (regression guard
> unit-tested). **Verify:** 8 new unit tests (boost math + resolver + client field) green; **live smoke**
> on the wangu corpus — `get_chapter_index_for_source` resolved a real chapter_id→index 11 via Neo4j
> (stale→None), and with the open chapter set the ranking shifted from newest chapters (20/19/18) to the
> in-scope 11/12/13. ai-gateway is a pure body pass-through, so no gateway change.
>
> **UPDATE 4 — M3 pull-mode MEASURED → NO-GO-for-now (2026-07-06):** ran the pull-mode A/B on the wangu
> corpus — [`../eval/context-budget/M3-pullmode-ab-2026-07-06.md`](../eval/context-budget/M3-pullmode-ab-2026-07-06.md).
> Findings: prepend injects **~3636 actual tokens/turn** (55% passages + 30% glossary); JIT-pull saves
> **~59%** (not the ~97% ceiling — the plan turn + a reasoning answer turn that re-reads the stub+pulls
> cost ~1500 tok). Pull-mode WORKS but has hard prerequisites: a **mandatory seed stub** (without a
> ~120-tok glossary badge the planner can't resolve role-referenced queries → pulls nothing; WITH it,
> correct recalls), a **capable tool-caller** (gemma emitted degenerate char-split searches, missed
> 2/12), and the **chat-service streaming tool-loop** (knowledge's `llm_client` doesn't surface
> `tool_calls`). Quality-parity vs prepend is **UNPROVEN** — the cheap standalone prepend baseline
> collapsed to "信息不足" on the raw block (a `ab-baseline-must-model-production` harness artifact; a
> valid A/B needs the real chat answering path). **Decision:** moderate savings + hard prerequisites +
> unproven parity ⇒ don't build pull-mode into `retrieval_mode` now. The measurement surfaced a
> **cheaper lever**: trim the L3 passage-count / glossary budget (direct token win, no tool-calling
> risk) + fix knowledge's `estimate_tokens` CJK over-count (~40%: 5091 est vs 3636 actual — Inspector
> token numbers are inflated for non-Latin books).
>
> **UPDATE 5 — the cheaper lever MEASURED (2026-07-07):**
> [`../eval/context-budget/M3-tokenlever-tuning-2026-07-07.md`](../eval/context-budget/M3-tokenlever-tuning-2026-07-07.md).
> (a) **`estimate_tokens` CJK over-count FIXED** (`e37133d0e`): cl100k_base → o200k_base (GPT-4o /
> modern-local tokenizer). English ~unchanged, CJK drops ~40% to match reality; honest Inspector
> numbers + fair CJK budget. For under-6000 blocks (common) it's pure relabeling. (b) **Passage/glossary
> content trim: measured, NOT justified.** A passage top-K sweep (K∈{10,8,6,4}) on the wangu goldens was
> flat within judge noise, the query mix is mostly SPECIFIC_ENTITY (pool=5, already tight), and the
> persistent 0-scores are **retrieval MISSES** (answer not retrieved), not over-provisioning. Glossary
> is near its 800-tok budget with load-bearing badges. The block is 3636 real tok — under the 6000 cap,
> so no budget pressure. Cutting would risk the M1a/M4 recall gains for no gain. **The real remaining
> lever is retrieval RECALL** (extraction/embedding gaps on the missed queries), not budget trimming.

**Date:** 2026-07-06 · **Branch:** `feat/context-budget-law` · **Status:** M4 measured + answer-quality
A/B run (through a `/review-impl` correction) → **M1a = GO, but a measured one.** Evidence
([`docs/eval/context-budget/M4-graph-anchor-bridge-2026-07-06.md`](../eval/context-budget/M4-graph-anchor-bridge-2026-07-06.md)):
STRONG mechanism legs — (1) 100%-consistent coverage gap; (2) **6/6 natural queries** produce EMPTY
facts-anchors today (L2 graph layer dark when the message names no entity). WEAK-but-positive answer
quality — on a *passage-inclusive* baseline with truncation excluded, **+14% overall / +50%
bridge-class, 0 regressions across every fair run**, but ~1 stable win and a magnitude too
small/noisy (N=15, one small book) to call large. The first "+28%/2× Pareto-safe" headline was
**deflated** by the review (baseline had wrongly omitted passages). GO is justified by the
empty-anchor rescue + zero-regression safety, not a dramatic lift. See "Resolved edge cases" #6.

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

## Resolved edge cases (verified against code 2026-07-06 — supersedes the M1 table below where they conflict)

The original M1 assumed primitives are wired where they aren't. Five corrections, each grounded:

1. **M1b working-scope boost is NOT free assembly — split it out.** `editor_context` lives **only in
   chat-service** (`stream_service.py`/`messages.py`/`frontend_tools.py`); it is **absent from
   knowledge-service** and from the grounding-request contract, and `current_chapter_index` is **not
   populated** by `_safe_l3_passages` today (`full.py:115`). So M1b needs a real cross-service field
   addition (grounding-request DTO + chat-service populating book_id/chapter_id + threading to the
   selector). **M1 splits: M1a (graph expansion) ships alone; M1b becomes its own small cross-service
   slice, sized honestly — not folded into "one pass."**
2. **Use the right primitive.** `find_relations_for_entity` ([`relations.py:611`](../../services/knowledge-service/app/db/neo4j_repos/relations.py))
   is a genuine **1-hop, both-directions, project-scoped, confidence + archived-peer filtered**
   traversal — the correct anchor for M1a. Do **not** "trim `find_relations_2hop`" (that one is
   2-hop, outgoing-only, and *mandates* `hop1_types`).
3. **Anchors + injection site.** `passages.py` returns *passages*, not entities — you cannot graph-
   expand from it. Anchors already exist: `select_l2_facts` resolves entity IDs and `full.py` builds
   `surfaced_entity_ids` (`full.py:798`). **M1a's home is the L2 FACTS path in `full.py`** (expand
   from surfaced entities, inject related facts into the facts block) — NOT "after MMR in
   `passages.py`."
4. **M1a design invariants:** degree-cap per anchor + a few-hundred-token total budget (unit-tested on
   the capped helper); **dedup expanded relations against those `select_l2_facts` already surfaced**;
   degrade to empty on neo4j timeout/failure like `_safe_l3_passages`; run before the final budget
   trim but capped so it can't starve passages; inherit the project-scope + confidence + archived-peer
   filters (`find_relations_for_entity` already applies them).
5. **M4 corpus caveat.** Dracula (6ch/~100 entities) proves the pipeline end-to-end but is thin for a
   multi-hop relational eval; use **万古神帝 (4233ch/308 entities)** as M1's eval corpus and Dracula as
   the smoke.
6. **[DECISIVE — 2026-07-06] The graph traversal M1a proposed already exists in the FACTS selector.**
   `select_l2_facts` ([`facts.py:189`](../../services/knowledge-service/app/context/selectors/facts.py))
   runs **1-hop `find_relations_for_entity` every turn**, plus **2-hop `find_relations_2hop` on
   relational intent** (facts.py:211), plus a **widened 2-hop retry on an empty 1-hop miss**
   (`full.py:733`, P4/R-T4-06). So "retrieval never traverses the graph" is true only for the
   *passage* selector; the *facts* path traverses today. Building "1-hop graph expansion" as originally
   framed would **duplicate facts.py**. The genuine residual is narrower: graph expansion is anchored
   **only on `intent_obj.entities`** (entities the classifier pulled from the message text), NOT on
   entities surfaced by semantic passage retrieval (`l3_passages`) or the salience-ranked glossary
   `entities` set. The real M1a, if justified, is a **"vector-hits-feed-the-graph" anchor bridge** —
   value **unproven**. **Decision: run M4 measurement FIRST** (multi-hop recall AFTER the existing
   facts.py traversal); build the bridge only if the numbers show a real miss. Perf/recall items fix
   when measurement shows pain (CLAUDE.md defer-gate #4 / No-Defer-Drift).

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
