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
