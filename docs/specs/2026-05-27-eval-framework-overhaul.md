# Spec — Eval framework overhaul (anchor + multi-judge + DeepEval orchestration)

**Cycle:** 2026-05-27 (post-cycle-1-negative meta-cycle)
**Size:** XL (~13 files, 8 logic blocks, 1 side effect — Docker rebuild for new deps)
**Driver:** Architectural cycle #1 (multilingual few-shot prompts) reverted on negative VERIFY. Investigation revealed the bespoke eval framework provides no **anchor point** — every cycle's baseline is compared against the prior cycle's number, drift compounds across cycles, and judgments from a single LLM judge have no inter-rater reliability check. The cycle's recall-regression hypothesis (extract vs scoring) is itself unresolvable with the current measurement system. Per the user's principle "đánh giá trước rồi mới build" (evaluate first, then build) — pause prompt cycles to upgrade the measurement system before resuming improvement work.

## Goals

1. **Establish anchor points** — published-benchmark numbers that root our metrics in an external truth signal. CoNLL-2003 NER (entity-only, English news) + DocRED (relation-only, English Wikipedia). Both have decades of established SOTA baselines.
2. **Multi-judge ensemble** — replace single-gemma judging with a 3-judge local ensemble (gemma + huihui-qwen3-30b + huihui-claude-4.7-opus). Compute inter-judge agreement (Fleiss kappa) and majority verdicts. Single-judge bias becomes visible as variance.
3. **DeepEval orchestration** — adopt DeepEval's pytest-native eval framework as a WRAP (not full migration) over our existing custom harness. Get structured per-item logging + G-Eval custom criteria + reproducible run reports without throwing away the current 10-chapter narrative-fiction fixtures.
4. **Re-baseline locked models** — re-judge the existing extraction dumps (claude-4.7-opus, 30B-instruct, 30B-multilang-c1 from cycle 1) with the new ensemble + report variance intervals. Definitively answer: did cycle 1's recall regression reflect extract or scoring?

## Non-goals (out of scope this cycle)

- **WikiNeural multilingual anchor** — VN/CN NER benchmark. Defer; CoNLL+DocRED give English anchoring; multilingual anchor cycle is a separate follow-up.
- **Cloud gold-standard judge** — adding real Anthropic claude-haiku-4-5 BYOK as a 4th judge to ground-truth the local ensemble. Defer until first ensemble run shows meaningful variance worth ground-truthing.
- **Full DeepEval migration** — rewriting all existing tests in DeepEval format. WRAP only; both old + new harnesses runnable side-by-side until DeepEval methodology validates.
- **CI integration** — wiring the new eval into a scheduled GH Actions / Jenkins run. No CI exists; defer.

## Architecture decisions

### D1 — DeepEval as wrap, not full migration

Keep existing `tests/quality/test_extraction_eval.py` + `test_judge_eval.py` as-is. Write a NEW `tests/quality/test_eval_with_deepeval.py` that runs the same extraction pipeline but reports metrics via DeepEval's structured results. Both runnable side-by-side; comparison validates DeepEval gives the same signal before retiring the legacy harness.

**Rationale:** lower-risk; if DeepEval methodology has gaps we don't know about, the legacy harness is still trusted ground.

### D2 — CoNLL-2003 + DocRED via HuggingFace `datasets` library

Download via `from datasets import load_dataset; load_dataset("conll2003", split="test")` + `load_dataset("docred", split="validation")`. Sample 50-100 examples from each test/validation split. Cache in container under `tests/fixtures/anchor_conll2003/` and `tests/fixtures/anchor_docred/`. Versioned by dataset version string.

**Anchor metric:** for CoNLL — run our `extract_entities` on each example's text, convert output to BIO/IOB tags via a coarse name-match (case-sensitive whole-word match against the source text token stream — see Risk 4), score with `seqeval` strict mode. Compare aggregate F1 to RoBERTa-large baseline (~92.4 F1 on CoNLL-2003 test).

For DocRED — run our `extract_relations` on each abstract, convert (subject, predicate, object) triples to unlabeled-F1 format (triple existence, ignoring our predicate-type mapping to DocRED's 96 relation types per Q3 resolution). Compare to a published unlabeled-F1 baseline from DocRED leaderboards (~0.45-0.55 depending on system).

**Floor targets (MED-5 + HIGH-1):** the floors are CALIBRATION + SANITY CHECK, not quality gates. Two-tier:

- **Informational floor (no gate):** CoNLL F1 anywhere in [0.20, 0.50] is normal for a narrative-fiction extractor on news-domain strict spans. DocRED unlabeled-F1 anywhere in [0.15, 0.40] is normal. Document the actual number; do NOT fail the cycle on quality.
- **Sanity floor (HARD gate against false-negative trap):** **CoNLL F1 ≥ 0.10 AND N_extracted ≥ 0.1 × N_gold on average across the CoNLL sample.** Same shape for DocRED. If anchor returns 0 entities (extractor regressed to wasserstein-style empty) the sanity gate fires + cycle does NOT pass acceptance. Floor is intentionally low (10% of gold count) — the goal is to catch "system is completely broken", not to gate quality.

### D3 — Multi-judge ensemble: sequential, local, 3 models

Three judge models, identified by UUID (canonical) — names are for prose only (COSMETIC-14):

| Slot | UUID (canonical identifier) | Human name (prose only) |
|---|---|---|
| Judge A | `019dc3df-58f3-7170-bb48-f1f0c9bd604c` | gemma-4-26b-a4b (Google family, baseline-default) |
| Judge B | `019e6a20-eeac-7b96-82ee-69a16d8ef68d` | huihui-qwen3-30b-instruct (Alibaba abliterated; pure-instruct, no reasoning) |
| Judge C | `019e5650-eca7-78c2-985d-465aa3bce1ce` | huihui-claude-4.7-opus (Anthropic-style fine-tune; thinking-on) |

Sequential execution: LM Studio swaps via JIT model loading. Each judge runs the full 9-chapter judging pass independently against the same extraction dump. Total wall clock: ~60-90 min for one ensemble run (vs ~20 min single-judge).

**Agreement metrics:**
- Per-item: simple **majority vote** (2/3 agreement → take that verdict; 0 agreement → mark `disputed`)
- Aggregate: **Fleiss' kappa** (κ) for inter-rater reliability. Cutoffs (Landis & Koch 1977): κ < 0.20 → "poor", 0.21-0.40 → "fair", 0.41-0.60 → "moderate", 0.61-0.80 → "substantial", 0.81-1.0 → "almost perfect". Expect κ ≈ 0.50-0.70 for narrative-fiction extraction (sub-substantial but informative).

**Per-judge bias dimensions (formulas locked in D12 below).**

### D4 — Multi-judge implementation: extend `llm_judge.py`

The current `judge_chapter(client, judge_model, ...)` takes ONE judge UUID. Refactor to accept `judge_models: list[str]` and:
- Run each judge sequentially against the full dump
- Persist each judge's raw verdicts in `judge_verdicts_<judge_short_name>.json`
- Compute majority verdict + Fleiss κ + per-judge strictness metric in a NEW `judge_ensemble.py` module
- Emit `judge_ensemble_report.json` per chapter with: majority verdict, vote tally, disputed flag

Existing single-judge call signature stays backward-compatible (defaults to `[gemma_uuid]` if no list given).

### D5 — DeepEval custom metrics for narrative extraction (distinct judge per metric)

DeepEval ships with `GEval` (custom criteria via natural-language description). Define 3 narrative-fiction metrics, each pinned to a DIFFERENT ensemble judge to avoid the circular-judge problem (one model judging in both llm_judge.py AND G-Eval would be 1-judge × 3-paths, not 3-way ensemble):

- `NarrativeEntityCoverage` (judge: **gemma-4-26b-a4b**) — input: chapter text + extracted entities + gold entities. Criteria: "score 0-1 based on how well the extracted entities cover the gold entities; partial credit for paraphrases or canonical alternates of gold entries."
- `RelationFactualGroundedness` (judge: **huihui-qwen3-30b-instruct**) — input: chapter text + extracted relations. Criteria: "score 0-1 for each relation: 1 if the (subject, predicate, object) is unambiguously supported by the chapter text; 0 if it's a hallucination or unsupported inference; partial credit for plausible-but-not-explicit relations."
- `EventActionRecall` (judge: **huihui-claude-4.7-opus**) — input: chapter text + extracted events + gold events. Criteria: "score 0-1 based on how many gold events were captured (under any phrasing); partial credit for over-merged or split events."

DeepEval's `evaluate()` returns a structured report per test case. Each metric's judge runs sequentially (model swap via JIT) so VRAM stays within limits. **The 3-judge ensemble in llm_judge.py is INDEPENDENT of the G-Eval metric judges** — ensemble is for entity-level majority vote on a unified dump; G-Eval metrics are for chapter-level quality scoring under DeepEval orchestration. They produce complementary signals: ensemble gives "how reliable is our P/R" (variance), G-Eval gives "how good is each extraction category" (qualitative).

### D6 — Test file layout

```
services/knowledge-service/tests/quality/
├── eval_harness.py                          (unchanged — legacy rule-based)
├── llm_judge.py                              (MODIFY — accept list[judge_model])
├── judge_ensemble.py                         (NEW — Fleiss κ + majority vote)
├── deepeval_metrics.py                       (NEW — 3 G-Eval metric definitions)
├── anchor_runner.py                          (NEW — CoNLL + DocRED runners)
├── test_extraction_eval.py                   (unchanged — legacy path)
├── test_judge_eval.py                        (MODIFY — accept ensemble mode)
├── test_eval_with_deepeval.py                (NEW — DeepEval wrap)
└── test_anchor_eval.py                       (NEW — CoNLL + DocRED anchors)
```

Fixtures:
```
services/knowledge-service/tests/fixtures/
├── golden_chapters/                          (unchanged — 10 narrative chapters)
├── anchor_conll2003/                         (NEW — 50-100 CoNLL test examples)
└── anchor_docred/                            (NEW — 50-100 DocRED dev examples)
```

### D7 — Re-baseline scope

Three existing dumps to re-judge with ensemble:
- `/tmp/eval_dump_huihui_v2` — claude-4.7-opus baseline (yesterday)
- `/tmp/eval_dump_huihui30b` — 30B baseline (yesterday)
- `/tmp/eval_dump_30b_ml_c1` — cycle 1 negative (today)

Plus: run CoNLL + DocRED anchors on the 30B model (the new default) to establish floor.

Output: one new section in QUALITY_EVAL_BASELINES.md per baseline showing single-judge vs ensemble metrics + Fleiss κ + anchor F1 numbers.

### D8 — Container dependency story

New PyPI deps to install in `services/knowledge-service`:
- `deepeval>=2.0` — eval framework (~50MB)
- `seqeval>=1.2.2` — token-level NER F1 (~1MB)
- `datasets>=2.20` — HuggingFace datasets loader for CoNLL/DocRED (~80MB)
- `krippendorff>=0.7` — alpha agreement metric (in case we add it; backup to Fleiss kappa)

Add to `requirements.txt`. Dockerfile rebuild required → mid-BUILD checkpoint after foundation lands.

## Acceptance gate

- [ ] DeepEval test runs on ≥1 narrative chapter, reports the 3 custom G-Eval metrics (each from its DESIGNATED judge per D5 — no circular judging)
- [ ] CoNLL-2003 anchor passes the sanity floor (F1 ≥ 0.10 AND N_extracted ≥ 0.1 × N_gold per sample average) — see D2 floors. Actual F1 documented but not a quality gate.
- [ ] DocRED anchor passes the sanity floor (unlabeled F1 ≥ 0.10 AND triple count ≥ 0.1 × gold-triple count per abstract). Actual F1 documented but not a quality gate.
- [ ] Multi-judge ensemble runs all 3 judges on existing 30B dump; emits Fleiss κ + majority verdicts + the three D12 per-judge bias metrics. **If any judge fails per D11**, that judge's dimension is reported as `unavailable`, NOT silently degraded.
- [ ] Re-baseline of cycle 1's dump applies D9 decision rule (with D9 cross-check honesty re: English-only anchor signal per MED-6) and produces a written conclusion in QUALITY_EVAL_BASELINES.md.
- [ ] QUALITY_EVAL_BASELINES.md has new "Eval framework overhaul" section + re-baseline tables with confidence intervals (per-judge + ensemble).

## D9 — Decision rule for cycle 1's open question (extract vs scoring)

When the ensemble runs on the cycle-1 dump (`/tmp/eval_dump_30b_ml_c1`, R_rule-based=0.343) vs the 30B baseline dump (R_rule-based=0.580):

**Variables (MED-4 disambiguation):**

- `R_macro(dump, judge)` = macro recall across the 9 chapters as scored by `judge`, dump-as-input. Compute per (dump, judge) pair. So we have 6 values: R_macro(baseline, A), R_macro(baseline, B), R_macro(baseline, C), R_macro(cycle1, A), R_macro(cycle1, B), R_macro(cycle1, C).
- `ΔR_judge` = R_macro(baseline, judge) − R_macro(cycle1, judge). One value per judge. Positive ΔR means cycle 1 had LOWER recall (regressed).
- `Direction(judge)` = sign(ΔR_judge). Positive / negative / zero.
- `Magnitude(judge)` = |ΔR_judge|.

**Interpretation procedure:**

1. **All 3 judges' Direction(.) agree AND all Magnitude(.) ≥ 0.10 (10pp)** → confirms a **real regression**. Extract logic genuinely worsened; revert was right.
2. **All 3 judges' Direction(.) agree AND all Magnitude(.) < 0.05 (5pp)** → **scoring was the artifact** (rule-based wrongly punished prompt-style changes; LLM-judge sees roughly the same recall). Cycle 1's revert was over-cautious; can re-attempt with refined examples.
3. **All 3 judges agree on Direction(.) BUT Magnitudes are inconsistent (some <5pp, some >10pp)** → mixed evidence; document each judge's per-chapter ΔR breakdown to find which chapters drove the signal. Cycle's revert is justified but informative for next attempt.
4. **2/3 judges agree on Direction(.) — moderate signal.** The dissenting judge's per-item verdicts get hand-audited for over-strict / over-lenient patterns. Conclusion conditional on which judge dissents (D12 bias metrics inform which to trust).
5. **All 3 judges disagree (no majority on Direction)** OR **Fleiss κ < 0.2 on per-item agreement** → **question unresolvable** with our judges. Cycle 1's revert justified by recall risk regardless; the underlying truth about extract quality needs human or cloud-Claude adjudication. File `D-EVAL-FRAMEWORK-CLOUD-JUDGE` follow-up.

**Anchor cross-check (MED-6 honest scope):** if CoNLL/DocRED scores on the 30B-baseline-prompt AND the cycle-1-prompt both come out (run our extractor on CoNLL with each prompt set, take the F1 deltas), the anchor F1 deltas are an independent corroboration of the ensemble verdict — **but only on English content**. CoNLL is English news; DocRED is English Wikipedia. Cycle 1's biggest losses were on Vietnamese (`son_tinh` R −0.31) and Chinese (`journey_west_zh_ch14` R −0.18). The English anchor gives NO independent signal for those languages.

  - **For English-narrative cycle-1 chapters** (alice, sherlock, pride_prejudice, little_women): anchor cross-check applies; agreement increases confidence, disagreement flags judging-system bias.
  - **For CJK/VN cycle-1 chapters** (journey_west_zh_*, son_tinh, tam_cam): verdict comes from ensemble ALONE; anchor is silent. Document this scope limit explicitly in the QUALITY_EVAL_BASELINES.md re-baseline narrative. Multilingual anchor cycle (WikiNeural) is the proper fix; deferred.

## D11 — Ensemble failure handling (HIGH-2 fix)

When ANY judge of the 3 fails to complete a full 9-chapter pass on a given dump, the ensemble does NOT silent-fallback to a 2-judge majority. Failure modes + handling:

| Failure mode | Detection | Handling |
|---|---|---|
| Judge model fails to JIT-load (LM Studio HTTP 500 on first request) | Catch HTTP 5xx from gateway during the judge's first call | Mark this judge `unavailable`; do NOT retry beyond default gateway transient-retry budget; surface in report as missing dimension |
| Judge returns 0 verdicts for some chapters (wasserstein-style empty content) | `len(verdicts) == 0` for that chapter | Mark this (judge, chapter) pair as `incomplete`; per-item Fleiss κ computed only over items where ALL 3 judges produced a verdict |
| Judge produces verdicts but with all-unjudged outcomes | `verdicts[*].verdict == 'unjudged'` | Same as 0-verdicts case (treat as incomplete) |
| Judge times out mid-chapter (gateway transient-retry exhausted) | `ExtractionError` propagated from judge_chapter | Mark this (judge, chapter) as `failed`; do not contribute to ensemble for that chapter |

**Ensemble report shape** when failures present:

```json
{
  "judges": {"A": "019dc3df-...", "B": "019e6a20-...", "C": "019e5650-..."},
  "judge_status": {"A": "complete", "B": "complete", "C": "incomplete: chapter X had 0 verdicts"},
  "per_chapter_majority": {
    "alice_ch01": {"verdict": "supported", "votes": "3/3 agree", "fleiss_kappa_basis": 7},
    "alice_ch02": {"verdict": "supported", "votes": "2/2 agree (C incomplete)", "fleiss_kappa_basis": 5, "incomplete_judges": ["C"]}
  },
  "global_fleiss_kappa": 0.62,
  "global_kappa_basis": "items where all 3 judges produced verdicts (75% of total)"
}
```

The cycle's acceptance gate REQUIRES the ensemble run completed at least 2/3 judges to a `complete` state. If ≥ 2 judges failed, the ensemble run itself is `incomplete` and the cycle does not pass; the failure surface is investigated before retry.

**Never** silently downgrade to 2-judge majority + report as if it were a 3-judge result.

## D12 — Per-judge bias metrics (MED-7 formulas)

Three bias dimensions computed at the end of each ensemble run, persisted in `judge_ensemble_report.json` per judge:

- **Strictness gap (binary verdict acceptance rate)**:
  `strictness(judge) = (# items judged 'supported' / 'covered') / (# total items the judge produced verdicts on)`
  `strictness_gap(judge) = | strictness(judge) − median(strictness across all judges) |`
  Flag `judge` as outlier if `strictness_gap(judge) > 0.15`. (Strict judges accept fewer items; lenient judges accept more.)

- **Language bias (per-judge acceptance rate split by chapter language)**:
  For each judge, compute `accept_rate_lang(judge, lang)` = acceptance rate on chapters tagged with `lang` ∈ {en, vi, zh}.
  `language_bias(judge) = max_lang(accept_rate_lang) − min_lang(accept_rate_lang)` across the 3 languages.
  Flag `judge` if `language_bias(judge) > 0.15` (judge has > 15pp differential on the same task across languages → suggests language-specific bias).

- **Recall-vs-precision bias (which axis the judge favors)**:
  `precision_accept(judge)` = the judge's acceptance rate on PRECISION-mode verdicts (i.e., "is this extracted item supported by the text?").
  `recall_accept(judge)` = the judge's acceptance rate on RECALL-mode verdicts (i.e., "is this gold item captured?").
  `rp_bias(judge) = precision_accept(judge) − recall_accept(judge)`. Range [-1, +1]; positive means judge prefers to confirm precision; negative means judge confirms recall more easily.
  No "flag" threshold; report the metric for each judge as informational.

When any bias metric flags a judge, the ensemble report includes a 1-line note in the analyst-facing summary (e.g., `"Judge C: language_bias=0.22 — significantly stricter on VN than EN; treat VN majority votes including C as lower-confidence"`).

## D10 — Ensemble re-lock cadence policy

To prevent the "every cycle compares against drift" problem cycle 1 exposed, formalize when ensemble baselining MUST re-run:

- **(a) Every new extractor model registered** — establish ensemble baseline before that model becomes part of any decision.
- **(b) Every cycle that touches prompts / aggregator / scoring code** — re-lock the affected dimension (entity prompts → re-lock entity metrics; aggregator → re-lock all).
- **(c) Every quarter** — drift check; LM Studio versions, judge model updates, or fixture changes can shift numbers without code changes.
- **(d) Before any "ship this configuration to production" decision** — final gate before deployment.

Per-cycle iteration smokes can continue using SINGLE-judge (gemma) for fast feedback; ensemble runs are reserved for the above 4 triggers. Documented to keep the velocity-vs-rigor tradeoff explicit.

## Open questions (DESIGN-phase resolution)

- **Q1: How big a sample from CoNLL/DocRED?** Recommend 100 examples each — large enough to be representative, small enough to fit in ~20-min runs per model. *Resolved: 100 each.*
- **Q2: BIO/IOB tag alignment for CoNLL** — our entity extractor returns `(name, kind)` pairs, not span offsets. CoNLL expects token-level BIO tags. Need a tokenize-and-align pass: split text into tokens (whitespace + punctuation), mark tokens matching an extracted entity name as B-{kind}/I-{kind}, others O. Some loss inevitable but representative. *Resolved: build alignment pass; document precision loss.*
- **Q3: DocRED relation typing** — DocRED has 96 typed relations (e.g., `P26: spouse`, `P39: position held`); our extractor produces ~28 predicates. Need a coarse mapping table from our predicates to closest DocRED relation OR run DocRED with `unlabeled` evaluation (just F1 on triple existence, ignore type). *Resolved: ship unlabeled-F1 first; typed-mapping is a separate cycle.*
- **Q4: Krippendorff vs Fleiss kappa** — Krippendorff handles missing data + ordinal categories better. Fleiss is simpler. *Resolved: Fleiss for the 3-judge binary case (supported/unsupported); use Krippendorff if we add a 4th cloud judge later.*

## Risks

- **Risk 1: DeepEval's G-Eval is itself LLM-judged** → we'd be adding another judge LAYER, not replacing the single-judge problem. Mitigation: DeepEval's G-Eval allows passing a SPECIFIC model UUID — we pass our ensemble's MAJORITY model (or use the same gemma instance our llm_judge.py uses) for consistency. Document this circularity.
- **Risk 2: HuggingFace datasets requires internet on first download** → Docker container may not have network access during run. Mitigation: pre-download at BUILD time + cache the data files in the image; verify by smoke run.
- **Risk 3: DocRED has license issues for redistribution** → can't ship the dataset in the repo. Mitigation: download dynamically + cache locally; don't commit fixture data, only commit a download script + checksums.
- **Risk 4: Tokenizer drift between CoNLL gold spans + our extracted name spans** → token boundaries differ (e.g., "New York" gold span vs our "New York City" extracted entity). seqeval is strict-by-default. Mitigation: use `seqeval` strict mode for the ANCHOR comparison; document that we're measuring "name overlap" not "span exactness".
- **Risk 5: Multi-judge wall clock = ~60-90 min per ensemble run** → too slow for tight iteration loops. Mitigation: ensemble is used for BASELINE LOCK runs, not per-cycle smokes. Per-cycle smoke can still use single-judge (gemma) for fast iteration; ensemble re-runs at major-milestone-only.

## Memory anchors

- `feedback_mock_only_coverage_hides_crossservice_bugs` — validates the "we need real benchmarks" thesis; mock-only would not have surfaced cycle 1's regression
- `feedback_test_input_fields_from_producer_schema` — anchor benchmarks are external-producer schemas; we adapt to them, not them to us
- `feedback_xl_cycle_natural_checkpoint_pattern` — explicit foundation/integration seam; checkpoint after foundation BUILD lands

## What this cycle does NOT prove

- Whether cycle 1's prompt change was good for the actual product use case (chat retrieval). The ensemble's verdict on cycle 1's dump answers "did the extract change recall by judge metric" — but the downstream impact on Mode-3 retrieval quality is a SEPARATE evaluation cycle (would need user-query benchmarks, not just extraction baselines).
- Whether any of the 3 judges is RIGHT. The ensemble surfaces variance; it does not resolve which judge has better fidelity to ground truth. For that we'd need a 4th gold-standard judge (cloud Claude or human) — deferred per scope.
- Whether the extractor is FAST ENOUGH for production scale. This is a quality framework, not a perf framework.
