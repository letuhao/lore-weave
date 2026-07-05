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
| Should T5 be flipped ON by default? | **NO — not yet, but the case changed (see §6).** The Round-1 regression was **grounding-induced**: after populating the KG (§6), grounded T5 ≈ grounded baseline (helpfulness 4.5 = 4.5; the empty-reply + refuse-to-write both resolved). Still N=1 per config + a transient "project not found" blip to understand → defer the flip, but re-run N≥4 **on the grounded project** as a clean comparison, not a regression-chase. |
| **What is the #1 lever for "continue writing"?** | **GROUNDING COVERAGE, not the model or the budget tiers** — CONFIRMED by the §6 re-measure. Populating the KG fixed the arc-recall punt + the continue-writing stalls. Two residual gaps are now concrete + buildable: chapter **summaries** (`D-KG-SUMMARIES-TARGET-NOOP` — "where is X at chapter N") and a protagonist **salience** signal (`D-KG-PROTAGONIST-SALIENCE` — "who is the main character"). Neither is model/budget-limited. |

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

---

## 6. ROUND 2 — grounded re-measure (2026-07-05, same day)

**What changed:** to test whether the punts and the T5 regression were grounding-induced, I ran
the knowledge extraction pipeline on the Dracula project (`POST …/extraction/start`, scope
`chapters` [1,4], gemma llm + bge-m3 embedding — the benchmark-passed model; explicit refs, so no
reliance on the empty `user_default_models`). Job `019f2f46` completed 4/4 for **$0.016**,
populating the KG in **Neo4j: 63 Entities (incl. Jonathan Harker, Mina, Count Dracula), 114
Events, 12 Facts**. *(Note: my first "0 rows" check hit the wrong surface — Postgres
`entity_canonical_snapshots`, a separate canonicalization cache; extraction writes the graph. The
[[silent-success-is-a-bug-not-environment]] pattern: verify the measurement surface.)* Then I
re-ran the SAME A/B (`baseline_grounded` / `t5on_grounded`), blind-judged.

### 6.1 The T5 regression was GROUNDING-INDUCED — it disappears with adequate grounding

`continue_writing` per-turn (tok/reply-chars), all four runs:

| turn | baseline | t5on | **baseline_grounded** | **t5on_grounded** |
|---|---|---|---|---|
| 0 | 25439/418 | 44566/**0** | 50432/557 | 39655/**723** |
| 1 | 4858/1022 | 24172/**581** (refused) | 4900/1036 | 4938/**924** (wrote) |
| 2 | 5433/1330 | 5240/1420 | 5477/1246 | 5510/1419 |
| 5 | 6043/1157 | 5990/1059 | 6172/1146 | 6315/1252 |

T5-on's two failures — the **empty turn-0 reply** (0 ch) and the **refuse-to-write turn-1** (581 ch
"paste the manuscript") — **both resolve under grounding**: turn-0 becomes a 723-ch honest punt,
turn-1 becomes 924 ch of strong Gothic prose. The residual t0 punt now carries a telling cause
(*"the knowledge graph … showing as 'project not found' when I query directly"* — a transient KG
lookup blip, not the systematic stall).

**Blind judge, grounded runs** (RUN_A=baseline_grounded, RUN_B=t5on_grounded, judge blind):

| dim | baseline_grounded | t5on_grounded | (ungrounded gap was) |
|---|--:|--:|---|
| helpfulness | **4.5** | **4.5** | 4.33 vs 3.83 — **closed** |
| craft_quality | 3.17 | **3.33** | 3.5 vs 3.33 |
| correctness | 4.5 | 4.5 | tie |
| continuity | 5.0 | 5.0 | tie |

Judge verdict: *"near-equivalent … RUN_B [t5on] holding a slight edge on prose craft and lore
precision."* **So the answer to "was T5 worse because of the grounding bug?" is: largely YES.**
The ungrounded T5 regression was an artifact of thin grounding (T5 routed the openings as lore
turns → heavier retrieval that found nothing → stall/refuse). With the KG populated, **T5 ≈
baseline** (even marginally better on craft). This does NOT yet clear T5 for a default flip — still
N=1 per config, and the transient "project not found" blip needs understanding — but it removes the
headline regression and re-frames the T5 N≥4 re-run as a clean comparison rather than a
regression-chase.

### 6.2 What grounding fixed, and what it did NOT (two deeper findings)

**Fixed by the KG facts/events:**
- `cross_chapter_change` — punt → a genuine grounded arc (**Traveler → Prisoner → Hunter**, 1363
  ch), drawn from the extracted facts. The clearest grounding win.
- The continue-writing openings stopped stalling (above).

**NOT fixed — two distinct, deeper gaps:**
1. **Protagonist mislabel PERSISTS** (`main character = Count Dracula`, still a shared
   `critical_confabulation` in both grounded runs) even though **Jonathan Harker is now an
   entity**. This is a **SALIENCE problem, not a coverage problem** — the KG has no POV/protagonist
   signal, and Dracula is the most-connected entity (title + most events), so he wins "main
   character" by centrality. Directly motivates the salience substrate work ([[constellation-wiring-ceiling-crud-guis]],
   Track 4 entity-access telemetry). **New row: `D-KG-PROTAGONIST-SALIENCE`.**
2. **"Where is Harker at the end of chapter 4" STILL punts**, because **chapter summaries were
   never generated** — `summary_chapters` / `summary_books` are **still 0** after extraction, and
   there are no `Summary` nodes. The extraction job's `summaries` *target* did **not** populate the
   per-chapter narrative recap (it's produced by a separate `summary_processor`/`summary_enqueue`
   job, or the target silently no-op'd). KG facts answer *thematic/arc* questions; a chapter
   *summary* is what answers *"where is X at chapter N"*. **New row:
   `D-KG-SUMMARIES-TARGET-NOOP`** — investigate why the `summaries` extraction target produced 0
   `summary_chapters`, then re-measure the ch-recap turn once summaries exist.

### 6.3 Cost note (grounding is not free)

Richer grounding made the opening lore turn **search harder**: `continue_writing` t0 rose to
**50,432 tok** (baseline_grounded) — **crossing the 32K compaction trigger** for the first time in
this whole exercise. So the grounded continue-writing arc is the scenario that would finally
exercise T4/D13a — reinforcing `D-T4-D13A-COMPACTION-EVAL` (now with a concrete trigger: a grounded
continue-writing opening).

### 6.4 Round-2 verdict

- **T5 default flip:** still deferred, but the case changed — the regression was grounding-induced,
  not intrinsic. The N≥4 re-run should be done **on the grounded project** (a fair comparison).
- **#1 lever for continue-writing quality** is now split into two concrete, buildable pieces:
  chapter **summaries** (`D-KG-SUMMARIES-TARGET-NOOP` — the "where is X now" recall) and a
  protagonist/**salience** signal (`D-KG-PROTAGONIST-SALIENCE` — the "who is the main character"
  answer). Neither is a model or budget-tier problem.

**Grounded run artifacts:** `runs/continue-writing-2026-07-05/{baseline,t5on}_grounded.transcript.jsonl`.

---

## 7. ROUND 3 — tool-surface bug hunt: why the agent can't reach the manuscript (2026-07-05)

The residual punts ("where is X at chapter N", "the firm name") led to the question: **can the
agent reach the raw chapter TEXT at all** when the derived layers are thin? Traced against code +
live MCP probes through the real ai-gateway federation:

### 7.1 CONFIRMED BUG (fixed) — `story_search` was silently dropped from federation
`story_search` (the universal manuscript find — **`mode=exact` is a lexical/keyword search that
needs NO embeddings/KG**, plus semantic + block-snippet granularity) is registered in
knowledge-service's MCP server, but the **ai-gateway C-GW prefix gate dropped it**: knowledge's
allowed prefixes were `[memory_, kg_]`, and `story_search` matches neither. Direct proof from the
gateway log, every catalog refresh:
```
dropping tool 'story_search' from provider 'knowledge': name does not match any allowed prefix [memory_, kg_]
```
So the agent's catalog had **175 tools with no manuscript-search tool** — it literally could not
search the book text, so it fell back to `memory_search` (semantic, empty — see §7.3) and punted.
**Fix:** add `story_` to knowledge's `EXTRA_PREFIX_MAP` (the same mechanism `kg_` uses for
knowledge's second namespace). **Verified:** catalog 175→176, `story_search` present, and
`story_search mode=exact "Hawkins"` now returns the **raw chapter prose** — *"I handed to him the
sealed letter which Mr. Hawkins had entrusted to me"* (Ch II), `matchType: lexical`, zero
embeddings. This is the keyword-search fallback that works on ANY book (no glossary/KG/embeddings
required). Files: `services/ai-gateway/src/config/config.ts` (+ `catalog.spec.ts`/`providers.spec.ts`
regression tests pinning that `story_search` survives).

### 7.2 Discovery gap (mitigated) — a hot model never *found* `story_search`
Even federated, the agent didn't use it: `find_tools` ranks `story_search` 7th/misses it (the
token-overlap scorer weights name-match == description-match, so composition tools whose
descriptions mention "story"/"search" tie and win). **Mitigation:** hot-seed the `story` domain on
book-scoped + studio surfaces (`_BOOK_SCOPED_HOT_DOMAINS`/`_STUDIO_HOT_DOMAINS` in
`tool_discovery.py`) — the SAME lesson the code already recorded for `composition_*` ("a local
model spun for minutes … never discovered the family it was standing on"). Now `story_search` is
advertised on pass 0 of every book turn (unit-proven). Files: `services/chat-service/app/services/
tool_discovery.py` (+ `test_tool_discovery.py`).

### 7.3 STILL OPEN (deeper, not a wiring bug) — two residual causes of the punt
After both fixes, a live re-probe shows the agent **still prefers `memory_search`** (it even called
it 10× in one turn) and still punts on the firm name. Root causes, both beyond the tool-surface
wiring:
1. **`memory_search` has no chapter data** — chapter **passages are not ingested** (0 Passage nodes
   in Neo4j, no passage tables populated). `memory_search`'s semantic leg searches embedded
   passages; with none, it returns only glossary/KG memory, so chapter-BODY details (the firm name)
   are invisible to it. **`D-KG-PASSAGES-NOT-INGESTED`** — extraction wired passage_ingester but
   produced 0 passages for this project; investigate + trigger, then `memory_search` works for
   chapter text.
2. **Model tool-selection** — `memory_search`'s description ("find what is already known about a
   topic, character…") reads as the natural pick for "recall a fact", so gemma chooses it over
   `story_search` even when both are advertised. **`D-AGENT-PREFERS-EMPTY-MEMORY-SEARCH`** — options:
   make `memory_search` fall back to the lexical leg when its semantic result is empty (so the tool
   the agent *does* pick succeeds), and/or sharpen tool descriptions. This is agent-behavior work,
   not wiring.

**Net:** the tool-surface WIRING bug is fixed (the manuscript search is now reachable + works with
zero embeddings), which makes the eval more objective — but the agent won't *reliably* stop punting
on chapter-body recall until (1) passages are ingested so its preferred `memory_search` works, or
(2) `memory_search` degrades to lexical on an empty semantic hit. These are the next levers.

### 7.4 SHIPPED — search-tool unification (engine + surface) + chapter-body read
Plan: `docs/plans/2026-07-05-search-tool-unification.md`. User-approved full unify.
- **Engine-unify (`_handle_memory_search`, knowledge-service):** `memory_search` now runs the SAME
  lexical-inclusive hybrid engine `story_search` uses over the linked book's chapters (needs no
  embeddings), plus its existing semantic passage leg for chat/glossary — merged/deduped. So
  whichever search tool the agent picks is **never empty when the chapter text lexically matches**.
  Verified live: `memory_search "Hawkins"` now returns the chapter snippet ("…the sealed letter
  which Mr. Hawkins had entrusted to me") — it returned 0 before. 13 executor tests green.
- **Chapter-body read (`book_get_chapter`, book-service Go):** opt-in `include_body=true` returns
  the chapter's plain-text prose from `chapter_blocks` (default omits it — the body can be large).
  Verified live: returns 28.6k chars incl. "Hawkins"; absent without the flag. DB test green.
- **Surface:** `story_search` is the hot/canonical find tool (grep); `memory_search` stays
  registered-but-lazy with an accurate, redirecting description; `book_get_chapter include_body` is
  the read (glob/read). Minimal, memorable — the Claude-Code shape.

**Residual reality (the honest limit — NOT a wiring bug).** Re-running continue-writing, gemma
**still punts** on the *semantic* queries ("where is Harker at ch4", "what firm does he work for"),
because: (a) its queries are semantic but only the **lexical** leg has data (no embedded passages),
so "firm Harker works for" doesn't lexically match "Mr. Peter Hawkins"; and (b) gemma does NOT fall
back to `book_get_chapter include_body` to read the chapter — it just punts. So the tools are now
**correct + unified** (a stronger model, or ingested passages, would use them), but the residual
punts trace to `D-KG-PASSAGES-NOT-INGESTED` (semantic index) + weak-model orchestration, not the
tool surface. The eval confound (a dropped/hidden search tool) is **removed** — the measurement now
reflects true agent+tool capability.

### 7.5 SHIPPED — passage ingestion (D-KG-PASSAGES-NOT-INGESTED) → the ch4 punt RESOLVED
Root cause: passages are ingested on the `chapter.published` event (CM3c), but that path **skips
when the project has no embedding config at publish time** — the Dracula KG project was
created/linked to the book AFTER its chapters were published, so **0 passages** were ever ingested,
leaving semantic search empty. Fix: ingested the 4 published chapters' passages via the production
`ingest_chapter_passages` path → **116 `:Passage` nodes, all embedded** (bge-m3, $0 local). Made it
**durable + reproducible** with a new idempotent endpoint
`POST /internal/projects/{id}/backfill-passages` (`internal_backfill.py`, mirrors the sibling
backfills) that enumerates a project's published chapters and (re)ingests their passages; resolves
user + embedding config + book from `knowledge_projects`; skips cleanly on no-book / no-embedding /
no-neo4j. 2 unit tests + live-smoke (200, 4 chapters, idempotent).

**Result — re-run continue-writing (`postpassages`):**
- **t0 "where is Harker at the end of chapter 4" → RESOLVED.** The agent now answers grounded from
  the passages: *"Jonathan is currently a prisoner in Count Dracula's castle in the Carpathians. He
  is confined to his own room … away from the 'awful women' (the three female vampires) … he
  attempted to open his door but found it 'hopelessly fast'."* The blind "paste the manuscript"
  punt is **gone**.
- **t6 "the firm Harker works for" → grounded + honest** (not a blind punt): *"the firm is not
  explicitly mentioned … his profession is a 'banking solicitor'"* — correct, cited from passages;
  the exact "Peter Hawkins" line wasn't in the semantically-retrieved set for that phrasing (a
  retrieval-recall nuance, not a data gap — `story_search mode=exact "Hawkins"` still finds it).
- **Cost:** t0 rose to **~85K tokens** (8 `memory_search` calls pulling passages) — rich retrieval
  is not free; well past the 32K compaction trigger, reinforcing `D-T4-D13A-COMPACTION-EVAL`.

**Net:** with passages ingested, the agent's *own preferred tool* (`memory_search`) now returns
real chapter context and it **stops punting on chapter-narrative recall**. The measurement is now
genuinely objective — search reaches the manuscript both lexically (any book) and semantically
(indexed book). Remaining systemic follow-up: **auto-trigger `backfill-passages`** when a project is
linked to an already-published book (or fold it into the extraction start), so this isn't a manual
step. Weak-model orchestration (won't read a whole chapter to chase a needle) is a model-tier limit,
not a repo gap.
