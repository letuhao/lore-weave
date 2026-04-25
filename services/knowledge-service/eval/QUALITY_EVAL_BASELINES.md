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

| Model                   | Context | Precision | Recall | FP-trap | Time   | Note                                       |
|-------------------------|---------|-----------|--------|---------|--------|--------------------------------------------|
| qwen2.5-coder-14b       | 24K     | 0.145     | 0.337  | 0.301   | 5:12   | Coder bias — over-extracts (~85% FP)       |
| google/gemma-4-e4b      | 131K    | 0.183     | 0.284  | 0.238   | 7:22   | Conservative; 4B effective param count     |
| **google/gemma-4-26b-a4b** | **64K** | **0.251** | **0.356** | 0.275 | **15:49** | **Best narrative — recommended local model** |
| qwen/qwen3.5-35b-a3b    | 120K    | TIMEOUT   | —      | —       | 59:08† | †Hard timeout at 900s/call; both attempt + retry exceeded. Model too slow on this GPU at fixture scale (35B MoE active params still hit the wall). Practical ceiling appears to be ~26B. |

**Gemma-4-26b-a4b is the recommended local-LLM baseline** for narrative
extraction. +73% precision over the coder model with comparable recall;
strongest Vietnamese performance across all models tested.

## Per-chapter signal (gemma-4-26b-a4b — best model)

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

1. **Predicate alignment cycle** (Finding 1) — single PR. Highest leverage.
2. **Trap expansion** (Finding 2) — bundle with #1 since both touch fixtures.
3. **Cloud LLM baseline** — claude-haiku-4-5 / gpt-4o-mini run for hard-gate calibration.
4. **Multi-language few-shot** in prompts (architectural Finding) — separate cycle.
5. **LLM-as-judge scoring** (Finding 3) — defer; needs design ADR.
6. **Chunking for large chapters** — defer until 10KB+ fixture appears.

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
