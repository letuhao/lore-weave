# M3 — pull-mode A/B (prepend vs JIT-pull) on the wangu corpus

**Date:** 2026-07-06 · **Branch:** `feat/context-budget-law` ·
**Corpus:** 万古神帝 (project `019f37f0`, 158 ent / 402 rel / 58 pass) ·
**Model (answerer + planner + judge):** Gemma 4 26B A4B QAT (local, `019ebb6e`), $0 ·
**Harness:** `scratchpad/m3_pull_ab.py` (+ `m3_prepend_cost.py`, `m3_toolcall_probe.py`).
**Plan:** [`../../plans/2026-07-06-context-retrieval-improvements.md`](../../plans/2026-07-06-context-retrieval-improvements.md) M3.

## The question

`retrieval_mode` is a hardcoded label `"prepend"` (`chat-service/app/config.py:165`) that gates
NO behavior today — it only stamps the Inspector frame. M3 asks: is prepend wasting tokens, and
would JIT **pull** (prepend a tiny stub, let the model pull grounding via the existing
`memory_search`/`memory_recall_entity`/`story_search` tools) save tokens without hurting answers?

## Method

12 golden questions (8 role-referenced "bridge" + 4 named "control"), same set as the M1a/M4 A/B.
- **PREPEND arm:** the real `/internal/context/build` grounding block (grounding=ON) → answer.
- **PULL arm:** a 124-char glossary-name **stub seed** → a JSON "planner" turn (model names what to
  `recall`/`search`) → execute via the REAL repos (`find_entities_by_name`+`get_entity_with_relations`,
  `find_passages_by_vector`) → answer from stub+pulled context only.
- Token cost = the gateway's own `usage.input_tokens` per LLM call (pull = plan + answer turns).
- Answerer uses a length-retry (reasoning model burns tokens on `reasoning_content` first).

## Results (n=12)

| Metric | Prepend | Pull |
|---|---|---|
| Prompt tokens / turn (avg, gateway count) | **3636** | **1501** (plan 224 + answer 1277) |
| Token savings | — | **58.7%** |
| Judge quality (0–2 avg) | **0.3 ⚠️ (broken baseline — see below)** | 1.0 |

Per-turn token cost was also measured directly (`m3_prepend_cost.py`): prepend = **avg 3636 actual
tokens** (min 3162, max 4087), 55% passages + 30% glossary. (knowledge-service's own
`estimate_tokens` reported **5091** for the same blocks — it **over-counts CJK by ~40%**; the
Inspector's per-turn token numbers are inflated for CJK books. Separate observability bug.)

## The quality comparison is INCONCLUSIVE — the prepend baseline is a harness artifact

**Do not read "pull 1.0 > prepend 0.3" as "pull beats prepend."** The standalone prepend answerer
collapsed to `信息不足。` ("insufficient information") on nearly every question **even though the
answer was in the corpus** — the PULL arm, drawing from the *same* graph, answered them correctly
(林妃 / 黄极境 / 神武印记 / 秦雅 / 聚气丹 / 林家+星辉宝剑). Feeding the raw rendered `<memory>` XML
block to a terse reasoning answerer over-triggers its conservative "insufficient info" response. This
is the `ab-baseline-must-model-production` trap: production answers this block inside chat-service's
full streaming loop with the real system prompt, not a bespoke terse answerer. **A valid quality A/B
requires chat-service's real answering path**, which this harness does not exercise.

So the quality question is **unresolved**. What IS robust:

## Robust findings

1. **Token savings are real but MODERATE (~59%), not the ~97% ceiling.** The naive ceiling (stub ≈
   120 tok vs 3636 prepend) ignores that pull pays a **plan turn** + a **reasoning answer turn that
   re-reads the stub + pulled snippets** (answer alone = 1277 tok avg). Net ≈ 2.4× reduction/turn —
   meaningful, not dramatic.
2. **A seed stub is MANDATORY for pull-mode.** First run (NO stub) → the planner emitted
   `{recall:[],search:[]}` for every role-referenced question (it can't resolve "被重生的主角" →
   张若尘 without a name anchor) → pull produced nothing. Adding a **124-char entity-name badge**
   flipped the planner to correct recalls (张若尘 / 神武印记 / 云武郡王 …). This validates and
   quantifies M3's "prepend a tiny stub" design: the stub is the *enabler*, not an optimization.
   (It's also the same role-referenced gap M1a's passage→graph bridge closes in prepend mode.)
3. **Planner quality is model-gated.** gemma-26b emitted degenerate char-split searches
   (`['张','若','尘']`) and still missed 2/12 (the 功法 question). A stronger tool-caller plans
   better; pull-mode viability scales with model capability.
4. **Native tool-calls are NOT surfaced by knowledge-service's `llm_client`.** gemma correctly
   returns `finish_reason=tool_calls` with sound reasoning, but `job.result.messages[].tool_calls`
   is `null` — only chat-service's streaming path parses tool_calls. Real pull-mode must run through
   chat-service's tool loop, not a bespoke knowledge path.
5. **Pull can over-include.** Pulled relation lists carried noise (e.g. 秦雅 answer hallucinated an
   extra 墨翰林; 云武郡王's sons over-listed) — the graph's fuzzier edges reach the answer unfiltered.

## Verdict — DON'T build pull-mode into `retrieval_mode` yet

Pull-mode is a **real but moderate** token lever (~59%/turn) with **hard prerequisites**: a mandatory
seed stub, a capable tool-calling model, and the chat-service streaming tool-loop — and its
**quality-parity with prepend is unproven** (the cheap baseline couldn't be trusted). Per the
No-Defer-Drift gate (build a perf item when measurement shows a *clear* win), the win here is moderate
and the risk is real, so pull-mode does not clear the bar for a build now.

**Cheaper, safer lever the measurement surfaced:** the prepend block is **55% passages (2774 tok) +
30% glossary (1516 tok)** every grounded turn. **Trimming the L3 passage count / glossary budget is a
direct, low-risk token win** with no tool-calling dependency or quality-parity question — a better
next step than pull-mode. Also fix the CJK `estimate_tokens` over-count (~40%) so the Inspector's
per-turn numbers are honest for non-Latin books.

**If pull-mode is revisited:** do it in chat-service (real tool-loop), with the mandatory stub seed,
gated on a strong tool-calling model, and A/B'd through the real answering path — not a bespoke
harness.
