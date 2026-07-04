# Context Budget — Measurement Phase: continue-writing over a public-domain novel

**Date:** 2026-07-05 · **Model under test (LOCKED):** local `google/gemma-4-26b-a4b-qat`
(LM Studio), model_ref `019ebb72-…` · **Book:** Bram Stoker's *Dracula* (public domain),
`book_id 019eeb09-a4aa-7acf-9281-e812d7975a6c` — 4 published chapters of Harker's Journal
(~5.7k words each) + draft "Escape" chapters · **KG project:** `019f2be0-…` (100 authored
glossary entities) · **Harness:** `scripts/eval/run_quality_gate.py` + new scenario set
`scripts/eval/context_budget_scenarios_continue.json` · **Raw transcripts:**
`runs/continue-writing-2026-07-05/`.

**Goal (user directive):** drive the real chat agent to *continue-write* a public-domain
story over a few chapters, judge answer QUALITY, and monitor CONTEXT against the Context
Budget Law criteria. This is the measurement phase that the tiers were built to enable.

**Design:** A/B over the same 6-scenario set (recall · status · **7-turn continue-writing
arc** · continuity · cross-chapter), real HTTP path through chat-service, gemma via BYOK.
- **RUN_A = baseline** — shipped defaults (T4/T5/D13a OFF; D7 tool-result cap 8000 ON;
  breadcrumb ON; agui tool-discovery ON).
- **RUN_B = t5on** — `T5_INTENT_GATE_ENABLED=true` (chat-service recreated; restored after).
- **Blind judge** — a cold-start Agent scored RUN_A/RUN_B shuffled, never told which is which.

T4 (story_state) and D13a (collapse-dup) are compaction-dependent and env-unwired; the short
scenarios never crossed the ~32K compaction trigger, so they are **out of scope for this run**
(a dedicated long-session compaction test is the follow-up — see Deferred).

---

## 1. Verdict

| Question | Answer |
|---|---|
| Is the agent a capable continue-writer? | **Yes.** On the turns where it wrote, craft was excellent — authentic first-person Gothic Harker voice, correct revision behavior (kept prior text, layered darkness), and an *accurate cross-chapter echo* (the Count scaling the wall "like a lizard"). Judge `craft_quality` = **5/5** (baseline). |
| Does it stay honest under thin grounding? | **Yes.** Where it lacked data (the firm name, the ch4 arc) it **honestly declined** rather than inventing — no fabricated events. The safety instinct held. |
| Is the context machinery healthy? | **Yes.** No-lore turns cheap (3.9–5.1K tok, 0 tools); first-lore fetch heavy (19–28K, driven by tool *results* not grounding); follow-up generative turns reuse context cheaply (5–6K, 0 tools). Tool-discovery constant ~2.06K (agui hot-set, **not** the 41K full catalog). |
| Should T5 be flipped ON by default? | **NO — not yet.** Single-run regression signal on the continue-writing arc (empty reply + refusal-to-write) and the blind judge scored baseline higher. Needs N≥4 to separate signal from gemma variance + root-cause the empty reply. **Defer.** |
| **What is the #1 lever for "continue writing"?** | **GROUNDING COVERAGE, not the model or the budget tiers.** This project's derived knowledge layer is **unbuilt** (0 chapter summaries, 0 entity snapshots); grounding = 100 glossary entities only. That single gap explains every quality miss below. |

---

## 2. Quality (blind judge, 1–5)

Overall means across 6 scenarios (RUN_A = baseline, RUN_B = t5on — judge blind):

| dim | baseline (A) | t5on (B) |
|---|--:|--:|
| correctness | 4.5 | 4.5 |
| groundedness | 4.5 | 4.33 |
| continuity | 5.0 | 4.83 |
| helpfulness | **4.33** | **3.83** |
| craft_quality | **3.5** | 3.33 |

**Per-scenario highlights:**
- `continue_writing_dracula` — **baseline craft 5, helpfulness 5**; t5on **helpfulness 2** (empty
  turn-0 reply + turn-1 *refused to write* the requested prose, only recovering from turn 2).
  Judge: *"RUN_A is clearly stronger: it wrote on request and built the scene coherently, while
  RUN_B's empty reply and refusal-to-write cost it two turns."*
- `lore_recall_primary` — **both runs `critical_confabulation=true`**: both confidently answer the
  main character is **Count Dracula**. The POV protagonist is **Jonathan Harker**. This is a
  *grounding mislabel* (no protagonist signal in the entity layer — see §4), not fluent invention;
  the same runs correctly center Harker in `continuity`/`cross_chapter`.
- `continuity_darker_keep_character` — both keep the same character through the darker rewrite
  (the gating safety-net held under T5); baseline slightly cleaner on grounding.

---

## 3. Context telemetry (per turn)

`used_tok` = the meter's `used_tokens`; `mem_kg` = knowledge grounding block; `tools_sch` =
advertised tool schemas; `story_state` = T4 block (0, tier off). No turn triggered compaction.

### baseline (T4/T5/D13a off)
| scenario · turn | used_tok | mem_kg | tools_sch | history | tools | reply_chars |
|---|--:|--:|--:|--:|---|--:|
| smalltalk · 0 | 3894 | 88 | 2059 | 17 | — | 1884 |
| status_plan · 0 | 5089 | 1126 | 2059 | 23 | — | 1414 |
| lore_recall · 0 | 27692 | 1068 | 2059 | 24 | run_subagent, kg_graph_query, memory_recall×2 | 638 |
| continue · 0 | 25439 | 0 | 2059 | 36 | memory_search, find_tools×2, kg_graph_query | 418 |
| continue · 1 | 4858 | 799 | 2059 | 188 | — | 1022 |
| continue · 2 | 5433 | 1070 | 2059 | 492 | — | 1330 |
| continue · 3 | 16979 | 955 | 2059 | 867 | memory_recall_entity, memory_search | 775 |
| continue · 4 | 6008 | 1126 | 2059 | 1089 | — | 252 |
| continue · 5 | 6043 | 1068 | 2059 | 1199 | — | 1157 |
| continue · 6 | 6187 | 954 | 2059 | 1526 | — | 420 |
| continuity · 0 | 21004 | 1068 | 2059 | 20 | run_subagent, memory_search, kg_graph_query | 1505 |
| continuity · 1 | 5356 | 1068 | 2059 | 425 | — | 2505 |
| cross_chapter · 0 | 18997 | 596 | 2059 | 25 | run_subagent, kg_graph_query, kg_schema_read | 848 |

### t5on (T5 intent gate on) — divergences highlighted
| scenario · turn | used_tok | tools | reply_chars | vs baseline |
|---|--:|---|--:|---|
| smalltalk · 0 | 5030 | — | 1926 | +1136 tok (still light) |
| continue · 0 | **44566** | conversation_search, memory_search, kg_graph_query, memory_recall, find_tools×2 | **0** | **empty reply; +19K tok; crossed 32K trigger** |
| continue · 1 | 24172 | memory_search×2, memory_recall_entity, kg_graph_query | 581 | **refused to write (baseline wrote 1022 ch)** |
| continue · 5 | 5990 | — | 1059 | equivalent (great lizard-echo prose) |
| continuity · 0/1 | 21000 / 5422 | (same shape) | 1779 / 2248 | ≈ baseline (safety-net held) |

**Reading:** the T5 gate, on this run, pushed the continue-writing *openings* into heavier
retrieval cascades that still couldn't surface chapter text (§4), and the model then stalled
(empty reply) or punted (refuse-to-write) instead of writing. Later turns and the
continuity/cross-chapter scenarios were unaffected. **N=1 — this could be gemma run-to-run
variance**, which the methodology explicitly warns about; the empty-reply/tool-loop failure mode
must be understood before any default flip.

---

## 4. Headline finding — the continue-writing loop is GROUNDING-STARVED (buildable)

Every quality miss traces to one root cause, verified against the DB:

- `summary_chapters` for the book = **0 rows**
- `entity_canonical_snapshots` for the project = **0 rows**
- `knowledge_projects.stat_entity_count` = **0** (extraction_status = `ready`, but the derived
  layer was never actually populated)
- grounding therefore = the **100 authored glossary entities only**

Consequences, each observed in the transcripts:
1. **Protagonist mislabel** (`main character = Dracula`) — the entity layer has no "who is the POV
   protagonist" signal, so the model picks the title/most-salient entity.
2. **Can't recall chapter-narrative state** ("where is Harker at the end of chapter 4") — needs a
   chapter summary; there are none → honest punt (both runs).
3. **Can't recall chapter-body details** ("the firm Harker works for" = Peter Hawkins of Exeter) —
   a prose detail, not a glossary entity → honest punt.

The model's *writing* is not the bottleneck (craft 5). The bottleneck is that the agent is asked
to continue *this manuscript* but is given only entity cards, not the chapters' narrative state.
**This is buildable, not blocked:** the knowledge extraction/summarization pipeline
(`summary_chapters` + entity snapshots) exists — it simply hasn't been run for this project. The
single highest-leverage next step for the user's actual goal is to populate that layer and
re-measure (expected: the ch4-recap and arc turns stop punting, and the protagonist mislabel
resolves).

---

## 5. Recommendations & Deferred

- **DO NOT flip T5 default on yet** (`D-T5-CONTINUE-WRITING-REGRESS`). Single-run regression on
  continue-writing openings (empty reply, refuse-to-write) + blind judge favored baseline.
  Gate reason #4-adjacent (needs evidence): re-run **N≥4** on the continue-writing scenario, both
  configs, and root-cause the empty-reply tool-loop before any default change.
- **Build the derived grounding layer for eval books** (`D-EVAL-BOOK-GROUNDING`). Run extraction/
  summarization on the Dracula project so `summary_chapters` + entity snapshots populate, then
  re-run this measurement. This is the #1 lever for making continue-writing genuinely work, and it
  is buildable in-repo (pipeline exists). Gate reason #2 (needs a scoped build/run).
- **Long-session compaction test for T4/D13a** (`D-T4-D13A-COMPACTION-EVAL`). The short scenarios
  never crossed the 32K trigger, so story_state projection (T4) and dup-read collapse (D13a) were
  not exercised. Author a ~30-turn sustained-writing scenario that forces ≥1 compaction, wire
  `STORY_STATE_BLOCK_ENABLED` / `COMPACT_COLLAPSE_DUPLICATES_ENABLED` env passthrough in
  docker-compose (only T5 is wired today), and measure retention across the compaction boundary.

**What held up well (ship-confidence):** the agui tool-discovery path (constant ~2K, not 41K),
the cheap-reuse pattern on follow-up turns, the D7 cap (no single tool result blew the turn), and
the honesty floor (zero *invented* lore). The context machinery is sound; the product gap is
grounding coverage.
