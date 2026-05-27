# Plan — Eval framework overhaul (XL cycle, foundation + integration split)

**Spec:** [docs/specs/2026-05-27-eval-framework-overhaul.md](../specs/2026-05-27-eval-framework-overhaul.md)
**Size:** XL (~13 files, 8 logic blocks, 1 side effect — Docker rebuild)
**Sessions:** ~2 (foundation in session 1, integration + re-baseline in session 2 if needed)

## DAG + checkpoint seam

```
FOUNDATION (session 1) ──────────────────── checkpoint commit ──────────── INTEGRATION (session 1 or 2)
─ install deps + Dockerfile                                                ─ wire DeepEval into test_eval_with_deepeval.py
─ download CoNLL + DocRED via HF datasets                                  ─ modify llm_judge.py for multi-judge mode
─ write deepeval_metrics.py (3 G-Eval metrics)                             ─ modify test_judge_eval.py for ensemble call
─ write judge_ensemble.py (Fleiss κ + majority)                            ─ write test_eval_with_deepeval.py
─ write anchor_runner.py (CoNLL + DocRED + seqeval)                        ─ run anchor on 30B
─ write test_anchor_eval.py                                                ─ run ensemble re-judge on 3 dumps
─ unit-test anchor_runner + judge_ensemble in isolation                    ─ document in QUALITY_EVAL_BASELINES.md
                                                                           ─ commit + push final
```

Per `feedback_xl_cycle_natural_checkpoint_pattern`: foundation is isolated logic (modules, fixtures, data); integration touches test orchestration. Mid-BUILD checkpoint commit between them is the safe seam.

## File-by-file action

### Foundation (commit 1 — XL, ~half-day) — sub-checkpoints recommended (LOW-11)

**Sub-checkpoint 1a (deps + Dockerfile + HF smoke, ~1h):** lands files 1-2 + a 5-line smoke that proves `from datasets import load_dataset; load_dataset("conll2003", split="test")` returns rows inside the rebuilt container. If this breaks, ONLY 2 files revert, not 7. Sub-commit optional but lower-risk for the XL cycle.

**Sub-checkpoint 1b (modules + unit tests, ~3-4h):** lands files 3-7. Builds on the proven dep base.

| # | File | Action | Notes |
|---|---|---|---|
| 1 | `services/knowledge-service/requirements.txt` | MODIFY +4 deps | **Pinned versions (LOW-10):** `deepeval==2.5.0`, `seqeval==1.2.2`, `datasets==2.21.0`, `krippendorff==0.7.0` (current latest stable as of cycle date — pin for reproducibility; DeepEval especially has rapid API churn). **Image bloat note (LOW-12):** realistic added container size ~500MB-1GB including pyarrow + sentence-transformers + pydantic v2 + openai-python transitives — not the ~130MB the spec's bare-dep size implied. Document for downstream image-size monitoring. |
| 2 | `services/knowledge-service/Dockerfile` | MODIFY | Pre-download CoNLL+DocRED at BUILD time to cache in image (avoids runtime network — Risk 2 mitigation): `ENV HF_DATASETS_CACHE=/app/.hf_datasets_cache` + `RUN python -c "import os; os.environ['HF_DATASETS_CACHE']='/app/.hf_datasets_cache'; from datasets import load_dataset; load_dataset('conll2003', split='test'); load_dataset('docred', split='validation')"` after pip install. **Cache path (LOW-9):** override the HF default `~/.cache/huggingface/` via the env var so the cache lands at a known image path, not in the home dir which isn't in our COPY layer policy. |
| 3 | `services/knowledge-service/tests/quality/anchor_runner.py` | NEW | `run_conll2003_anchor(extractor, n_samples)` + `run_docred_anchor(extractor, n_samples)`. Returns aggregate F1 + per-sentence breakdown + **the sanity-floor check per spec HIGH-1**: emits `passes_sanity_floor: bool` based on (F1 ≥ 0.10 AND N_extracted ≥ 0.1 × N_gold). Uses `seqeval` strict mode for CoNLL (Risk 4 case-sensitive whole-word alignment). For DocRED, unlabeled-F1 (triple existence) — not typed-mapping. |
| 4 | `services/knowledge-service/tests/quality/judge_ensemble.py` | NEW | `ensemble_judge(judges: list[str], dump_root: Path) -> EnsembleReport` — calls existing `judge_chapter()` once per judge sequentially (LM Studio JIT model swap each time), persists per-judge verdicts to `judge_verdicts_<judge_uuid_short>.json`, computes Fleiss κ + per-item majority + **D11 ensemble-failure handling** (judge_status per judge: complete / incomplete / failed; Fleiss κ basis = items where all 3 judges produced verdicts; never silent-downgrade to 2-judge majority). Computes **D12 bias metrics** (strictness_gap, language_bias, rp_bias) per judge. Emits `judge_ensemble_report.json`. |
| 5 | `services/knowledge-service/tests/quality/deepeval_metrics.py` | NEW | 3 `GEval` metric definitions per spec D5; `NarrativeEntityCoverage` pinned to gemma UUID, `RelationFactualGroundedness` pinned to 30B UUID, `EventActionRecall` pinned to claude-4.7-opus UUID. Each accepts a `judge_client` (existing `LLMClient`) at construction. |
| 6 | `services/knowledge-service/tests/quality/test_anchor_eval.py` | NEW | `pytest.mark.quality` markers. Runs CoNLL + DocRED anchors against env-supplied extractor model UUID. Prints aggregate F1 + writes `anchor_report.json` under `KNOWLEDGE_EVAL_DUMP_PATH`. **Assertion change vs prior plan:** assert `passes_sanity_floor is True` from the anchor_runner output. F1 number itself remains informational; sanity floor is the hard gate. |
| 7 | `sdks/python/tests/test_extraction/test_judge_ensemble_unit.py` | NEW | Pure-unit test for `judge_ensemble.py`'s Fleiss κ + majority vote + **D11 ensemble-failure paths** (judge_status complete/incomplete/failed, incomplete-judge handling in κ basis, no silent 2-judge fallback) + **D12 bias metric formulas**. Mock 3 judge outputs across known cases:  all-agree, 2/3-agree, all-disagree, judge-incomplete, judge-failed, judge-zero-verdicts. ~10-12 test cases. |

**Foundation acceptance (HIGH-1 + HIGH-2 reflected):** all 7 files exist; `pytest sdks/python/tests/test_extraction/test_judge_ensemble_unit.py` passes (including the new failure-mode test cases); `docker compose build knowledge-service` succeeds with new deps + HF cache pre-downloaded; `pytest tests/quality/test_anchor_eval.py --run-quality` runs against 30B extractor and passes the **sanity floor** (F1 ≥ 0.10 AND N_extracted ≥ 0.1 × N_gold), NOT just "any F1 value". This is the false-negative-trap fix.

### Integration (commit 2 — M, ~3-4h)

| # | File | Action | Notes |
|---|---|---|---|
| 8 | `services/knowledge-service/tests/quality/llm_judge.py` | MODIFY | (a) Extend `judge_chapter()` signature: `judge_models: str | list[str]` (str defaults to existing behavior; list triggers ensemble loop via `judge_ensemble.py`). Backward-compatible. (b) **MED-8 fix:** refactor module-level `_judge_client` singleton (or wherever the asyncio teardown leak lives — see D-JUDGE-EVAL-ASYNCIO-TEARDOWN) into a function-scoped fixture or explicit per-call client construction + `await client.aclose()` per test. This unblocks the discrimination + extraction tests from running in the same pytest invocation without the closed-event-loop crash. Add unit test asserting client lifecycle: client created → used → closed in one async-with block. |
| 9 | `services/knowledge-service/tests/quality/test_judge_eval.py` | MODIFY | Add env `KNOWLEDGE_EVAL_ENSEMBLE_JUDGES` (comma-sep UUIDs); when present, swap from single-judge to ensemble call. Existing single-judge default unchanged. Per MED-8: rewrite `test_judge_discriminates_fabricated_items` + `test_llm_judge_extraction_quality` to each use a function-scoped client fixture (no module-level state). Confirm BOTH tests now pass in the same pytest invocation (the bug closes here). |
| 10 | `services/knowledge-service/tests/quality/test_eval_with_deepeval.py` | NEW | DeepEval test wrapping `extract_entities + gather_relations_events_facts` + scoring via `deepeval_metrics.py`. Runs each chapter as a DeepEval `LLMTestCase`. Outputs DeepEval's standard JSON report. **Uses the MED-8 fixed client lifecycle pattern from #8 — function-scoped client, explicit aclose** so the new test doesn't replicate the same bug class. |
| 11 | `services/knowledge-service/eval/QUALITY_EVAL_BASELINES.md` | MODIFY | New "Eval framework overhaul" section. Re-baseline tables for 3 dumps (claude / 30B / cycle-1) with: per-judge P/R, ensemble majority P/R, Fleiss κ, anchor F1 (CoNLL/DocRED on each extractor variant). **MED-3 re-baseline order:** 30B-baseline + 30B-cycle1 done TOGETHER first (they share the same chapter set so the 3-judge sweep can be done in one continuous run per judge — cuts wall-clock vs running each dump separately), then claude-4.7-opus dump optional as next session. |
| 12 | `docs/sessions/SESSION_PATCH.md` | MODIFY | Header metadata + new deferred rows (D-EVAL-FRAMEWORK-CLOUD-JUDGE follow-up + D-EVAL-FRAMEWORK-WIKINEURAL-MULTILINGUAL-ANCHOR if ensemble shows CJK/VN gap + D-JUDGE-EVAL-ASYNCIO-TEARDOWN closes here per MED-8). |
| 13 | `docs/sessions/SESSION_HANDOFF.md` | MODIFY | New session entry + status snapshot of architectural-improvement track. |

**Integration acceptance:**
- `pytest tests/quality/test_eval_with_deepeval.py --run-quality -v -s -k <one chapter>` produces DeepEval report with 3 G-Eval scores
- `KNOWLEDGE_EVAL_ENSEMBLE_JUDGES=$gemma_uuid,$30b_uuid,$claude_uuid pytest tests/quality/test_judge_eval.py --run-quality` produces `judge_ensemble_report.json` on at least 1 dump
- D9 decision rule applied → cycle-1 question answered (extract regression vs scoring artifact)
- Memory updated with the outcome

## Per-cycle smoke vs ensemble cadence (operational)

- **In-cycle iteration smokes:** continue using single-judge gemma via existing `test_judge_eval.py` (~20 min). Fast feedback.
- **Ensemble re-lock triggers** (per spec D10):
  - New extractor model registered → ensemble baseline before use
  - Cycle touches prompts/aggregator/scoring → ensemble re-lock on affected dimension
  - Quarterly drift check
  - Before any "ship to production" decision

## Risk-aware sequencing (MED-3 reordered)

Per spec Risk 5 (ensemble wall clock ~2-3h per dump × 3 dumps = ~6-9h), the re-baselining work is BIG. Reordered to answer the cycle-1 open question FIRST:

- **Re-baseline 30B-baseline + 30B-cycle1 dumps TOGETHER** (they share the same 9 chapters; each judge runs over both dumps in one continuous LM Studio session per judge → 3 judge swaps total, not 6). Total: ~3h. **This produces the D9 decision-rule data directly.**
- **Re-baseline claude-4.7-opus dump SEPARATELY** — for the precision-champion ensemble number. Time: ~2h. May defer to next session if foundation+integration alone consumed a full day.
- **Anchor CoNLL+DocRED runs** alongside the 30B-baseline + 30B-cycle1 re-baseline — run on BOTH extractor configurations (30B with baseline prompts AND 30B with cycle-1 prompts, on the CoNLL/DocRED examples). Provides D9 anchor cross-check signal for the English subset. Additional ~30-45 min per extractor config.

**Time-buffer note (LOW-13):** the "1.5 working days" total includes the 6-9h re-baseline window. LM Studio model swaps under load have produced HTTP 500 retries in this session (3-judge sweep means 6 swaps when both dumps are bundled per MED-3; each swap adds ~30s + risk of transient 500). Buffer 25-50% on the re-baseline phase = realistic 3-4h instead of 3h. Total realistic estimate: **1.5-2 working days**.

## Memory anchors

- `feedback_xl_cycle_natural_checkpoint_pattern` — foundation/integration split with mid-BUILD commit
- `feedback_design_checkpoint_commit_separates_design_from_implementation` — spec + plan as commit-able artifact pre-BUILD (this commit lands before any code)
- `feedback_review_impl_on_design_cycles` — recommend /review-impl on the spec doc before foundation BUILD starts
- `feedback_mock_only_coverage_hides_crossservice_bugs` — anchor benchmarks + multi-judge IS the live-smoke for our scoring system

## Open follow-ups (deferred to post-cycle)

- **D-EVAL-FRAMEWORK-CLOUD-JUDGE** — add cloud Claude as 4th judge after first ensemble run surfaces meaningful local-judge variance. Cost: ~$1-3/full-judge-run.
- **D-EVAL-FRAMEWORK-WIKINEURAL-MULTILINGUAL-ANCHOR** — multilingual NER anchor (CJK + VN). Defer until English anchors prove the methodology.
- **D-EVAL-FRAMEWORK-DOCRED-TYPED-RELATIONS** — typed-F1 instead of unlabeled-F1 against DocRED (requires our 28-predicate → DocRED 96-relation mapping table). Defer; unlabeled-F1 is sufficient anchor.
- **D-EVAL-FRAMEWORK-CI-INTEGRATION** — wire DeepEval reports into a scheduled CI run. Defer until GH Actions or similar lands.
- **D-EVAL-FRAMEWORK-USER-QUERY-BENCHMARKS** — downstream Mode-3 retrieval quality evaluation (not extraction). Different cycle.

## Estimated effort

| Phase | Time |
|---|---|
| Foundation BUILD | ~4-5h |
| Foundation VERIFY (unit tests + 1 anchor smoke) | ~30 min |
| Checkpoint commit | 5 min |
| Integration BUILD | ~3-4h |
| Re-baseline 30B (single ensemble run) | ~2h |
| Re-baseline cycle-1 (single ensemble run) | ~2h |
| Doc update + SESSION + commit | ~30 min |
| **Total realistic** | **~12-14h ≈ 1.5 working days** |

User may opt to checkpoint after foundation (commit 1) and resume integration in a fresh session per `feedback_xl_cycle_natural_checkpoint_pattern`.
