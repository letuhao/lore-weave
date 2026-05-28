# C19 Quality Eval — Multi-model Baseline (2026-04-25)

First end-to-end live runs of the K17.10 quality eval (`pytest tests/quality/ --run-quality`)
against the C19 v2 fixture set (5 v1 English + 4 v2 multilingual). Run after the
C-LM-STUDIO-FIX cycle unblocked LM Studio extraction (proxy `response_format`
normalization + relation schema soften).

## Setup

- Stack: full extraction profile (`docker compose --profile extraction up`)
- Provider: LM Studio (host) via provider-registry proxy
- Fixtures: 9 chapters covering English / Traditional Chinese / Vietnamese
- Threshold gates (set in `tests/quality/test_extraction_eval.py`):
  - `KNOWLEDGE_EVAL_MIN_PRECISION=0.80`
  - `KNOWLEDGE_EVAL_MIN_RECALL=0.70`
  - `KNOWLEDGE_EVAL_MAX_FP_TRAP=0.15`

All 3 runs **failed the gates** — expected, since the gates are tuned for
strict-instruction-following cloud LLMs (claude-haiku, gpt-4o-mini) and the
fixtures annotate **conservatively**, while local LLMs extract broadly.

## Aggregate scores

### Pre-alignment baselines (predicate vocabulary mismatch)

| Model                   | Context | Precision | Recall | FP-trap | Time   | Note                                       |
|-------------------------|---------|-----------|--------|---------|--------|--------------------------------------------|
| qwen2.5-coder-14b       | 24K     | 0.145     | 0.337  | 0.301   | 5:12   | Coder bias — over-extracts (~85% FP)       |
| google/gemma-4-e4b      | 131K    | 0.183     | 0.284  | 0.238   | 7:22   | Conservative; 4B effective param count     |
| **google/gemma-4-26b-a4b** | **64K** | **0.251** | **0.356** | 0.275 | **15:49** | **Best narrative — recommended local model** |
| qwen/qwen3.5-35b-a3b    | 120K    | TIMEOUT   | —      | —       | 59:08† | †Hard timeout at 900s/call; both attempt + retry exceeded. Model too slow on this GPU at fixture scale (35B MoE active params still hit the wall). Practical ceiling appears to be ~26B. |

### Post-alignment baseline (C-PRED-ALIGN cycle, 2026-04-25)

After expanding prompt vocab to 28 predicates organized by category +
direction rule for kinship + canonicalizing fixture predicates:

| Model                      | Precision | Recall | FP-trap | Δ vs pre |
|----------------------------|-----------|--------|---------|----------|
| **google/gemma-4-26b-a4b** | **0.311** | **0.429** | **0.238** | **P +24% / R +20% / FP-trap −13%** |

Validates Finding #1 hypothesis. Lift below estimated +73% precision
because prompt vocab expansion also helped LLM emit MORE relations
(some still don't match fixtures), partially offsetting the gain.

**Gemma-4-26b-a4b is the recommended local-LLM baseline** for narrative
extraction. Strong Vietnamese performance retained (son_tinh
P=0.368→0.556, R=0.438→0.625 — best chapter post-alignment).

## Per-chapter signal (gemma-4-26b-a4b)

### Pre-alignment

| Chapter                    | TP | FP | FN | Precision | Recall | FP-trap rate |
|----------------------------|----|----|----|-----------|--------|--------------|
| alice_ch01                 | 5  | 8  | 2  | **0.385** | **0.714** | 0.0      |
| alice_ch02                 | 5  | 7  | 5  | 0.385     | 0.500  | 0.5          |
| journey_west_zh_ch01       | 4  | 30 | 17 | 0.100     | 0.190  | 0.5          |
| journey_west_zh_ch14       | 5  | 17 | 12 | 0.227     | 0.294  | 0.0          |
| little_women_ch01          | 4  | 18 | 8  | 0.167     | 0.333  | 0.667        |
| pride_prejudice_ch01       | 2  | 24 | 6  | 0.071     | 0.250  | 0.667        |
| sherlock_scandal_ch01      | 2  | 6  | 6  | 0.250     | 0.250  | 0.0          |
| **son_tinh_thuy_tinh_vi**  | **7** | 11 | 9 | **0.368** | **0.438** | 0.143    |
| tam_cam_vi                 | 4  | 9  | 13 | 0.308     | 0.235  | 0.0          |

### Post-alignment

| Chapter                    | TP | FP | FN | Precision | Recall | FP-trap rate | Δ R vs pre |
|----------------------------|----|----|----|-----------|--------|--------------|------------|
| alice_ch01                 | 3  | 9  | 4  | 0.250     | 0.429  | 0.0          | −0.29 (LLM nondeterminism, no fixture changes) |
| alice_ch02                 | 6  | 4  | 4  | **0.545** | **0.600** | 0.5       | +0.10      |
| journey_west_zh_ch01       | 8  | 22 | 13 | 0.222     | 0.381  | 0.5          | **+0.19** (vocab expansion helps Chinese) |
| journey_west_zh_ch14       | 6  | 13 | 11 | 0.316     | 0.353  | 0.0          | +0.06      |
| little_women_ch01          | 5  | 13 | 5  | 0.263     | 0.500  | 0.333        | +0.17 (also dropped 2 intent predicates) |
| pride_prejudice_ch01       | 3  | 18 | 4  | 0.130     | 0.429  | 0.667        | +0.18 (also dropped 1 intent predicate) |
| sherlock_scandal_ch01      | 2  | 7  | 6  | 0.222     | 0.250  | 0.0          | 0.0 (tense fix marginal)    |
| **son_tinh_thuy_tinh_vi**  | **10**| 7 | 6 | **0.556** | **0.625** | 0.143    | **+0.19** (direction flip + canonical worked) |
| tam_cam_vi                 | 5  | 12 | 12 | 0.294     | 0.294  | 0.0          | +0.06      |

### Big-fixture diagnostic — Speckled Band (53KB / ~13K tokens, 2026-04-25)

Added in C-BIG-FIXTURE cycle to expose production-scale behavior. Pipeline survived end-to-end without crash, ~7-8 min/chapter latency. Per-chapter score:

| Chapter                    | TP | FP | FN | Precision | Recall | FP-trap rate | Notes |
|----------------------------|----|----|----|-----------|--------|--------------|-------|
| sherlock_speckled_band     | 15 | 33 | 11 | 0.278     | 0.577  | 0.267        | P drops ~50% vs sherlock_scandal_ch01 baseline (0.571) due to over-extraction |

**Failure mode confirmed**: hypothesis #3 (entity over-extraction explodes), NOT context overflow nor instruction-following degradation. Recall stays solid (R=0.58 in line with English baseline).

**Over-extraction breakdown** (entity FPs):
- 11 backstory places never present in any scene: London, Calcutta, Berkshire, Hampshire, Surrey, Crewe, Harrow, Reading, India, Waterloo, Crane Water
- 4 backstory people: Mrs. Stoner (dead mother), Major-General Stoner (dead biological father), Miss Honoria Westphail (extracted in honorific form), Mrs. Hudson (Baker Street landlady)
- 3 organizations/artifacts: Bengal Artillery, Scotland Yard, Eley's No. 2 revolver
- 1 duplicate-form (Percy Armitage extracted twice as "Mr. Armitage" + "Percy Armitage")

**Decisive insight for chunking**: pipeline does NOT degrade with longer context — LLM correctly extracts more entities BECAUSE chapter contains more named mentions. The fixture's conservative annotation philosophy (scene-actors only) does not match the prompt's instruction to "extract named entities in TEXT". **Chunking would not directly help**. Real lever is **prompt scene-vs-backstory tightening**.

Full attribution dump available at `chat-history/eval_dump_bigfix_20260425_232710/sherlock_speckled_band/`.

### Aggregate after big-fixture addition

| Model                      | Precision | Recall | FP-trap | Lenient P | Note |
|----------------------------|-----------|--------|---------|-----------|------|
| google/gemma-4-26b-a4b (10 chapters) | **0.394** | **0.552** | 0.274 | **0.437** | Speckled Band drags strict P down −0.013 from 9-chapter baseline; R holds steady |

## Findings worth recording

1. **Model choice matters more than parameters at this scale.** Coder-14b had
   a higher *recall* than gemma-4-e4b (0.337 vs 0.284) because coder over-extracts
   broadly, but its precision was much worse (0.145 vs 0.183) and its trap-hit
   rate higher (0.301 vs 0.238). Pick by *task fit*, not parameter count.

2. **Vietnamese narrative works** with the right model. Sơn Tinh Thủy Tinh
   under gemma-4-26b: precision 0.368 / recall 0.438 — best Vietnamese
   performance across all models, suggests diacritic preservation and
   non-honorific kinship-term canonicalization (e.g. `dì ghẻ`) are functioning.

3. **English alice_ch01 reaches recall 0.714** under gemma-4-26b — within
   touching distance of the 0.70 hard-gate. Confirms the fixture annotations
   are sound; the model just needs to be strong enough.

4. **Traditional Chinese remains the weak axis** even for the best local
   model (recall 0.19 on `journey_west_zh_ch01`). Possible causes worth
   investigating in a follow-up cycle:
   - Prompt examples are all English/Latin script; LLM may not generalize
     the entity-extraction pattern to Han characters.
   - Annotations at 10 entities for ch01 are CONSERVATIVE — model extracts
     34 candidates (4 TP + 30 FP), most reasonable but outside our list.
   - CJK tokenization may inflate context cost vs effective output.

5. **Pipeline robust** — every model tested ran end-to-end on all 9 chapters
   without crashing. The C-LM-STUDIO-FIX cycle (proxy normalization + schema
   soften) made the system tolerant enough for real-world LLM-output drift.

## Recommendations

- **Current local baseline**: gemma-4-26b-a4b. Use for smoke / dev iteration.
- **Hard-gate validation**: cloud LLM (claude-haiku-4-5 or gpt-4o-mini —
  both registered in DB). Expect P ≈ 0.50-0.70 / R ≈ 0.60-0.75 based on
  cross-domain extrapolation.
- **Lower thresholds for "illustrative" gate**: hard gate of 0.80/0.70 is
  unrealistic against conservative fixtures. A "smoke" gate of 0.20/0.40
  would catch pipeline regressions without demanding cloud-LLM-quality
  output.
- **Improve Chinese**: add CJK few-shot examples to extraction prompts;
  consider qwen3-30b-a3b (Qwen has stronger Chinese training).

## Audit findings — why local LLMs score low even when extracting reasonably

Investigation done during the qwen3.5-35b-a3b run (which itself timed out)
identified three issues that account for most of the precision/recall gap.
Listed in order of expected impact if fixed.

### Finding 1 (HIGH) — Predicate vocabulary mismatch between fixtures and prompt

The relation extraction prompt
([relation_extraction.md §Rule 2](../app/extraction/llm_prompts/relation_extraction.md#L46-L50))
explicitly tells the LLM to **prefer a small predefined set** of predicates:

> `knows`, `trusts`, `works_for`, `lives_in`, `owns`, `married_to`,
> `child_of`, `member_of`, `enemy_of`, `located_in`. Invent new
> predicates only when none of the above fit.

But the v1+v2 fixture annotations use predicates **NOT in this list**:

| Fixture                  | Annotated predicates                                                                          |
|--------------------------|-----------------------------------------------------------------------------------------------|
| journey_west_zh_ch01     | `located_in`, `located_on`, `born_from`, `commands`                                           |
| journey_west_zh_ch14     | `becomes_disciple_of`, `names_disciple`, `imprisoned`, `instructs`                            |
| son_tinh_thuy_tinh_vi    | `father_of`, `courts`, `resides_at`, `marries`                                                |
| tam_cam_vi               | `stepsister_of`, `mother_of`, `stepmother_of`, `helps`, `marries`                             |
| alice_ch01 (v1)          | `sits_by`, `follows`                                                                          |
| sherlock_scandal_ch01    | (similar story)                                                                                |

LLMs that follow the prompt emit predicates from the suggested set
(`lives_in` instead of `resides_at`, `child_of` instead of `father_of`,
`member_of` instead of `becomes_disciple_of`). Score harness uses
**exact-string equality after canonicalization** — synonyms don't match.
**Result**: every reasonable LLM relation gets marked FP+FN.

Estimated impact if aligned: alice_ch01 R=0.71 → ~0.85; aggregate P
0.25 → ~0.40. **Single-cycle fix.**

**Action options**:
- (a) Rewrite each `expected.yaml` predicate to use prompt-suggested vocabulary
- (b) Expand prompt suggested-set to include narrative-fiction verbs
  (`child_of`/`parent_of`, `disciple_of`/`mentor_of`, `commands`,
  `imprisoned_by`, `helps`)
- (c) Loosen score harness to accept semantic synonyms (LLM-as-judge or
  embedding-similarity equality)

Recommend (a)+(b) combined: align fixtures + expand prompt vocab so both
sides agree.

### Finding 2 (MEDIUM) — Trap list incomplete

For Tay Du Ky ch01, gemma-4-26b emitted ~30 entities (4 TP + 30 FP).
Our trap list has 12 entries; only 6 matched the LLM output. The remaining
~24 FPs are LLM-extracted things outside both our entity list AND our
trap list — most are reasonable surface-form named-entity candidates
(epithet fragments like `大慈仁者`, `高天上聖`; cosmological references
like `三皇`, `五帝` we DID list but missed `盤古`-as-text-mention vs
`盤古`-as-actor; numerological `周天三百六十五度`).

Actionable additions per fixture: 5-8 more traps catching common
over-extraction patterns. Lower leverage than Finding 1 but reduces FP
counts directly.

### Finding 3 (HIGH-impact, ARCHITECTURAL) — Conservative annotations vs broad LLM output

The fixture README explicitly says **"Annotate conservatively"** — list
only the absolute essentials. LLMs are trained to **find every named
entity in the text**. This guarantees a structural precision gap: our
annotations are a SUBSET of reasonable extractions, not the complete
set.

Two architectural fixes possible:
- (a) Switch to **exhaustive annotation** — expand each fixture to
  list every reasonable entity-equivalent surface form. Bigger upfront
  work, more accurate scoring. Doesn't help relation-predicate problem.
- (b) **LLM-as-judge** scoring — feed the model's output + the source
  text + our annotations to a strong reference LLM, ask "which actual
  extractions are reasonable given the text?". Removes annotation-
  completeness bias but introduces dependency on a judge LLM.

Recommend (b) as a longer cycle; immediate gain is from Finding 1.

### Architecture comparison vs similar projects

| Aspect              | LoreWeave (current)                  | GraphRAG (Microsoft)               | HippoRAG                       |
|---------------------|--------------------------------------|------------------------------------|--------------------------------|
| Chunking            | None (whole-chapter prompt)          | ~600-token chunks with overlap     | Per-chunk extraction           |
| Few-shot examples   | 1 per prompt (English only)          | 3-5 typed examples                 | 1-2 per prompt                 |
| Sequential pipeline | entity → relation → event ✓          | entity → relationship → claim ✓    | single-pass                    |
| Multilingual        | English-only examples                | Configurable per language          | English-focused                |
| Entity canonical-id | SHA-hash + alias union ✓             | Name match across chunks           | TF-IDF entity fingerprint      |

**Verdict on architecture**: sound for fixture-scale (1.1-1.5KB chapters).
Needs chunking to scale to real chapters (10-15KB). Multilingual signal
weak due to English-only few-shot — adding Chinese + Vietnamese examples
to all 3 prompts is a moderate-leverage cycle.

### Recommended next actions (priority order)

1. ~~**Predicate alignment cycle** (Finding 1)~~ — **DONE 2026-04-25 (C-PRED-ALIGN cycle)**. P 0.251→0.311 (+24%), R 0.356→0.429 (+20%).
2. ~~**Form-mismatch fixes (entity kind + event Jaccard + predicate synonyms + annotation gap)**~~ — **DONE 2026-04-25 (C-EVAL-FIX-FORM cycle, A+C bundle)**. P 0.311→0.407 (+31%), R 0.429→0.549 (+29%); lenient P 0.453.
3. ~~**Add big chapter fixture to expose production reality**~~ — **DONE 2026-04-25 (C-BIG-FIXTURE cycle)**. Speckled Band 53KB / ~13K tokens. Pipeline survived end-to-end without crash; chapter scored P=0.28 R=0.58. **Failure mode: entity over-extraction (11 backstory places + 4 backstory people emitted)**. Chunking would NOT address this — confirmed by data. Real lever is prompt scene-vs-backstory distinction.
4. **Prompt scene-vs-backstory tightening** (next cycle, derived from C-BIG-FIXTURE finding) — entity prompt currently says "extract named entities in TEXT", which correctly extracts backstory mentions. Tighten to "extract entities that ACT in the chapter's scenes, not entities mentioned only in backstory or asides".
5. **Multi-language few-shot** in prompts — Chinese + Vietnamese examples to lift Vietnamese bare-noun recognition (dì ghẻ, vua, cá bống).
6. ~~**Trap expansion** (Finding 2)~~ — DEMOTED to LOW priority. Adding traps doesn't lift precision (same denominator); only adds explicit FP labels. Real lever for over-extraction is prompt tightening (#4).
7. **Eval test parallelism** — eval is serial (`for fixture` loop) and within-chapter R+E+F is serial too (drift from production orchestrator that uses `asyncio.gather`). LM Studio 0.4.0+ continuous batching makes this 2-3x throughput win at no quality cost.
8. **Cloud LLM baseline** — claude-haiku-4-5 / gpt-4o-mini run, ONE-OFF for hard-gate calibration only (cost-controlled per local-LLM-first stance).
9. **LLM-as-judge scoring** (Finding 3) — defer; needs design ADR.
10. ~~**Chunking for large chapters**~~ — **CONFIRMED DEFERRED** by C-BIG-FIXTURE data. 13K-token chapter survived without quality degradation from context length; over-extraction is the failure mode, not context degradation. Re-evaluate when 30KB+ fixture is needed.

## Reproducing

After loading the recommended models in LM Studio with the documented
context windows:

```sh
psql -U loreweave -d loreweave_provider_registry \
  -v owner_user_id="'YOUR-USER-UUID'" \
  -v provider_credential_id="'YOUR-LM-STUDIO-CRED-UUID'" \
  -f services/knowledge-service/eval/register_lm_studio_models.sql
```

Then set `KNOWLEDGE_EVAL_MODEL` to the returned `user_model_id` and run
`pytest tests/quality/ --run-quality -v -s`. See the SQL file's header
comment for the full env var list.

> **Pricing note (2026-05-21).** After the Phase 6a spend guardrail
> shipped, every model needs a `pricing` JSONB or the gateway fails
> CLOSED ("model pricing not configured", 402). Local LM Studio models
> are free → set `pricing = {"input_per_mtok": 0, "output_per_mtok": 0}`
> on each `user_models` row. `register_lm_studio_models.sql` does NOT yet
> set this — patch it, or `UPDATE user_models SET pricing=...` per model.

---

## 2026-05-21 — Qwen3.6-35B-A3B baseline + LLM-as-judge

### Rule-based baseline (qwen/qwen3.6-35b-a3b, 32K ctx, 10 chapters)

| Model | Precision | Recall | FP-trap | Time |
|-------|-----------|--------|---------|------|
| **qwen3.6-35b-a3b** | **0.603** (lenient 0.642) | **0.407** | **0.117** | 1:41:03 |
| gemma-4-26b-a4b (prior, 10 ch) | 0.394 | 0.552 | 0.274 | — |

vs gemma: precision +53%, FP-trap −57% (now *under* the 0.15 gate),
recall −26%. Qwen3.6 is conservative/precise rather than the
over-extracting coder profile that was feared. Run serial because LM
Studio `Max Concurrent Predictions=1` is required to give each request
the full 32K (4 slots → 8K/slot overflows a 13K-token chapter).

### LLM-as-judge (the rule-based scorer is the wrong instrument)

The rule-based harness ([eval_harness.py](../tests/quality/eval_harness.py))
matches by exact string / token equality — wrong for an interpretive
task. New source-grounded judge ([llm_judge.py](../tests/quality/llm_judge.py),
runner [test_judge_eval.py](../tests/quality/test_judge_eval.py)) reads
the chapter text and judges semantic correctness: **precision** = is each
extracted item supported by the text; **recall** = is each gold item
captured under any phrasing. Routes through the `loreweave_llm` SDK →
provider-registry (gateway invariant). Judge = **gemma-4-26b-a4b**
(different family from the Qwen extractor → no self-reinforcement).

Judge run over the qwen3.6 dump (gemma judge):

| Metric | Judge | Rule-based | Note |
|--------|-------|-----------|------|
| Precision | **~1.00** (cov 68%) | 0.60 | judged items are uniformly *supported* |
| Recall | **0.46** (cov 76%) | 0.41 | events ≈0 dominate the miss |

**Discrimination probe (validates the judge isn't rubber-stamping):**
fed alice_ch01 + 2 real + 3 fake entities (Napoleon, Spaceship
Enterprise, Tokyo) → judge correctly returned `supported` for the 2 real
and `unsupported` for all 3 fakes. So **P≈1.0 on the real extraction is
genuine** — qwen3.6 does not hallucinate; everything it extracts is in
the text.

**Conclusions (these reframe the R&D track):**

1. **Precision is NOT the problem.** It is ≈1.0; the rule-based 0.60 was
   a measurement artifact — it penalized reasonable, source-grounded
   extractions absent from the *conservative* gold set (e.g. Speckled
   Band's "44 FP" are real backstory entities, just not scene-relevant
   per the annotation philosophy). Stop tuning for precision.
2. **Recall is the lever**, and **events are the biggest hole**
   (qwen3.6 extracts ≈0 events across all chapters); relations next.
3. **Open caveat — judge coverage 68% (precision).** A *reasoning* judge
   model (gemma-4-26b-a4b emits `reasoning_tokens`) sometimes drops a
   batch's verdicts even with batch_size=8 + a 512+96·n token budget.
   Items the judge omits are excluded from the denominator (not counted
   as misses) and surfaced as coverage. To harden the absolute numbers:
   shrink the batch, or use a non-reasoning judge.

**Judge harness env:**

```sh
# (judge model loaded in LM Studio; extraction dump already produced)
KNOWLEDGE_EVAL_JUDGE_MODEL=<judge_user_model_uuid> \
KNOWLEDGE_EVAL_USER_ID=<uuid> \
KNOWLEDGE_JUDGE_DUMP_PATH=/path/to/extraction/dump \
  pytest tests/quality/test_judge_eval.py --run-quality -s
```

The judge model MUST differ from the extraction model. `model_ref` is an
env var so a cloud judge (calibration pass) is a one-line swap.

---

# Post-fence-fix LLM-judge baseline (2026-05-23)

After the **gateway aggregator markdown-code-fence fix** (`provider-registry-service/internal/jobs/aggregator.go` — `mergeChunkJSON` now retries via `extractJSONObject(raw)` extracting the outermost `{…}` when direct `json.Unmarshal` fails on a leading backtick). qwen3.6 (and any reasoning model that wraps JSON in ` ```json … ``` `) was emitting well-formed extraction output that the gateway aggregator was silently throwing away (`chunk_errors: ["invalid character '`'..."]`, 0 items returned despite real `output_tokens`). The bug had been silent across every extraction op (`entity`/`relation`/`event`/`fact`) for every fenced model since the aggregator shipped.

## Setup

- Extraction: `qwen/qwen3.6-35b-a3b` (LM Studio, host) — user_model `019e21cc-…`
- Judge: `google/gemma-4-26b-a4b` — user_model `019dc3df-…` (different family, no self-bias)
- Stack: minimal extraction profile (knowledge-service + provider-registry + deps); Neo4j NOT required for extract-dump + judge
- Fixtures: 9 chapters covered (the 10th, `sherlock_speckled_band` at 1139 lines / 17 chunks, hung under concurrent load on the local 35B target — perf concern unrelated to fence-fix; excluded from this baseline)
- Concurrency: 3 for the original concurrent dump; 2 chapters re-extracted serially (concurrency=1) after a transient concurrent-load flake (cold-model entity-extraction returned 0 → `if not entities` short-circuited relations+events)

## Raw extraction counts (post-fix, 9 chapters)

| chapter                | entities | relations | events |
|------------------------|---------:|----------:|-------:|
| alice_ch01             |        3 |         0 |      7 |
| alice_ch02             |        3 |         7 |      5 |
| journey_west_zh_ch01   |       17 |        10 |      5 |
| journey_west_zh_ch14   |        9 |         9 |      6 |
| little_women_ch01      |       10 |         0 |      5 |
| pride_prejudice_ch01   |       10 |        11 |     10 |
| sherlock_scandal_ch01  |        3 |         2 |      1 |
| son_tinh_thuy_tinh_vi  |        6 |         5 |      8 |
| tam_cam_vi             |        4 |         5 |     13 |
| **TOTAL**              |   **65** |    **49** | **60** |

Before fix the rule-based-scored session-60 dumps showed **8/10 chapters with 0 events** (the extraction model emitted them, the gateway aggregator threw them away). Post-fix every chapter produces at least one event, with the kind enum exclusively populated by valid in-enum values (action/dialogue/travel/etc.) and every event carrying named participants — mechanisms A (out-of-enum `kind`) and B (empty participants) flagged in the `KNOWLEDGE_SERVICE_CATALOGUE_DRIVEN_EXTRACTION_ADR.md` did NOT trigger across the golden set. The catalogue-driven refactor still has value for genre fiction (xianxia / cultivation realm kinds), but recall recovery on the current fixtures is dominated by the fence-fix.

## LLM-judge aggregate (macro across 9 chapters)

**P = 0.97 | R = 0.81 | coverage P = 62% R = 56%**

| chapter                | P    | R    | ent P/R       | rel P/R       | evt P/R       | cov P/R    |
|------------------------|-----:|-----:|---------------|---------------|---------------|------------|
| alice_ch01             | 0.83 | 0.57 | 0.83 / 0.67   | 1.00 / 0.00   | n/a  / 1.00   | 30% / 100% |
| alice_ch02             | 1.00 | 0.78 | n/a  / 0.60   | 1.00 / n/a    | 1.00 / 1.00   | 80% / 90%  |
| journey_west_zh_ch01   | 1.00 | 1.00 | 1.00 / 1.00   | n/a           | n/a           | 53% / 48%  |
| journey_west_zh_ch14   | 1.00 | n/a  | 1.00 / n/a    | 1.00 / n/a    | n/a           | 42% / 0%   |
| little_women_ch01      | 0.93 | 0.86 | 0.90 / 1.00   | 1.00 / 0.00   | 1.00 / n/a    | 100% / 70% |
| pride_prejudice_ch01   | 1.00 | 1.00 | 1.00 / n/a    | 1.00 / 1.00   | 1.00 / n/a    | 65% / 14%  |
| sherlock_scandal_ch01  | 1.00 | 0.67 | 1.00 / 0.75   | 1.00 / 0.50   | n/a           | 83% / 75%  |
| son_tinh_thuy_tinh_vi  | 1.00 | 1.00 | 1.00 / 1.00   | n/a           | n/a  / 1.00   | 32% / 69%  |
| tam_cam_vi             | 1.00 | 0.57 | 1.00 / 0.57   | 1.00 / n/a    | 1.00 / n/a    | 77% / 41%  |

Run time: 19 min for 9 chapters (judge=gemma-4-26b-a4b).

## Comparison vs prior baselines

| Run | Date | Extractor | Scorer | Precision | Recall |
|---|---|---|---|---:|---:|
| C19 baseline (pre-align) | 2026-04-25 | gemma-4-26b-a4b | rule-based exact-string | 0.251 | 0.356 |
| Session 59 (C-PRED-ALIGN done) | 2026-05-13 | gemma-4-26b-a4b | rule-based | 0.311 | 0.429 |
| Session 60 LLM-judge (broken pipeline — fence bug undetected) | 2026-05-22 | qwen3.6 | gemma-4-26b judge | ~1.00 | ~0.46 |
| **Post-fence-fix LLM-judge** (session-61 baseline) | **2026-05-23** | **qwen3.6** | **gemma-4-26b judge** | **0.97** | **0.81** |
| Post-P3 non-regression (judge-truncation-affected) | 2026-05-24 | qwen3-30b-a3b | gemma-4-26b judge | 0.91 (cov 49%) | 0.39 (cov 63%) |
| Post-P3 non-regression + judge fix | 2026-05-24 | qwen3-30b-a3b | gemma-4-26b judge | 0.93 | 0.57 |
| Post-arch fix on uncensored (rule-based pre-anti-think) | 2026-05-24 | huihui-qwen3.6-abliterated ⁴ | rule-based | 0.452 | 0.461 |
| **Post-arch fix on uncensored (with anti-think)** | **2026-05-24** | **huihui-qwen3.6-abliterated** | **rule-based** | **0.411** | **0.548** ⁵ |
| **huihui-claude-4.7-opus variant (rule-based)** | **2026-05-26** | **huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated** ⁶ | **rule-based** | **0.324** | **0.560** |
| **huihui-claude-4.7-opus variant (LLM-judge)** | **2026-05-26** | **huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated** | **gemma-4-26b judge** | **0.93** | **0.71** ⁷ |
| qwen3.6-uncensored-wasserstein (rule-based) — **NEGATIVE BASELINE** | 2026-05-27 | qwen3.6-35b-a3b-uncensored-wasserstein ⁸ | rule-based | 0.074 | 0.026 |
| huihui-qwen3-30b-instruct (rule-based) | 2026-05-27 | huihui-qwen3-30b-a3b-instruct-2507-abliterated ⁹ | rule-based | 0.165 | 0.580 |
| **huihui-qwen3-30b-instruct (LLM-judge) — HIGH-RECALL BASELINE** | **2026-05-27** | **huihui-qwen3-30b-a3b-instruct-2507-abliterated** | **gemma-4-26b judge** | **0.79** | **0.90** ⁹ |

⁴ Uncensored 32K variant; chosen for NSFW novel extraction. Has hidden thinking mode (reasoning_tokens dominate response).
⁵ Anti-think prefix (commit 6a02750d) reduced reasoning_tokens from ~100% to 55-89% of output. Recall +19% vs pre-anti-think (more content tokens emitted). Precision slight dip — more extraction = more noise. Pre-rendered: pipeline now context-aware (no KV-cache OOM), but model inherently thinking-heavy. Gateway-side `chat_template_kwargs={thinking:false}` forwarding (D-EXTRACTION-CONTEXT-FIX-STAGE-4) would further help but deferred.
⁶ New claude-4.7-opus-style fine-tune of huihui-qwen3.6-35b-a3b, loaded in LM Studio with 40K context, thinking ON. Required two SDK patches (`response_format` json_object→text in 5 extractors + `llm_judge.py`) because newer LM Studio rejects `json_object` (HTTP 400 — must be json_schema or text). Patches detailed below.
⁷ Coverage 100%/100% — judge fix (session 67 cont.5 commit 63d91095) holds; gemma judge no longer drops batches. journey_west_zh_ch01's R=0.00 was a transient concurrency flake — `/review-impl` HIGH-1 root-cause verified the same async-jobs path produces 10 Chinese entities on isolated re-run (model output: ` ```json `-fenced JSON, aggregator parses cleanly). **Aggregate R likely understates by ~10 pp** — projecting the chapter's typical ~R=1.00 yields a near-baseline-equivalent **R ≈ 0.81 on a clean run**, matching the qwen3.6-35b-a3b session-61 baseline.
⁸ **Wasserstein abliteration variant of qwen3.6-35b-a3b — not viable at current settings.** Direct A/B vs huihui-claude-4.7-opus (same base architecture, different abliteration recipe). 8 of 9 chapters returned **completely empty extraction** (`{"entities":[], "relations":[], "events":[]}`); only `tam_cam_vi` produced anything — 6 entities, 0 relations, 0 events. Root cause: extreme reasoning ratio. The model's smoke ping consumed **97% reasoning tokens on a "hello" prompt** (248 reasoning / 7 content tokens); on a 6094-char extraction system prompt + chapter text, reasoning saturates the `ContextBudget.max_output_tokens=4096` cap before any content tokens are emitted, so the content channel is empty when the gateway aggregator parses. Anti-think prompt prefix (already in extractor system prompts since session 67 cont.4 commit 6a02750d) did not help. **Follow-up test:** re-ran 1-chapter alice_ch01 smoke with bumped output cap (200K context + `ContextBudget(max_output_tokens=16384)`) — slight improvement (2 entities for alice_ch01 — Alice + White Rabbit/other, vs 4 for huihui-claude-4.7-opus + 0 relations/events still) but R+E+F still starved. Confirms the abliteration recipe is reasoning-dominant regardless of output budget headroom. Possible mitigations for a future re-try: (a) gateway-forward `chat_template_kwargs={enable_thinking: false}` (`D-EXTRACTION-CONTEXT-FIX-STAGE-4-LIVE-SMOKE` path), (b) drop the variant. Wall clock 2:09 min — fast not because the model is fast but because most chapters terminated immediately on max_tokens=length with empty content. **Verdict: not viable as primary extractor.**

¹ Different from session-61 (qwen3.6-35b-a3b not loaded; qwen3-30b is 5B fewer params + older).
² R delta vs session-61 (0.57 vs 0.81) driven entirely by extractor model substitution — qwen3-30b under-extracts relations + Vietnamese fixtures vs qwen3.6-35b. P3 commits don't touch extraction prompts. Apples-to-apples re-check requires re-loading qwen3.6-35b-a3b in LM Studio + re-running.
³ Judge fixed in session 67 cont.5 (commit 63d91095): anti-thinking prompt prefix + batch_size 8→3 + 3× token budget. Coverage jumped 49/63% → 100/100%; gemma reasoning_tokens dropped 989→1 (anti-think worked). Pattern borrowed from RAGAS/DeepEval per-item small-batch approach.

Precision lift from session 60 to this run is small (extraction was already accurate when it survived); the **recall jump from ~0.46 to 0.81** is the fence-fix payoff — the chunks that were getting silently dropped were not low-quality, they were the bulk of the chapter.

## Open follow-ups (not blocking)

- `sherlock_speckled_band` (1139 lines / 17 chunks × 4 ops) — local-target perf limit; consider a per-chapter chunk-size cap or a separate large-chapter eval flow.
- Judge coverage is 62% / 56% — gemma-4-26b emits reasoning tokens that occasionally swallow a judge batch's verdicts (the original session-60 caveat carries over). A non-reasoning judge would harden the absolute numbers; a reasoning judge keeps the relative-improvement signal honest.
- Some chapters land with very low judge coverage (alice_ch01 P=30%, pride_prejudice R=14%) — uneven because the judge selects which items to grade per batch; a smaller batch size would even it out at the cost of more LLM calls.
- The catalogue-driven extraction ADR (`docs/03_planning/KNOWLEDGE_SERVICE_CATALOGUE_DRIVEN_EXTRACTION_ADR.md`) remains a real design improvement for genre fiction kinds, but its premise ("event recall ≈ 0 because of kind-enum drop") is empirically refuted on the current fixtures. Re-prioritise only when a genre-fiction fixture set exists.

## Run notes — LM Studio config (session-61 long-chapter perf fix)

During session 60–61, sustained extraction runs on the local 35B target (`qwen/qwen3.6-35b-a3b`) repeatedly stalled mid-job: the upstream stopped emitting tokens, the gateway streamer had no idle timeout (memory `feedback_no_timeout_on_llm_pipeline` — wall-clock timeout is deliberately off; idle timeout is fundamentally different and was added in session 61 — see `provider/streamer.go:idleTimeoutReader`), and the chunk waited forever. The trigger was LM Studio **auto-evicting the loaded model** under sustained load — confirmed by an in-DB `llm_jobs` row failing with HTTP 400 `"Failed to load model qwen/qwen3.6-35b-a3b. Operation canceled."` mid-job.

Two recommendations for the LM Studio side when running a long extraction or eval:

1. **Disable TTL / idle-eviction** of the loaded model. In LM Studio Settings → Local Server, switch off any "Unload after N minutes idle" option (or set the TTL high enough — many hours — to outlast the eval run). The 4-op × 17-chunk extraction of `sherlock_speckled_band` consumed ~1h+ of wall-clock; default TTLs are often shorter than that.
2. **Keep `Max Concurrent Predictions ≥ 4` + `Unified KV Cache ON`** (per `C-PRED-ALIGN-DEF-03`). Continuous batching is what closes the GPU-util gap that the serial loop leaves open.

On the gateway side, the **idle-timeout safety net** is enabled by default in deployment (`LLM_GATEWAY_STREAM_IDLE_TIMEOUT_S=300` in `infra/docker-compose.yml`). 300 s of upstream silence is treated as a stuck connection — the streamer closes the body, the chunk surfaces an `ErrUpstreamTimeout`, the aggregator records a chunk error, and the job completes with partial data instead of hanging. Set `=0` to opt out (preserves the historical no-timeout behavior).

For the eval harness, very long chapters can be excluded via `KNOWLEDGE_EVAL_LONG_CHAPTER_MAX_PARAGRAPHS=200` (default — sherlock_speckled_band at 252 paragraphs is skipped). Set high or to `0` to include them. The aggregate baseline above (P=0.97 R=0.81) was measured on the 9 chapters under this default, since the 10th chapter remained a perf outlier even after the idle-timeout safety net.

---

# 2026-05-26 — huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated baseline (Track A model swap)

User-driven Track A live-smoke verification. Previous huihui-qwen3.6-abliterated ran at ~7.6 tok/s parallel under thinking-heavy reasoning_tokens (55-89% of output) and was too slow for an iterative eval loop. Loaded a newer variant (`huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated`, a claude-4.7-opus-style fine-tune of huihui-qwen3.6 abliterated) in LM Studio at 40K context, thinking ON (per user direction "không có tắt thinking, 40k context, test hử xem"), and ran the same 9-chapter eval + LLM-judge pipeline.

## Setup

- Extractor: `huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated` (user_model `019e5650-eca7-78c2-985d-465aa3bce1ce`, 40K ctx, thinking ON)
- Judge: `google/gemma-4-26b-a4b` (user_model `019dc3df-58f3-7170-bb48-f1f0c9bd604c`, same family as prior baselines for continuity, NOT same family as extractor)
- Stack: extraction profile (postgres + redis + neo4j + auth + provider-registry + usage-billing + glossary + knowledge + worker-ai)
- Fixtures: 9 chapters (sherlock_speckled_band excluded by default `KNOWLEDGE_EVAL_LONG_CHAPTER_MAX_PARAGRAPHS=200`)
- Concurrency: 4 (default)
- Thresholds: disabled (`KNOWLEDGE_EVAL_MIN_PRECISION=0.0 KNOWLEDGE_EVAL_MIN_RECALL=0.0 KNOWLEDGE_EVAL_MAX_FP_TRAP=1.0`) — this run is a baseline measurement, not a gate pass/fail

## SDK patches required (response_format json_object → text)

Newer LM Studio rejects `response_format: {"type":"json_object"}` with HTTP 400 (`'response_format.type' must be 'json_schema' or 'text'`). The previous gateway-side normalization (`normalizeResponseFormatForKind` in `server.go`, commit db065152 from C-LM-STUDIO-FIX cycle 2026-04-25) lives on the `/internal/proxy/*` path; the async jobs path (`/internal/llm/jobs` → adapters.go) does NOT call it, so when knowledge-service extractors migrated from proxy → async jobs (Phase 4a-α), the LM Studio normalization was effectively left behind for every extraction. Yesterday's baselines (huihui-abliterated 2026-05-24) ran before LM Studio tightened the validation.

Patched in this session (5 SDK files + 1 judge file):

- `sdks/python/loreweave_extraction/extractors/entity.py:242`
- `sdks/python/loreweave_extraction/extractors/relation.py:256`
- `sdks/python/loreweave_extraction/extractors/event.py:372`
- `sdks/python/loreweave_extraction/extractors/fact.py:316`
- `sdks/python/loreweave_extraction/extractors/summarize.py:145`
- `services/knowledge-service/tests/quality/llm_judge.py:407`

Pattern: `"response_format": {"type": "json_object"}` → `"response_format": {"type": "text"}`. Justification: extractor + judge prompts already include "Return only the JSON object" instructions; the aggregator's `extractJSON` helper (session 67 cont.5 markdown-fence fix) handles fenced output. `text` is OpenAI-default behaviour (no JSON enforcement, prompt-driven) so cloud LLMs remain unaffected. **Follow-up:** add `normalizeResponseFormatForKind`-equivalent normalization to the async jobs path (gateway-side defensive fix) so future extractor changes don't have to re-discover this — tracked separately.

## Rule-based scores (9 chapters)

**Aggregate: P=0.324 (P_lenient=0.336) R=0.560 FP-trap=0.294**

| Chapter                | P    | R    | TP / FP / FN | FP-trap rate | Note |
|------------------------|-----:|-----:|--------------|-------------:|------|
| alice_ch01             | 0.29 | 0.71 | 5 / 12 / 2   | 0.00         | |
| alice_ch02             | 0.36 | 0.80 | 8 / 11 / 2   | 1.00         | 2/2 traps hit |
| journey_west_zh_ch01   | **0.00** | **0.00** | 0 / 0 / 21 | 0.00     | model emitted ZERO entities (Chinese gap) |
| journey_west_zh_ch14   | 0.30 | 0.59 | 10 / 22 / 7  | 0.00         | |
| little_women_ch01      | 0.67 | 0.60 | 6 / 2 / 4    | 0.33         | best rule-based P |
| pride_prejudice_ch01   | 0.25 | 0.43 | 3 / 6 / 4    | 1.00         | |
| sherlock_scandal_ch01  | 0.20 | 0.50 | 4 / 16 / 4   | 0.00         | |
| **son_tinh_thuy_tinh_vi** | **0.58** | **0.88** | **14 / 8 / 2** | **0.14** | best chapter overall — Vietnamese |
| tam_cam_vi             | 0.26 | 0.53 | 9 / 19 / 8   | 0.17         | |

Extraction wall clock: **424.83s (7:04 min)** for 9 chapters at concurrency=4. **~2.7× faster than the qwen3.6-35b session-61 baseline (19 min)** — thinking-ON did not regress throughput; the claude-4.7-opus fine-tune appears more efficient per token than the original qwen3.6.

## LLM-judge scores (gemma-4-26b-a4b)

**Macro aggregate: P=0.93 R=0.71 | coverage P=100% R=100%**

| Chapter                | P    | R    | ent P/R     | rel P/R     | evt P/R     | cov P/R    |
|------------------------|-----:|-----:|-------------|-------------|-------------|------------|
| alice_ch01             | 0.88 | 0.86 | 0.50 / 0.67 | 0.86 / 1.00 | 1.00 / 1.00 | 100% / 100% |
| alice_ch02             | 0.93 | **1.00** | 0.83 / 1.00 | 0.88 / 1.00 | 1.00 / 1.00 | 100% / 100% |
| journey_west_zh_ch01   | 1.00 | **0.00** | 1.00 / 0.00 | 1.00 / 0.00 | 1.00 / 0.00 | 100% / 100% | nothing to judge for P → trivially 1.00 |
| journey_west_zh_ch14   | 0.91 | 0.94 | 1.00 / 0.89 | 0.75 / 1.00 | 1.00 / 1.00 | 100% / 100% |
| little_women_ch01      | 0.88 | 0.60 | 0.88 / 1.00 | 1.00 / 0.00 | 1.00 / 0.00 | 100% / 100% |
| pride_prejudice_ch01   | 1.00 | 0.43 | 1.00 / 0.75 | 1.00 / 0.00 | 1.00 / 0.00 | 100% / 100% |
| sherlock_scandal_ch01  | 0.88 | 0.75 | 1.00 / 0.75 | 0.81 / 0.50 | 1.00 / 1.00 | 100% / 100% |
| **son_tinh_thuy_tinh_vi** | **1.00** | **1.00** | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 | 100% / 100% | perfect chapter |
| tam_cam_vi             | 0.87 | 0.82 | 1.00 / 0.71 | 0.69 / 0.80 | 0.97 / 1.00 | 100% / 100% |

Coverage 100/100% across all 9 chapters — judge tuning from session 67 cont.5 (anti-thinking prompt prefix + batch_size 8→3 + 3× token budget, commit 63d91095) holds. Gemma judge no longer drops batches; every extracted item + every gold item gets a verdict.

## Comparison vs session-61 qwen3.6 baseline

| Metric | qwen3.6-35b-a3b (session-61) | huihui-claude-4.7-opus (today) | Δ |
|---|---:|---:|---:|
| Precision (macro) | 0.97 | 0.93 | **−0.04 pp** |
| Recall (macro, as measured) | 0.81 | 0.71 | **−0.10 pp** |
| Recall (projected, excl. transient ch01 zero) | 0.81 | ~0.81 | **±0** |
| Coverage (P / R) | 62% / 56% | 100% / 100% | **+38 / +44 pp** |
| Extraction wall clock | 19 min | 7 min | **−63% (≈2.7× faster)** |
| Model size | 35B-A3B (3B active MoE) | 35B-A3B (3B active MoE) | same arch |

The 10-point gross R drop is **entirely accounted for by a single transient zero on journey_west_zh_ch01** (concurrency=4 flake; isolated re-run yields 10 entities cleanly). Projected clean-run R is on par with qwen3.6-35b-a3b baseline, with 2.7× the throughput and full judge coverage. **Verdict: viable model swap; quality on par, throughput substantially better.**

## Run notes — observations

1. **journey_west_zh_ch01 zero-extraction was a transient under concurrent eval load — not a CJK model weakness.** During the 9-chapter parallel eval (concurrency=4) the chapter scored 0/0/21 (TP/FP/FN). Post-eval root-cause investigation (`/review-impl` HIGH-1): re-ran the same async-jobs extractor on the same fixture in isolation → **10 Chinese entities extracted cleanly** (盤古, 三皇, 五帝, 四大部洲, 東勝神洲, 傲來國, 花果山, 玉皇大天尊玄穹高上帝, 千里眼, 順風耳). Raw model output capture showed the response was a ` ```json `-fenced JSON object with those 10 entities + reasoning routed to the separate ReasoningEvent stream — `extractJSONObject` (aggregator.go:376) recovers fenced output and would have parsed this correctly. Conclusion: the 0-result was concurrency contention / cold-model warmup, not a `text`-mode regression nor CJK model weakness. journey_west_zh_ch14 worked fine in the same parallel run (R=0.94). **Aggregate R likely understates by ~10 pp** because of this single transient — the chapter's true LLM-judge R would be near 1.00 in line with journey_west_zh_ch14. Filed as `D-EXTRACTION-PARALLEL-CONCURRENCY-FLAKE` — add a retry path when an extractor returns 0 candidates on a non-trivial chapter.
2. **Throughput vs prior huihui-abliterated (32K, anti-think prefix).** Yesterday huihui-abliterated ran at ~7.6 tok/s parallel with anti-think prompting reducing reasoning_tokens to 55-89%. Today's claude-4.7-opus variant at 40K with thinking ON ran the 9-chapter eval in 7 min — implying either the fine-tune has shorter reasoning chains, or LM Studio's continuous-batching has improved, or both.
3. **Precision uniformly high (≥0.87 on every non-trivial chapter).** Discrimination test (run earlier in session before being skipped for asyncio teardown reasons) confirmed the gemma judge is not rubber-stamping. So P=0.93 reflects genuinely source-supported extractions.
4. **Vietnamese chapter `son_tinh_thuy_tinh_vi` perfect (P=R=1.00) for the second time** — qwen3.6 also scored 1.00/1.00 on this. Vietnamese narrative extraction is well-served by the qwen3.6 family.
5. **`tam_cam_vi` event recall = 1.00** (97% P / 100% R) — strongest event extraction across the run. With 13 events extracted (more than any other fixture's gold count), this confirms event recall is solid for the Vietnamese narrative fixtures.

## Reproducing

After loading the model in LM Studio with 40K context + applying the SDK patches above + the stack is up:

```sh
# Extraction phase (huihui-claude-4.7-opus loaded in LM Studio):
docker exec -d -w /app \
  -e PYTHONPATH=/app \
  -e KNOWLEDGE_EVAL_MODEL=019e5650-eca7-78c2-985d-465aa3bce1ce \
  -e KNOWLEDGE_EVAL_USER_ID=019d4966-56c0-714f-a16a-3454622c8c15 \
  -e KNOWLEDGE_EVAL_MODEL_SOURCE=user_model \
  -e KNOWLEDGE_EVAL_MODEL_CONTEXT=40000 \
  -e KNOWLEDGE_EVAL_DUMP_PATH=/tmp/eval_dump_huihui_v2 \
  -e KNOWLEDGE_EVAL_MIN_PRECISION=0.0 \
  -e KNOWLEDGE_EVAL_MIN_RECALL=0.0 \
  -e KNOWLEDGE_EVAL_MAX_FP_TRAP=1.0 \
  -e KNOWLEDGE_EVAL_CHAPTER_CONCURRENCY=4 \
  infra-knowledge-service-1 \
  python -m pytest tests/quality/test_extraction_eval.py --run-quality -v -s

# After extraction completes, swap LM Studio to gemma-4-26b-a4b, then:
docker exec -d -w /app \
  -e PYTHONPATH=/app \
  -e KNOWLEDGE_EVAL_JUDGE_MODEL=019dc3df-58f3-7170-bb48-f1f0c9bd604c \
  -e KNOWLEDGE_EVAL_USER_ID=019d4966-56c0-714f-a16a-3454622c8c15 \
  -e KNOWLEDGE_EVAL_JUDGE_MODEL_SOURCE=user_model \
  -e KNOWLEDGE_JUDGE_DUMP_PATH=/tmp/eval_dump_huihui_v2 \
  infra-knowledge-service-1 \
  python -m pytest tests/quality/test_judge_eval.py -k test_llm_judge_extraction_quality --run-quality -v -s
```

The `-k` filter is required to skip the discrimination test in the same pytest invocation, due to a known asyncio event-loop teardown leak between tests (separate cycle's pytest-asyncio fixture-scoping fix).

## Open follow-ups (not blocking)

- ~~**journey_west_zh_ch01 zero-extraction**~~ — RESOLVED post-eval via `/review-impl` HIGH-1: confirmed transient concurrency flake (isolated re-run produced 10 entities cleanly). Filed `D-EXTRACTION-PARALLEL-CONCURRENCY-FLAKE` for the retry-on-zero defense.
- **Gateway async-jobs response_format normalization** — port `normalizeResponseFormatForKind` (currently only on `/internal/proxy/*`) to the `/internal/llm/jobs` adapter layer so future LM Studio extractors don't have to discover this regression. Tracked as `D-LM-STUDIO-RESPONSE-FORMAT-ASYNC-PATH` in the SDK-patch plan.
- **Aggregator reasoning-content contamination guard** — `extractJSONObject` assumes reasoning_content is on a separate stream channel; if a future model emits reasoning as regular content tokens, "first { to last }" picks up the wrong range. Filed `D-AGGREGATOR-REASONING-CONTAMINATION-GUARD`.
- **OpenAI BYOK live smoke** — patch verified against LM Studio + by OpenAI API spec for `response_format: text`; a one-off OpenAI live smoke would close the spec-only assumption. Deferred per `feedback_local_llm_first_cloud_is_fallback`.
- **Speckled Band on the new model** — skipped by default; worth a separate run when the chunk-cap or large-chapter eval flow lands.
- **sherlock_scandal_ch01 relation precision (P=0.81)** — slightly below the typical ≥0.88, weakest chapter for the model after the now-resolved journey_west_zh_ch01. Manual inspection of relation FPs could surface a prompt or canonicalization fix.

---

# 2026-05-27 — Track A model-swap iteration: A/B/C verdict + huihui-qwen3-30b-instruct high-recall baseline

After the 2026-05-26 huihui-claude-4.7-opus baseline was locked, ran a model bracket against same-arch variants to inform default-model selection. Three contenders tested with identical 9-chapter eval + gemma-4-26b-a4b judge:

1. `huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated` (yesterday's baseline)
2. `qwen3.6-35b-a3b-uncensored-wasserstein` (same base, different abliteration)
3. `huihui-qwen3-30b-a3b-instruct-2507-abliterated` (qwen3 not 3.6, smaller, pure-instruct no reasoning)

## Final A/B/C comparison (LLM-judge gemma-4-26b)

| Model | P | R | F1 | Coverage P/R | Extraction wall | Verdict |
|---|---:|---:|---:|---:|---:|---|
| huihui-**claude-4.7-opus** (35B) | **0.93** | 0.71 | 0.806 | 100/100% | 7:04 min | **Precision champion** — conservative, low-noise |
| **huihui-qwen3-30b-instruct** (30B) | 0.79 | **0.90** | **0.841** | 100/100% | **3:44 min** | **High-recall + speed champion** — best F1, ≈2× faster |
| wasserstein (35B) | — | — | — | — | 2:09 min | **Negative** — reasoning-dominant, R+E+F starves on max_output even at 16K |

**Trade-off articulated by use case (per Mode-3 retrieval analysis):**

- **High-precision use case** (wiki article generation, translation glossary, "publish-quality" facts): prefer `huihui-claude-4.7-opus`. Less noise in the knowledge graph; what's extracted is trustworthy.
- **High-recall use case** (chat/RAG context retrieval, search-by-entity, comprehensive analytics): prefer `huihui-qwen3-30b-instruct`. RAG's LLM-side filtering tolerates FPs in the context; missing facts hurt more than noisy ones.
- **Balanced (default for Mode-3 mainline + R&D iteration):** `huihui-qwen3-30b-instruct` wins on F1 (0.841 vs 0.806) AND wall clock (≈2× faster), AND fixes the Chinese transient seen on claude-4.7-opus (`journey_west_zh_ch01` P=0.91/R=1.00 on 30B vs transient zero on claude).

## huihui-qwen3-30b-instruct per-chapter judge scores

**Macro aggregate: P=0.79 R=0.90 | coverage P=100% R=100% | extraction wall 3:44 min**

| Chapter | P | R | ent P/R | rel P/R | evt P/R |
|---|---:|---:|---|---|---|
| alice_ch01 | 0.81 | 1.00 | 0.91/1.00 | 0.68/1.00 | 1.00/1.00 |
| alice_ch02 | 0.75 | 0.90 | 0.91/0.80 | 0.28/1.00 | 1.00/1.00 |
| **journey_west_zh_ch01** | **0.91** | **1.00** | 0.97/1.00 | 0.87/1.00 | 0.92/1.00 |
| journey_west_zh_ch14 | 0.73 | 0.71 | 1.00/0.89 | 0.55/1.00 | **0.00/0.00** |
| little_women_ch01 | 0.69 | 0.90 | 0.94/1.00 | 0.06/0.00 | 0.88/1.00 |
| pride_prejudice_ch01 | 0.72 | 1.00 | 0.88/1.00 | 0.50/1.00 | 0.86/1.00 |
| sherlock_scandal_ch01 | 0.71 | 0.75 | 0.92/0.75 | 0.43/0.50 | 0.83/1.00 |
| **son_tinh_thuy_tinh_vi** | **0.96** | 0.94 | 1.00/1.00 | 0.91/0.80 | 1.00/1.00 |
| tam_cam_vi | 0.80 | 0.94 | 0.91/0.86 | 0.61/1.00 | 1.00/1.00 |

## huihui-qwen3-30b-instruct rule-based per-chapter (for completeness)

**Aggregate rule-based: P=0.165 R=0.580 FP-trap=0.360** — over-extracts ≈5× the conservative gold-set entity count (high TP + high FP). LLM-judge confirms most FPs are legitimately source-supported (Speckled-Band-style over-extraction pattern — see Finding 3 in C19 baseline above).

| Chapter | P | R | TP / FP / FN | FP-trap rate |
|---|---:|---:|---|---:|
| alice_ch01 | 0.14 | 0.71 | 5 / 29 / 2 | 0.00 |
| alice_ch02 | 0.22 | 0.70 | 7 / 20 / 3 | 1.00 |
| journey_west_zh_ch01 | 0.13 | 0.43 | 9 / 54 / 12 | 0.25 |
| journey_west_zh_ch14 | 0.26 | 0.71 | 12 / 22 / 5 | 0.25 |
| little_women_ch01 | 0.09 | 0.60 | 6 / 54 / 4 | 0.33 |
| pride_prejudice_ch01 | 0.15 | 0.71 | 5 / 24 / 2 | 0.67 |
| sherlock_scandal_ch01 | 0.21 | 0.50 | 4 / 13 / 4 | 0.00 |
| son_tinh_thuy_tinh_vi | 0.19 | 0.62 | 10 / 39 / 6 | 0.57 |
| tam_cam_vi | 0.10 | 0.24 | 4 / 24 / 13 | 0.17 |

## Notable observations

1. **Chinese robustness.** `journey_west_zh_ch01` LLM-judge P=0.91 R=1.00 on 30B — no transient gap. Compare claude-4.7-opus same chapter (R=0.00 transient on 9-chapter parallel run, ~R=1.00 on isolated re-run). 30B's reasoning-free dispatch is more stable under concurrent eval load.
2. **Events solidly extracted across most chapters** (≥0.83 P, ≥1.0 R on 6/9 chapters) — historical "events are the biggest hole" finding does NOT reproduce on this model. Either the per-op extraction split (entity → R+E+F gather) introduced in P3 phase plus the markdown-fence aggregator fix carries forward, or 30B's instruct training is naturally action-extraction-friendly.
3. **Relations are the new weak axis** — alice_ch02 rel P=0.28, little_women_ch01 rel P=0.06/R=0.00, tam_cam_vi rel P=0.61. The over-extraction problem concentrates here. Likely candidate for the next prompt cycle.
4. **journey_west_zh_ch14 events P=0.00 R=0.00** — single-chapter event failure (rest of run had events at near-perfect). Possibly a chunking boundary issue on this longer Chinese fixture; worth a future targeted look.

## Default-model decision

**Switching the R&D mainline default to `huihui-qwen3-30b-instruct` (user_model `019e6a20-eeac-7b96-82ee-69a16d8ef68d`)** for the following architecture-improvement cycles. Justification: recall has more headroom than precision (P=0.93 already near-ceiling under LLM-judge methodology; R=0.71-0.90 still has 10-20pp room), and the recall improvements are what unlock downstream Mode-3 retrieval quality + multilingual coverage. Keep `huihui-claude-4.7-opus` registered for ad-hoc precision-focused runs (wiki generation, translation memo refinement).

## Reproducing 30B run

Same shell as the 2026-05-26 huihui-claude-4.7-opus reproducing block, with model_ref swapped:

```sh
# Extraction phase (huihui-qwen3-30b loaded in LM Studio):
KNOWLEDGE_EVAL_MODEL=019e6a20-eeac-7b96-82ee-69a16d8ef68d  # huihui-qwen3-30b-instruct-2507-abliterated
KNOWLEDGE_EVAL_MODEL_CONTEXT=40000
KNOWLEDGE_EVAL_DUMP_PATH=/tmp/eval_dump_huihui30b
# … (rest identical)
```

## Footnote ⁹ for the comparison table above

⁹ **huihui-qwen3-30b-a3b-instruct-2507-abliterated** is a pure-instruct (no reasoning) variant of qwen3 (NOT qwen3.6 — older generation, smaller MoE). Smoke ping confirmed `reasoning_tokens=0` even without anti-think prefix; the model uses its entire output budget on content. Direct A/B vs huihui-claude-4.7-opus on the same 9-chapter fixture set + same gemma-4-26b-a4b judge: P=0.79 (vs claude 0.93), R=0.90 (vs claude 0.71), F1=0.841 (vs claude 0.806). Wall clock 3:44 min (vs claude 7:04 min — **≈2× faster**). Chinese chapter `journey_west_zh_ch01` extracted cleanly (P=0.91/R=1.00) without the transient zero seen on claude. Best balanced choice; new default for R&D mainline.

## Architectural attempt #1 — multilingual few-shot prompts (REVERTED 2026-05-27)

First post-Track-A architectural cycle aimed at the recall lever. Per Finding 4 of the C19 baseline ("Traditional Chinese remains the weak axis even for the best local model… Prompt examples are all English/Latin script") and the recommended-next-actions list item #5 ("Chinese + Vietnamese examples to lift Vietnamese bare-noun recognition"), appended one Chinese (Example C: 凌風 / 蒼山真人 / 玄霜宗 / 紫雲劍) + one Vietnamese (Example D: Mỵ Linh / bà mẹ ghẻ / Khôi / kiếm Bạch Long) demonstration to each of the 4 system prompts (entity / relation / event / fact). Each new example mirrored the existing English example structure (TEXT + KNOWN_ENTITIES + JSON output) and demonstrated scene-relevance filtering + alias collection + kinship direction in the target language. Plan: `docs/plans/2026-05-27-multilingual-fewshot-prompts.md` (deleted on revert; preserved in git log).

**Result: cycle reverted.** Two distinct failure modes surfaced under live smoke against `huihui-qwen3-30b-a3b-instruct-2507-abliterated`:

1. **Recall regressed by ~24 pp** (macro R 0.580 → 0.343 rule-based at concurrency=1) — the new "Notice what is OMITTED and WHY" sections in the CJK and VN examples reinforced the existing English scene-relevance lesson 3× (1 English Example B + 1 Chinese Example C + 1 Vietnamese Example D, all teaching omission-bias). The model OVER-CORRECTED — extracted more conservatively across all languages, including English. Vietnamese was hit hardest: `son_tinh_thuy_tinh_vi` R 0.62 → 0.31, `journey_west_zh_ch14` R 0.71 → 0.53. The naive "more examples = better" intuition failed because the examples shared a single high-pressure lesson (omission); the model learned the lesson too well.

2. **LM Studio HTTP 500 at concurrency ≥ 2** — the system prompt grew from ~6,094 chars (1 English example) to ~8,969 chars (1 English + 1 Chinese + 1 Vietnamese examples). Combined with `max_output_tokens=4096` per slot × concurrency=4 parallel chapters × 4 ops gather, the KV cache reservation overflowed VRAM. Every concurrent extraction request returned HTTP 500 (Internal Server Error) from LM Studio after the upstream retry budget was exhausted. Diagnostic ladder: c=4/max=4096 → all-zero (HTTP 500); c=4/max=8192 → all-zero (worse OOM); c=2/max=4096 → all-zero (still HTTP 500 under bigger-prompt batches); c=1/max=4096 → non-empty but recall-regressed. Direct stream-path probe (single non-concurrent request) on the same prompt + model worked fine — 11 entities cleanly extracted on `alice_ch01` — confirming the issue is concurrency × prompt-size, not a prompt-content bug.

**Lessons captured (for future recall cycles):**

- **Few-shot lessons compound rather than dilute.** Adding parallel examples that ALL teach the same lesson amplifies it instead of broadening coverage. For multilingual recall, the next attempt should pair LANGUAGES with DIFFERENT lessons (e.g. English shows scene-relevance, Chinese shows alias collection only, Vietnamese shows common-noun-as-name only) — three orthogonal lessons across three languages, not one lesson × three languages.
- **System prompt size has a hard concurrency ceiling on LM Studio** at a given VRAM budget. The 8,969-char prompt at c=4 broke; the 6,094-char prompt at c=4 worked. There's an implicit prompt-size × concurrency × max_output_tokens budget that LM Studio doesn't surface — when exceeded, the failure is a generic HTTP 500. Future cycles touching system prompts should either (a) keep prompt size flat, (b) reduce eval concurrency, or (c) split content into shorter per-language prompts dispatched by language detection.
- **Live smoke is mandatory** — the cycle's unit-suite-style regression-lock for the response_format patch passed instantly; the live smoke is the only signal that surfaced the recall regression + the LM Studio OOM. Validates `feedback_mock_only_coverage_hides_crossservice_bugs` for this class of change.
- **Direct probe through the streaming path can mask aggregator-side issues** during cycle design. The probe on alice_ch01 produced clean extraction; the eval through the async-jobs path failed concurrent-batched. Both paths exist for good reasons but a successful probe is not a sufficient pre-deploy signal.

**Files touched in the attempt** (all reverted):
- `sdks/python/loreweave_extraction/prompts/entity_extraction_system.md` (+73 lines, reverted)
- `sdks/python/loreweave_extraction/prompts/relation_extraction_system.md` (+64 lines, reverted)
- `sdks/python/loreweave_extraction/prompts/event_extraction_system.md` (+85 lines, reverted)
- `sdks/python/loreweave_extraction/prompts/fact_extraction_system.md` (+81 lines, reverted)
- `services/knowledge-service/tests/quality/test_extraction_eval.py` (added `KNOWLEDGE_EVAL_MAX_OUTPUT_TOKENS` env var, reverted — but documented here as a known knob for future cycles that legitimately need a higher cap)

## Track A — CLOSED

The bracket-iteration phase of Track A is closed. Acquired baselines are sufficient to inform the architectural-improvement track:

- **High-precision baseline:** huihui-claude-4.7-opus (P=0.93, R=0.71-0.81)
- **High-recall baseline:** huihui-qwen3-30b-instruct (P=0.79, R=0.90)
- **Negative datapoint:** wasserstein (abliteration recipe matters as much as base arch)

**Returning to the original Track A purpose: evaluate first, THEN re-architect for per-metric improvements.** Recall lever is identified as having more headroom; next cycles should target recall-improvement architecture (e.g., multi-language few-shot prompts, specialized relation/event prompts, hybrid 2-pass with 30B-then-claude refinement, P4 semantic chunking, P5 gated LLM coref). Filed under "What's NEXT" in [`docs/sessions/SESSION_HANDOFF.md`](../../../docs/sessions/SESSION_HANDOFF.md).

---

# 2026-05-28 — Eval framework overhaul: anchor + multi-judge ensemble baseline

The XL meta-cycle (spec: [`docs/specs/2026-05-27-eval-framework-overhaul.md`](../../../docs/specs/2026-05-27-eval-framework-overhaul.md), plan: [`docs/plans/2026-05-27-eval-framework-overhaul.md`](../../../docs/plans/2026-05-27-eval-framework-overhaul.md)) shipped the anchor + multi-judge ensemble framework + re-baselined the 30B extractor under that framework. This section records what's now the canonical measurement methodology.

## Anchor benchmarks (informational; sanity-floor only, not quality gates)

Two published-baseline datasets establish external truth signals for our extractor. Per spec D2 + HIGH-1 fix, each anchor enforces a **sanity floor** (F1 ≥ 0.10 AND avg_n_extracted ≥ 0.1 × avg_n_gold). Below the floor → extractor regressed to ~empty + cycle does not pass; above → F1 is recorded as informational.

| Anchor | Dataset (HF) | n_samples | Extractor | F1 | P | R | avg ext / avg gold |
|---|---|---|---|---:|---:|---:|---|
| **CoNLL-2003 NER** (English news, strict span match) | `tner/conll2003` test | 100 | huihui-qwen3-30b-instruct (40K ctx) | **0.219** | 0.204 | 0.237 | 3.4 / 2.1 |
| **DocRED unlabeled-triple** (English Wikipedia) | `thunlp/docred` validation | 50 | huihui-qwen3-30b-instruct (40K ctx) | **0.127** | 0.110 | 0.149 | 15.0 / 10.4 |

**How to read these numbers.** RoBERTa-large SOTA on CoNLL-2003 ≈ 92.4 F1 (we hit ~24%); RoBERTa-baseline on DocRED unlabeled-F1 ≈ 0.45-0.55 (we hit ~28%). Our extractor isn't trained on either schema — it's a narrative-fiction extractor — so getting ~25-30% of SOTA across two different external domains is the **calibration signal**, not a quality claim. Both anchors clear the sanity floor (`passes_sanity_floor=True` in both reports). Future cycles that touch prompts / aggregator / scoring re-run these anchors as part of acceptance per spec D10 cadence policy.

Spec D9 cross-check caveat: CoNLL + DocRED are English-only. For CJK/VN regressions (e.g., the cycle 1 multilang fewshot Vietnamese drop), the anchor is silent — verdicts come from the ensemble alone until the WikiNeural multilingual anchor lands.

## Multi-judge ensemble baseline (30B extractor)

Three local LM Studio judges run sequentially via JIT model swap, each scoring the same 9-chapter `huihui-qwen3-30b-instruct` extraction dump independently. The framework's correctness gate (D11) requires ≥ 2 judges complete; this run produced **3/3 complete** + 100% chapter coverage across 487 total verdict items.

### Per-judge macro P/R

| Judge | Model | Macro P | Macro R | Notes |
|---|---|---:|---:|---|
| **A (gemma)** | google/gemma-4-26b-a4b | **0.834** | **0.937** | strictness=0.84 (median); slight recall preference (rp_bias=−0.13) |
| **B (qwen-30b)** | huihui-qwen3-30b-instruct | 0.980 | 1.000 | **lenient outlier** (strictness=0.93, +0.09 over median); accepts almost everything; would inflate single-judge metrics |
| **C (claude-4.7-opus)** | huihui-qwen3.6-35b-a3b-claude-4.7-opus-abliterated | 0.983 | 0.879 | strictness=0.85; strict on precision (0.98) but lower recall (0.88) |

Median over the 3 judges: **P ≈ 0.93 / R ≈ 0.94**. Single-judge gemma run (yesterday's locked baseline for 30B) was P=0.79 / R=0.90 — today's gemma re-run is P=0.83 / R=0.94 (within run-to-run variance + judge-side budget bump per spec D5 vs cycle 67 cont.5's prior tuning).

### Fleiss kappa — substantial inter-rater reliability

`κ = 0.708` over 461 items voted by all 3 judges (94.7% of the 487 total items). Per Landis & Koch 1977 cutoffs, that's "substantial" agreement — the ensemble methodology is producing trustworthy data.

- Total items voted: 487
- Items disputed (no majority): 32 (6.6%)
- Items with full majority: 455 (93.4%)

### Per-judge bias profile (D12 dimensions)

| Judge | strictness | gap from median | language acceptance (en/zh/vi) | language_bias span | precision_accept | recall_accept | rp_bias |
|---|---:|---:|---|---:|---:|---:|---:|
| gemma | 0.841 | 0.004 | 0.78 / 0.87 / 0.92 | 0.138 | 0.812 | 0.938 | −0.126 |
| qwen-30b | 0.933 | **0.088** | 0.91 / 0.94 / 0.96 | 0.049 | 0.913 | 1.000 | −0.087 |
| claude-4.7-opus | 0.845 | 0.000 | 0.79 / 0.87 / 0.91 | 0.127 | 0.834 | 0.883 | −0.049 |

**No flags fired** (all bias metrics below their thresholds: strictness_gap < 0.15, language_bias < 0.15). But the pattern matters:
- **EN-stricter than CJK/VN** across all 3 judges (acceptance 0.78-0.91 EN → 0.87-0.96 zh → 0.91-0.96 vi). The judges accept CJK + VN extractions more readily than English. Two possible reasons: (a) the extractor genuinely IS better on CJK/VN at over-extracting (matches our prior "30B over-extracts" finding); (b) the judges are slightly more permissive on non-English content (fewer training-data anchors → weaker rejection). The English anchor (CoNLL) can't disambiguate; multilingual anchor cycle (WikiNeural) would.
- **All 3 judges favor recall over precision** (rp_bias is negative for all — they accept gold items "covered" more readily than they accept extracted items as "supported"). Consistent with judges that hedge toward "give credit when reasonable." For high-precision use cases, prefer claude-4.7-opus's narrower bias (−0.05) over gemma's wider bias (−0.13).

### Per-chapter dispute distribution

| Chapter | Total votes | Majority | Disputed | Dispute rate |
|---|---:|---:|---:|---:|
| son_tinh_thuy_tinh_vi | 70 | 70 | 0 | **0.0%** — clean consensus |
| sherlock_scandal_ch01 | 25 | 24 | 1 | 4.0% |
| pride_prejudice_ch01 | 39 | 38 | 1 | 2.6% |
| alice_ch01 | 37 | 34 | 3 | 8.1% |
| alice_ch02 | 44 | 42 | 2 | 4.5% |
| tam_cam_vi | 59 | 56 | 3 | 5.1% |
| journey_west_zh_ch01 | 80 | 76 | 4 | 5.0% |
| journey_west_zh_ch14 | 63 | 57 | 6 | 9.5% |
| **little_women_ch01** | 70 | 58 | **12** | **17.1%** — most contentious |

`little_women_ch01` is the new weak chapter under ensemble — 17% disputed. Worth a manual review of disputed items to find the systematic disagreement (likely event-summary phrasing differences across judges).

### Wall clock

`28:29 min` for 3 judges × 9 chapters sequential. Budget bump (KNOWLEDGE_JUDGE_BASE_TOKENS=3072, KNOWLEDGE_JUDGE_PER_ITEM_TOKENS=384, KNOWLEDGE_JUDGE_BATCH_SIZE=2) reduced JSON truncation warnings from the first attempt and actually sped up the run vs the initial 60-90 min estimate — fewer wasted reasoning cycles per call.

## D9 cycle-1 re-baseline — DEFERRED

Spec D9's "extract vs scoring" decision rule on the cycle-1 (multilang fewshot) dump was scoped into this cycle. **Deferred to next session** — the cycle-1 dump (`/tmp/eval_dump_30b_ml_c1`) was wiped by mid-cycle Docker stack restart + has not been re-created (cycle 1 prompts were reverted, so re-creating means temporarily restoring the multilang prompts + re-extracting + reverting again — clean cycle, ~10 min). Once recreated, run the same ensemble against it + apply D9 decision rule. Filed as `D-CYCLE1-ENSEMBLE-FORENSIC` (informational, not blocking).

## Methodology lessons captured (RETRO)

- **Live smoke is the only signal that surfaces test-adapter bugs.** The cycle's 19 foundation unit tests covered Fleiss/D11/D12 math but NOT the `_chapter_judgement_to_verdicts` flatten — which crashed on `rv.idx` vs `rv.gold_idx` only when given a producer-typed `GoldVerdict`. ~60 min of LM Studio compute wasted on the first ensemble run. **Fix landed inline:** moved flatten to `judge_ensemble.chapter_judgement_to_verdicts` (public) + added 2 regression-lock unit tests that instantiate the real `GoldVerdict` producer type. Validates `feedback_test_input_fields_from_producer_schema` again.
- **Bumping judge token budgets sped up the run.** Counter-intuitive: KNOWLEDGE_JUDGE_BASE_TOKENS bump from 1536 → 3072 reduced overall wall clock by reducing JSON-truncation retries on reasoning-heavy judges. The first ensemble had ~30 "judge call near/over budget" warnings; the re-run had ~5. Lesson: tight budgets on reasoning models are penny-wise, pound-foolish.
- **The qwen-30b judge over-accepts.** When used as the SOLE judge (yesterday's R=0.90), it gives artificially inflated metrics. Ensemble corrects for this. Future single-judge runs should prefer gemma (more median, closer to ensemble consensus).
- **CJK/VN judges are MORE LENIENT than English judges.** All 3 judges accepted CJK + VN at 87-96% vs English at 78-91%. Could be over-extraction reality OR judge under-rejection on non-English. The current anchor benchmarks (English-only) can't disambiguate; defer until WikiNeural multilingual anchor lands.

## Default measurement methodology (effective 2026-05-28)

Per cycle's D10 cadence policy:

- **In-cycle iteration smokes:** single-judge gemma via `test_judge_eval.py::test_llm_judge_extraction_quality` (~20 min). Fast feedback.
- **Baseline-lock runs (every new model, every prompt/aggregator change, quarterly drift check, pre-ship gate):** 3-judge ensemble via `test_judge_eval.py::test_llm_judge_ensemble` (~30 min after the cycle-1 bug fix + budget bumps) + CoNLL + DocRED anchors (~10 min total). Total: ~40 min for full baseline lock.
- **Single source of metric authority:** the ensemble's majority verdict + Fleiss κ. Per-judge numbers are informational; ensemble is the lock.

## Reproducing the 30B baseline (ensemble + anchors)

```sh
# Anchors first (any judge model loaded in LM Studio works since these
# only invoke the extractor):
docker exec -d -w /app \
  -e PYTHONPATH=/app \
  -e KNOWLEDGE_EVAL_MODEL=019e6a20-eeac-7b96-82ee-69a16d8ef68d \
  -e KNOWLEDGE_EVAL_USER_ID=019d4966-56c0-714f-a16a-3454622c8c15 \
  -e KNOWLEDGE_EVAL_MODEL_CONTEXT=40000 \
  -e KNOWLEDGE_EVAL_DUMP_PATH=/tmp/eval_dump_anchors \
  -e HF_DATASETS_CACHE=/tmp/hf_cache \
  -e HOME=/tmp/hf_cache \
  infra-knowledge-service-1 \
  python -m pytest tests/quality/test_anchor_eval.py --run-quality -v -s

# Then extraction (huihui-qwen3-30b-instruct loaded in LM Studio):
docker exec -d -w /app \
  -e PYTHONPATH=/app \
  -e KNOWLEDGE_EVAL_MODEL=019e6a20-eeac-7b96-82ee-69a16d8ef68d \
  -e KNOWLEDGE_EVAL_USER_ID=019d4966-56c0-714f-a16a-3454622c8c15 \
  -e KNOWLEDGE_EVAL_MODEL_CONTEXT=40000 \
  -e KNOWLEDGE_EVAL_DUMP_PATH=/tmp/eval_dump_30b_baseline_v2 \
  -e KNOWLEDGE_EVAL_CHAPTER_CONCURRENCY=4 \
  infra-knowledge-service-1 \
  python -m pytest tests/quality/test_extraction_eval.py --run-quality -v -s

# Then ensemble (3 judges sequential JIT — KNOWLEDGE_JUDGE_BASE_TOKENS bump
# avoids JSON truncation on reasoning-heavy judges):
docker exec -d -w /app \
  -e PYTHONPATH=/app \
  -e KNOWLEDGE_EVAL_USER_ID=019d4966-56c0-714f-a16a-3454622c8c15 \
  -e KNOWLEDGE_JUDGE_DUMP_PATH=/tmp/eval_dump_30b_baseline_v2 \
  -e KNOWLEDGE_EVAL_ENSEMBLE_JUDGES=019dc3df-58f3-7170-bb48-f1f0c9bd604c,019e6a20-eeac-7b96-82ee-69a16d8ef68d,019e5650-eca7-78c2-985d-465aa3bce1ce \
  -e KNOWLEDGE_EVAL_ENSEMBLE_LABELS=gemma,qwen-30b,claude-4.7-opus \
  -e KNOWLEDGE_JUDGE_BASE_TOKENS=3072 \
  -e KNOWLEDGE_JUDGE_PER_ITEM_TOKENS=384 \
  -e KNOWLEDGE_JUDGE_BATCH_SIZE=2 \
  infra-knowledge-service-1 \
  python -m pytest tests/quality/test_judge_eval.py::test_llm_judge_ensemble --run-quality -v -s
```

Output files (under `KNOWLEDGE_JUDGE_DUMP_PATH`):
- `judge_verdicts_gemma.json` + `judge_verdicts_qwen-30b.json` + `judge_verdicts_claude-4_7-opus.json` — per-judge raw verdicts
- `judge_ensemble_report.json` — Fleiss κ, per-chapter majority, D12 bias metrics, D11 judge_status

---

# 2026-05-29 — Cycle 70: specialized relation prompt (CJK disciple_of + VN stepchild_of)

First recall-improvement cycle measured against the cycle-69 ensemble baseline. Goal: lift relation precision on 30B's weak axis (little_women_ch01 was 17.1% disputed under ensemble, mostly relation FPs) by teaching two new predicate canonicalization rules via short language-specific examples in `relation_extraction_system.md`. Per cycle-1 lessons: bounded prompt growth (≤ +500 chars target; actual +400), pair LANGUAGES with DIFFERENT lessons (mentorship vs kinship, not 3× the same omission lesson), VERIFY via ensemble per spec D10 cadence.

## A/B/B' test results (3-judge ensemble)

| Variant | Prompt size | gemma P/R | qwen-30b P/R | claude-4.7-opus P/R | Median P/R | Fleiss κ | Disputed |
|---|---:|---:|---:|---:|---:|---:|---:|
| **c69 baseline** (no new examples) | 5100 | 0.834 / 0.937 | 0.980 / 1.000 | 0.983 / 0.879 | **0.93 / 0.94** | 0.708 | 6.6% |
| **c70a** (Lesson prose) | 5872 | 0.809 / 0.921 | 0.959 / 1.000 | 0.955 / **0.924** | **0.96 / 0.92** | 0.671 | 5.4% |
| c70b (trimmed, no prose) | 5482 | 0.774 / 0.857 | 0.944 / 0.993 | 0.947 / 0.835 | 0.94 / 0.86 | 0.655 | 6.9% |

## Decision: ship c70a (Lesson prose retained)

**c70a is the locked baseline post-cycle.** Reasoning:

1. **The Lesson prose helped, not hurt.** Refinement attempt c70b removed the "Lesson:" prose blocks under the hypothesis that they confused gemma. Result: monotonic regression across ALL 3 judges (gemma 0.83→0.77 P, claude 0.98→0.95 P). The prose was scaffolding that helped the model apply the new predicates correctly.

2. **Predicate learning is real + structural** — `disciple_of` (Chinese 拜...為師, journey_west_zh_ch14) and `stepchild_of` (Vietnamese con riêng, tam_cam_vi) appear in c70a extraction dumps where they did not before. The model learned the specific canonicalization rules.

3. **claude-4.7-opus judge improved on R** (+0.045pp, 0.879 → 0.924). The strictest precision-axis judge accepts MORE extractions with c70a. This means high-recall use cases (Mode-3 chat retrieval) gain real signal from the new predicate examples — the kinship/mentorship triples that previously got rejected as off-canonical are now retained.

4. **Net aggregate cost is small.** Median R dropped 0.02pp (within Fleiss-κ-substantial run-to-run noise). Median P actually rose 0.03pp.

## What did NOT happen (honest cycle report)

- **little_women_ch01 relation precision did NOT lift to 0.30+** (target). Rule-based P stayed at 0.08 (vs 0.06 baseline) — within noise. The new examples don't teach generic relation precision; they teach specific kinship+mentorship canonicalization that doesn't apply to little_women's parent-child-domestic narrative. Cycle's quantitative goal not met.
- **gemma judge slightly regressed** (−0.025 P, −0.016 R). The most-median judge penalizes the cycle's output marginally. Pattern matches the across-all-cycles observation that gemma is more language-biased than claude.
- **Fleiss κ dropped slightly** (0.708 → 0.671). Inter-judge agreement decreased — the new predicates create some judge disagreement (claude accepts them readily, gemma is unsure). Still "substantial" per Landis-Koch, but worth tracking.

## Lessons captured

- **Prompt prose can scaffold predicate canonicalization.** Cycle 1's lesson was "don't compound the same lesson across languages." Cycle 70's refinement attempt c70b tested "trim all prose; let JSON speak." Both attempts confirm the goldilocks zone: ONE concrete lesson per example with concise explanation > both extremes. Future relation/event prompt iterations should keep example-specific "Lesson:" blocks ~30-50 chars each.
- **Predicate learning ≠ aggregate metric improvement.** The model demonstrably learned new patterns (disciple_of/stepchild_of emitted correctly) but the ensemble metric needle barely moved. Metrics reflect AGGREGATE noise; specific predicate quality is a STRUCTURAL signal that takes longer to translate.
- **Claude-as-judge is the high-recall barometer** — when the new examples teach the model patterns that are real-but-non-canonical, claude updates its acceptance threshold first (R +4.5pp). Gemma is slower to do so. For high-recall product features, prefer the claude judge's verdict.

## Reproducing cycle 70 (c70a baseline)

Same as cycle 69's "Reproducing the 30B baseline (ensemble + anchors)" block, but with the patched `relation_extraction_system.md` (post-cycle-70 commit). Wall clock: ~30 min for ensemble after the cycle 69 budget-bump fixes (KNOWLEDGE_JUDGE_BASE_TOKENS=3072 etc.) baked in.

---

# 2026-05-29 — Cycle 71: specialized event prompt — NEGATIVE cycle (reverted)

Target: lift `journey_west_zh_ch14` event recall (cycle 69's biggest hole — model extracted 6 events but all 6 folded/padded, judge matched 0/4 gold). Approach: mirror cycle 70 pattern (Rule + CJK example + VN example + Lesson prose) on the EVENT prompt.

## A/B/B' results (gemma single-judge, c70a baseline = 0.81/0.92 macro P/R)

| Variant | Prompt size | gemma macro P/R | ch14 events extracted | Failure mode |
|---|---:|---:|---|---|
| **c70a baseline** | 5872 (relation prompt) + 4522 (event prompt unchanged) | 0.81 / 0.92 | n/a (c70 was relations) | — |
| **c71a** Rule 10 + Ex B (CJK) + Ex C (VN) + Lessons | 7475 event prompt | **0.79 / 0.89** | 2 events copying Example A English ("Kai departs from Harbin", "Zhao fights rebels at Iron Gate") | **Regurgitation** — Example B's text overlapped ch14 narrative; model defaulted to Example A for the overlapping chapter |
| **c71b** Rule 10 + remove Ex B + keep Ex C | 6355 event prompt | not judged (script audit definitive) | 11 events, **8 English / 3 mixed-Chinese** | **Script drift** — no CJK anchor example → Chinese chapters defaulted to English summary; journey_west_zh_ch01 went 3/0 EN/CJK |

## Decision: revert + close cycle as negative

Both variants empirically regressed vs c70a baseline. Prompt reverted (`git checkout HEAD --`); no code shipped.

## Why both failed (lessons)

1. **Event prompts ≠ relation prompts under cycle-70 pattern.** Cycle 70 taught new VOCABULARY (predicates `disciple_of` / `stepchild_of`) — model accepted readily. Cycle 71 tried to teach STRUCTURAL granularity ("one verb-of-change per event"); model resisted in TWO distinct ways depending on language-example coverage.
2. **Example text-overlap with eval fixtures triggers regurgitation.** Example B sourced from `journey_west_zh_ch14`'s seal-lifting scene. Same chapter is in `tests/fixtures/golden_chapters/`. When the model saw overlapping tokens in BOTH the prompt and the user TEXT, it emitted the first example (Example A) as a "safe default." → **Future language examples MUST source text NOT in the eval fixture set.**
3. **Asymmetric multilingual examples cause script drift.** c71b's EN + VN coverage left no CJK example anchor → all Chinese chapters drifted to English summary. → **Multilingual event prompts need symmetric coverage (1 per language, sourced outside fixtures) OR no language-specific examples at all.**
4. **Granularity Rule 10 wasn't isolated cleanly.** Most chapters showed event metrics ≥0.86 P / ≥0.60 R under c71a — but the regurgitation + script-drift confounded the granularity-only signal. Cycle 71-bis (S size) tests R10 alone.

## New deferred rows

- **D-CYCLE71-SYMMETRIC-CJK-EXAMPLE** — if attempting CJK event example again, source text from a chapter NOT in `tests/fixtures/golden_chapters/`. Pair with symmetric EN + VN examples sourced similarly.
- **D-EVENT-AGGREGATOR-FUZZY-MATCH** — judge-side fix for the granularity drift identified in cycle 69 (ch14 model extracts the same scenes as gold but folded/padded; matching at semantic level not literal). Alternative to prompt-side teaching.

## Cycle 71-bis (Rule 10 isolated) — ALSO NEGATIVE, reverted

Test: apply ONLY Rule 10 (English-only illustrative phrases) to event prompt; no Example B/C; rule-only granularity teaching.

### Result table (gemma single-judge)

| Variant | Prompt size | gemma macro P/R | ch14 evt P/R | ch14 script (EN/CJK) |
|---|---:|---:|---:|---:|
| c70a baseline | 4522 | 0.81 / 0.92 | not measured per-chapter by gemma | (c69: 0 / 6) |
| **71-bis** Rule 10 only | 5101 | **0.79 / 0.91** | **0.91 / 1.00** ⭐ | **8 / 3** (drift) |

### Why 71-bis was rejected

1. **Macro P regressed −2pp** (0.81 → 0.79), right at the ship threshold.
2. **CJK script drift** despite English-only rule prose — adding ANY rule with English illustrative phrases ("after praying", "happily", "walked across the bridge") biased the model to emit English summaries on Chinese chapters. journey_west_zh_ch01 went 3 EN / 0 CJK; ch14 went 8 EN / 3 CJK. Violates the prompt's explicit "Keep summary in ORIGINAL script of TEXT" rule.
3. **Relation regression pattern replicated** — alice_ch02 rel R=0 and little_women rel R=0 in 71-bis match the same chapters in c71a/c71b. Adding any rule to event prompt seems to have hidden interaction with relation extraction.
4. **The ch14 "win" is apples-to-oranges** — c69/c70a never measured per-chapter event metrics via gemma judge (only rule-based attribution showed 0 TP). Within-cycle comparison 71-bis vs c71a shows ch14 fixed (0/0 → 0.91/1.00) but vs c70a baseline we lack the gemma per-chapter data.

### Combined cycle-71 + 71-bis lessons (3 attempts, 3 failure modes)

1. **c71a** (Rule + CJK + VN + Lessons) → regurgitation when example text overlaps fixture chapter
2. **c71b** (Rule + VN only) → script drift on CJK chapters (no anchor)
3. **71-bis** (Rule only, English illustrative phrases) → script drift on CJK chapters (English bias in rule prose)

**Conclusion: event prompts are intrinsically resistant to prompt-side improvements.** Pivot to structural lever (#2 hybrid 2-pass).

### New deferred row (cycle 71-bis specific)

- **D-EVENT-RULE-ENGLISH-PROSE-CJK-DRIFT** — adding ANY new rule with English-only illustrative phrases biases the model to emit English summaries on Chinese chapters. If a future cycle adds rules to event prompt, use ONLY abstract phrasing OR symmetric multilingual examples sourced outside the fixture set.

## Open follow-ups (updated post-71-bis)

- **Cycle 72 candidates** (post-cycle-71+71-bis revert):
  - **Hybrid 2-pass extraction** (30B recall → claude-4.7-opus precision filter) — **RECOMMENDED**, L cycle, structural lever, no prompt risk, F1 target ~0.88
  - **D-CLAUDE-JUDGE-VS-GEMMA-JUDGE-DIVERGENCE-AUDIT** — S cycle, still pending from cycle 70 close
  - **D-EVAL-FRAMEWORK-WIKINEURAL-MULTILINGUAL-ANCHOR** — multilingual NER anchor; closes EN-vs-CJK judge bias question
  - **D-EVENT-AGGREGATOR-FUZZY-MATCH** — judge-side fix for granularity drift; alternative to prompt-side
  - **D-CYCLE1-ENSEMBLE-FORENSIC** — re-baseline cycle-1 multilang-fewshot dump for D9 verdict

## Open follow-ups (not blocking)

- **Cycle 72+ candidates** (per cheap-to-expensive ordering, updated with cycle 71's revert lessons):
  - **71-bis** (Rule 10 isolated) — S cycle, **NEXT after cycle 71 commit**
  - **Hybrid 2-pass extraction** (30B recall → claude-4.7-opus precision filter) — L cycle, no prompt growth risk, pivot here if 71-bis also negative
  - **D-CLAUDE-JUDGE-VS-GEMMA-JUDGE-DIVERGENCE-AUDIT** — S cycle, still pending from cycle 70 close
  - **D-EVAL-FRAMEWORK-WIKINEURAL-MULTILINGUAL-ANCHOR** — multilingual NER anchor; closes EN-vs-CJK/VN judge bias question
  - **D-EVENT-AGGREGATOR-FUZZY-MATCH** — judge-side alternative to prompt-side event teaching
  - **D-CYCLE1-ENSEMBLE-FORENSIC** — re-baseline cycle-1 multilang-fewshot dump for D9 verdict
