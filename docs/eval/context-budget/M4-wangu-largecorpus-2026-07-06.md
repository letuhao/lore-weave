# M4 / D-EVAL-BOOK — M1a bridge on a larger, Chinese corpus (万古神帝)

**Date:** 2026-07-06 · **Branch:** `feat/context-budget-law` ·
**Corpus:** 万古神帝 (project `019f37f0`, book `019efae6`, owner `019d4966`) —
**158 entities / 402 relations / 58 passages**, extracted THIS session (chapters 1–20).
**Answerer + judge:** Gemma 4 26B A4B QAT (local, `019ebb6e`), $0.
**Closes:** `D-EVAL-BOOK` — the "size the lift on a larger book" follow-on from
[`M4-multilingual-bridge-remeasure-2026-07-06.md`](M4-multilingual-bridge-remeasure-2026-07-06.md).

---

## Why this run

The Vietnamese re-measure decisively sized M1a but on a **small** graph (30 entities, N≈12).
`D-EVAL-BOOK` asked for a **larger** corpus. Building it required the whole extraction pipeline
(project → embedding → benchmark → scoped extraction) and surfaced/fixed `D-BACKFILL-NO-SCOPE-LIMIT`
+ an extraction-stall diagnosis (both in the sibling doc's appendices) before this A/B could run.
The result is a genuinely larger graph in a **third language (Chinese)** — 5× the Vietnamese entity
count — that also exercises the **CJK path** of `extract_candidates` (`split_cjk_run`).

## Method

Identical to the Vietnamese A/B (shipped `select_l2_facts` baseline + shipped
`expand_facts_from_passages` bridge; passages in BOTH arms; only arm-difference = the bridge's
relations; truncated-answer rows excluded). 12 golden questions grounded in the live relation graph
(protagonist 张若尘, mother 林妃, princes 八王子/九王子, realm 黄极境, manual 《九天明帝经》…): 8
role-referenced "bridge-sensitive" + 4 named "control". Harness: `scratchpad/wangu_ab.py`.

## Result

| Class | scored/total | mean base | mean +bridge | better / worse |
|---|---|---|---|---|
| Overall | 11/12 | 1.455 | **1.727 (+19%)** | 2 / **0** |
| Bridge-sensitive | 7/8 | 1.714 | **2.000 (+17%)** | 1 / **0** |
| Control | 4/4 | 1.000 | 1.250 (+25%) | 1 / **0** |

- **Zero regressions** in every class.
- **100% bridge-fact coverage** (12/12 queries got bridge facts; avg **11.08** new facts/query) — with
  both multilingual fixes deployed (`D-BRIDGE-NAME-FRAGMENT` + the cap/resolve-then-cap fix), the
  bridge fires richly on Chinese.
- Two clean rescues: *"林泞姗 belongs to which family, what weapon?"* base=0→bridge=2, and *"张若尘's
  father?"* base=0→bridge=1.
- `queries_empty_anchor = 0`: like Vietnamese, the intent classifier over-extracts phrase fragments as
  "anchors" on CJK (e.g. the whole clause `云武郡王有哪几个儿子` as one anchor), so base is rarely fully
  starved — yet the bridge still lifts the mean and never harms.

## Verdict — M1a is now sized across THREE independent corpora / THREE languages

| Corpus | Lang | Size (ent) | Overall lift | Bridge-class lift | Regressions |
|---|---|---|---|---|---|
| Dracula | EN | 64 | +14% | +50% | 0 |
| Vietnamese xianxia | VI | 30 | +36% | +67% | 0 |
| **万古神帝** | **ZH** | **158** | **+19%** | **+17% (→2.0)** | **0** |

**The lift is modest-but-consistent (+14–36% overall) and NEVER negative** across English, Vietnamese,
and Chinese, and across 30–158-entity graphs. The magnitude question `D-EVAL-BOOK` raised is answered:
M1a is a **safe, reliably-positive** recall aid — keep it ON (default). It is not a dramatic lift on any
single corpus, but its *safety* (0/31 questions regressed across all three books) and *cross-lingual
consistency* are the decisive properties.

## Caveats (unchanged)

- Local judge = answerer (gemma-26b) — no independent judge reliably servable (LM Studio model-thrash);
  one row excluded for judge truncation. N per corpus is modest.
- The bridge's value concentrates on **role-referenced** questions (the class it was built for); named
  queries mostly already work from message anchoring.

## Cost note (see [`../../plans/2026-07-06-extraction-cost-and-tiering.md`](../../plans/2026-07-06-extraction-cost-and-tiering.md))

Building this 20-chapter corpus cost ~28 LLM calls/chapter (4 extraction passes × ~7 chunks) ≈ 84K
tok/chapter — the "are we over-extracting?" analysis this run also produced. The A/B corpus is real
and reusable, but the extraction economics are the bigger follow-on.
