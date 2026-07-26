# M3 follow-on — the "cheaper token lever" measured (o200k fix + passage/glossary trim)

**Date:** 2026-07-07 · **Branch:** `feat/context-budget-law` · **Corpus:** 万古神帝 (wangu,
`019f37f0`) · **Model:** Gemma 4 26B A4B QAT (local), $0 · **Harness:** `scratchpad/m3_passage_k.py`.
Follow-on to [`M3-pullmode-ab-2026-07-06.md`](M3-pullmode-ab-2026-07-06.md), which recommended
"trim the L3 passage/glossary budget + fix the CJK `estimate_tokens` over-count" as a cheaper,
lower-risk lever than building pull-mode.

## 1. `estimate_tokens` CJK over-count — FIXED (`e37133d0e`)

`estimate_tokens` used tiktoken **cl100k_base** (GPT-4-turbo / Claude-3.x era), which splits CJK into
~1.6–2.5 tokens/char. Against the models the platform actually serves — GPT-4o (**o200k**), modern
local (gemma/qwen, ~1 tok/CJK-char) — that **over-counts CJK ~40%**: a wangu Mode-3 block the gateway
tokenized at ~3636 tokens was estimated at ~5091. Effects: the Inspector's per-turn numbers were
inflated for non-Latin books, and the budget enforcer (which compares this estimate to
`mode3_token_budget=6000`) trimmed CJK books to a **smaller REAL budget than Latin ones**.

**Fix:** swap to **o200k_base** (fallback chain o200k → cl100k → len/4). English ~unchanged
(o200k ≈ cl100k for Latin); CJK drops ~40% to match reality. For blocks already under 6000 (the
common case, incl. wangu) this is **pure relabeling — no content/cost change**; for over-budget CJK
blocks it grants the full real 6000 budget (fair vs Latin). 64 tests green.

## 2. Passage top-N trim — MEASURED, NOT JUSTIFIED

Swept passage top-K ∈ {10, 8, 6, 4} on 12 wangu goldens (production selectors: `select_l2_facts` +
`select_l3_passages`, answered with the facts+passage-list path that scored 1.7–2.0 in the M1a/M4
A/B — **not** the raw-block path that collapses):

| K | quality avg | score 2 / 1 / 0 |
|---|---|---|
| 10 | 1.25 | 7 / 1 / 4 |
| 8 | 1.00 | 6 / 0 / 6 |
| 6 | 0.92 | 5 / 1 / 6 |
| 4 | 1.08 | 6 / 1 / 5 |

**Non-monotonic within judge noise** — K4 (1.08) ≈ K10 (1.25). Two reasons cutting top-N isn't
supported:
- **The query mix is mostly `SPECIFIC_ENTITY` → pool = 5**, not 10 (only 1/12 questions hit the
  GENERAL/RELATIONAL top-N=10). So K10/K8/K6 are *identical* to K5 for 11/12 — there's nothing to
  trim on the dominant query type; top-N=5 is already tight.
- **The persistent 0-scores are retrieval MISSES, not over-provisioning.** 功法 / 林泞姗 / 九王子
  score 0 at *every* K including 10 — the answer isn't in the retrieved passages at all. Cutting
  passages can't help these; adding can't either. (These are extraction/embedding-recall gaps, a
  different track from budget.)

Passages also render **full-length** (`full.py:477`, no truncation). Truncating each chunk is a
quality risk (answer position within a chunk is unknown) with **no measured win** — the failures are
misses, not over-inclusion.

## 3. Glossary trim — NOT JUSTIFIED

The glossary selector budget is `max_tokens=800` (`glossary.py:234`); the rendered block measured
~1516 cl100k ≈ **~900 o200k** — roughly *at* its configured budget, not wildly over. And the glossary
badges are **load-bearing**: M3 showed the pull planner *needs* the entity-name list to resolve
role-referenced queries, and the reader/writer needs the name→alias mappings. Cutting the glossary is
a real quality risk with no budget pressure to justify it (blocks are under the 6000 cap).

## Verdict

The "cheaper token lever" resolved almost entirely to the **accounting fix** (o200k), which is the
honest, safe win — shipped. An **aggressive content trim (passage count/length or glossary budget) is
NOT supported by measurement**: passages are intent-tuned and tight (SPECIFIC_ENTITY=5), their
failures are retrieval misses rather than over-inclusion, and the glossary is near-budget with
load-bearing badges. Cutting any of them would risk the measured M1a/M4 recall gains for **no budget
pressure** (the wangu block is 3636 real tokens, well under the 6000 cap) — the measure-before-tune
gate correctly says *don't cut*.

**The real next lever is retrieval RECALL, not budget:** 3–4/12 goldens fail at every K because the
answer isn't retrieved (extraction/embedding-recall gaps), not because the budget is wrong. That —
not trimming — is where answer quality is actually left on the table.
