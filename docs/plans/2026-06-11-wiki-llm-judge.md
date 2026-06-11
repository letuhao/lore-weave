# Plan — D-WIKI-M8-EVAL-PLUS Phase 1 (wiki LLM-judge groundedness, on-demand)

**Date:** 2026-06-11 · **Branch:** `wiki/phase2-change-control` · **Size:** L (cross-service, SDK + learning + knowledge)

## Goal
An LLM-judge that scores AI wiki articles for **groundedness** [0,1], **flag-OFF by
default**, persisting to learning `quality_scores`. Phase 1 = the shared judge core +
the **on-demand** path (human runs `run_wiki_eval --judge` = the controlled "plan").
Phase 2 (next) = automatic-sampled. Distinct from CanonVerifier (rule-based flags); this
is a semantic claim-vs-source score. Mirrors `judge_translation_fidelity`.

## Changes

### SDK — `sdks/python/loreweave_eval/llm_judge.py`
`judge_wiki_groundedness(client, *, judge_model, user_id, model_source, article_text,
sources) → GroundednessVerdict|None` — one judge LLM call (system prompt: rate how well
the article's claims are SUPPORTED by the provided sources, 1.0=fully grounded …
0.0=hallucinated; JSON `{score, reason}`). Best-effort None on empty/failed/unparseable/
out-of-range. `GroundednessVerdict(score, reason)`. Export in `__all__`. Reuses
`_call_judge` + `_extract_json_object`.

### learning-service
- `app/config.py`: `wiki_llm_judge_enabled: bool = False`, `wiki_llm_judge_model_ref: str
  = ""`, `wiki_llm_judge_model_source: str = "user_model"`, `wiki_llm_judge_user_id: str
  = ""` (fallback owner).
- `app/db/online_wiki_judge.py`: `run_wiki_judge(client, *, article_text, sources,
  judge_model, model_source, user_id)` → verdict; `persist_wiki_judge(pool, *, article_id,
  book_id, user_id, verdict, judge_model, run_id)` → `persist_consumed_score(
  target_kind='wiki_article', metric_name='wiki_llm_judge_groundedness', value=score,
  source='auto', origin_service='wiki-judge', origin_event_id=f'{run_id}:{article_id}',
  comment={reason, judge_model})`. (run_id makes each eval run distinct, idempotent within.)
- `app/db/eval_repo.py`: seed `wiki_llm_judge_groundedness` (numeric [0,1]).
- `app/routers/wiki_judge.py`: `require_internal_token` dep (header vs settings) +
  `POST /internal/learning/wiki/judge` body `{run_id?, judge_model?, model_source?,
  articles:[{article_id, book_id, user_id, article_text, sources[]}]}` → resolve the judge
  model (request override OR settings when `wiki_llm_judge_enabled`); if none → `{enabled:
  false, scored:0}` (inert). Else build the judge client, judge+persist each, return
  `{run_id, scored, scores:[{article_id, score}]}`. Best-effort per article (a judge miss
  → skipped, not fatal).
- `app/main.py`: include the router.

### knowledge-service — `app/benchmark/wiki/run_wiki_eval.py`
`--judge` flag (+ `--judge-model`, `--judge-min` gate threshold). When set: for each AI
article it already fetches, collect the body plaintext + the stored cited snippets
(`collect_citation_marks`), POST the batch to the learning judge endpoint
(`LEARNING_INTERNAL_URL` + internal token), add `groundedness` (mean + per-article) to the
report; `--gate` fails if mean < `--judge-min`. No judge model / disabled → reported as
skipped.

## Tests
- SDK: `judge_wiki_groundedness` parses a score, clamps out-of-range→None, empty→None
  (mock JudgeLLMClient).
- learning: `run_wiki_judge` (mock client→verdict) + `persist_wiki_judge` (FakeConn, the
  quality_scores row shape + dedup key); the endpoint — disabled→inert, model-provided→
  judges+persists, per-article best-effort.
- knowledge: `run_wiki_eval --judge` posts the right batch + folds groundedness into the
  report (mock the learning HTTP call).

## Out of scope (Phase 2 / follow-ups)
Automatic-sampled judging of `wiki.generated` (rate-controlled) → next milestone. Judging
against FULL re-gathered sources (Phase 1 uses the stored cited snippets). A discrimination
probe / Fengshen golden corpus.
