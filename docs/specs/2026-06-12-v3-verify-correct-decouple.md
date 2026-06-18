# Spec — V3 verify/correct decouple (Wave 5 / 2b-T3b, XL)

## Goal

Decouple the **V3 pipeline** (`pipeline_version='v3'`) so a worker coroutine is not
pinned across its LLM waits — completing the LLM-execution event-driven re-architecture
(Phase 2b). V3 today runs fully synchronously: block-translate → verify/correct loop →
`_finalize_chapter`. After this wave, V3 runs as two chained decoupled stages and the
chapter finalizes **only after** verify/correct (defer-finalize — PO-approved, faithful
to the current translate→verify→finalize order).

## Current V3 flow (sync — `v3/orchestrator.py`)

```
translate_chapter_blocks_v3:
  1. compute extras (knowledge_brief, romanization, timeline, prev_memo) → extra_system
  2. block-translate (session_translator.translate_chapter_blocks, M3 batching)   [sync, multi-batch LLM]
  3. [optional] 2-pass cold-start re-translate                                     [sync, LLM]
  4. _verify_correct_persist:                                                      [sync loop]
       round 0: rule-verify (det) + LLM-verify (use_llm) → persist issues
       while HIGH && round<max:  corrector fan-out (LLM/block) → keep-if-improved (det) → re-verify → persist
       update rollup + record_stage("translation.verify")
  → caller _finalize_chapter (corrected body + chapter.translated + translation.quality)
```
`use_llm = qa_depth != 'rule_only'`; `max_rounds = ≤5 if thorough else 1`.

## Decoupled design (mode-chaining)

**Stage 1 — block-translate** reuses the existing `decoupled_block_translate` engine
(mode='block'), with the V3 extras computed up front and passed as `extra_system`, and
the V3 config carried in resume_state (`rs['v3']`). On block completion the consumer's
finalize_cb sees `rs['post_block']=='v3_verify'` and, instead of `_finalize_chapter`,
**starts the v3_verify SM** (no finalize yet).

**Stage 2 — verify/correct** is a NEW pure SM `workers/v3/decoupled_v3_verify.py`
(mode='v3_verify'), driven by terminal events through the existing T2 consumer:

```
START (after block): rule-verify (det, inline) → persist round-0 rule issues
   ├─ use_llm  → submit LLM-verify  → stage=VERIFY
   └─ rule_only → evaluate HIGH from rule issues directly

VERIFY terminal: parse LLM issues (cap high→med) + merge rule issues → report; persist round issues
   ├─ HIGH && rounds_used<max → submit corrector fan-out (1 job/flagged block) → stage=CORRECT
   └─ else → FINALIZE

CORRECT terminal (fan-in): fold each corrected block; when all folded →
   keep-if-improved (det rule-verify per block) → update draft_texts/result_blocks;
   rounds_used++ ; re-verify:
     ├─ use_llm  → submit LLM-verify (round N) → stage=VERIFY
     └─ rule_only → re-rule-verify (det) → evaluate HIGH → CORRECT or FINALIZE

FINALIZE: update rollup (quality_score, unresolved_high, qa_rounds_used) + record_stage
   + _finalize_chapter(corrected result_blocks) → body + chapter.translated + translation.quality
```

The fan-in (corrector) + the conditional LLM-verify + the bounded loop mirror the WX
recovery/filter fan-out + the trio fan-in, under the same `SELECT … FOR UPDATE`
race-guard already in the T2 consumer/engines.

## Seams (mirror WX-T2)

Add pure submit/parse seams so the shell submits fire-and-forget + parses on terminal,
and the SYNC path calls them (byte-identical):
- `llm_verifier.py`: `build_verify_submit_kwargs(...)` + `parse_verify_job(job)` (→ reuse `parse_issues`).
- `corrector.py`: `build_corrector_submit_kwargs(...)` + `parse_corrector_job(job)`.

## resume_state (mode='v3_verify')

Carries: `result_blocks` (serialized, mutated by corrections) · `source_texts`/`draft_texts`
{idx:str} · `cmap` (verified glossary map) · `glossary_prompt_block` · `knowledge_brief` ·
`source_lang`/`target` · `verifier_model` [src,ref] · `qa_depth`/`use_llm`/`max_rounds` ·
`msg` essentials (user_id, model_source, model_ref) · `stage` (VERIFY|CORRECT|FINALIZE) ·
`round`/`rounds_used` · `verify_job` · `corrector_jobs` {idx:job_id} · `rule_issues` (round
accumulator) · the chapter finalize context (ct_id, pipeline_version, indices, etc.).

## Integration points

- `chapter_worker._process_chapter`: add a v3 decouple branch (`flag && v3 && cold_start_mode!='two_pass'`)
  → `decoupled_v3_block_start` (computes extras + glossary + seeds `rs['v3']` + `post_block='v3_verify'`,
  then `decoupled_block_translate.start_chapter_blocks`). Else sync v3 (unchanged).
- `llm_terminal_consumer`: dispatch `mode=='v3_verify'` → `decoupled_v3_verify.resume`;
  the block finalize_cb branches on `rs['post_block']`.

## Scope boundaries (deferred)

- **`D-V3-DECOUPLE-COLDSTART-2PASS`**: the 2-pass cold-start re-translate (glossary-less +
  `cold_start_mode='two_pass'`) stays SYNC — those jobs fall back to the sync v3 path
  (the decouple gate excludes them). Narrow (cold-start two-pass only).
- `translation_quality` event + rollup parity: emitted at the v3_verify FINALIZE, same as sync.

## Acceptance

V3 chapters with decouple on run block→verify→correct→finalize off terminal events; the
chapter finalizes only after verify/correct (defer-finalize); rule_only/standard/thorough
qa_depth all honored; bounded ≤5 rounds; idempotent + FOR-UPDATE-safe; byte-identical
staging via the seams; inert when the flag is off or for non-v3 / cold-start-two-pass jobs.
Live-smoke = a real v3 chapter end-to-end (`D-V3-DECOUPLE-LIVE-SMOKE`).
