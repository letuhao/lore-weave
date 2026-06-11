# Plan — D-WIKI-M8-LEARNING-CONSUMER (wiki feedback flywheel: consume half)

**Date:** 2026-06-11 · **Branch:** `wiki/phase2-change-control` · **Size:** L (cross-service)

## Goal
Consume the `wiki.corrected` / `wiki.suggestion_reviewed` events (glossary M8, currently
EMITTED but dropped) in learning-service → `corrections` + `quality_scores`
(target='wiki_article'). PO: **collect on by default, scoring deferred, just record the
info, cost-controlled via a toggle.** The few-shot injection into generation and the
LLM-judge scoring stay deferred (D-WIKI-M8-FEWSHOT / D-WIKI-M8-EVAL-PLUS).

## Findings that shape it
- Learning already subscribes to `loreweave:events:glossary` (where the wiki events land,
  `aggregate_type='glossary'`); only handlers are missing.
- The `corrections` table is **redact-by-default by design** (structural + content-HASHES,
  no raw-prose columns). The gold AI→human text is **already retained in glossary
  `wiki_revisions`**, reachable by `article_id` — so "store raw" needs NO copy: the
  correction row's `target_id=article_id` is the pointer; the deferred few-shot half
  fetches the pair from glossary on demand. (No raw-capture flag / glossary endpoint.)
- `split_snapshot`/`derive_diff_class` default an unknown `target_type` to structural →
  no schema/classification change for `wiki_article`.
- **Gap:** the M8 events omit `user_id`, which `_persist_correction` +
  `persist_consumed_score` REQUIRE (DLQ otherwise) → add it at the glossary emit.

## Changes

### glossary-service (tiny)
- `internal/api/outbox.go`: `UserID string json:"user_id"` on `wikiCorrectedPayload` +
  `wikiSuggestionReviewedPayload`.
- `internal/api/wiki_handler.go`: set `UserID: userID.String()` at both emit sites
  (`patchWikiArticle` wiki.corrected, `reviewWikiSuggestion` wiki.suggestion_reviewed) —
  the owner is already resolved (requireUserID + verifyBookOwner).

### learning-service
- `app/config.py`: `wiki_learning_enabled: bool = True` (collect master toggle).
- `app/events/handlers.py`:
  - `handle_wiki_corrected` — flag-gated (off → ack+skip); `_persist_correction(
    target_type='wiki_article', op='human_edit', before={author_type:'ai',
    generation_status:prior}, after={author_type:'human'})` → diff_class 'other' (a
    non-None after avoids the spurious-drop misclassification); user_id from payload.
  - `handle_wiki_suggestion_reviewed` — flag-gated; only when `was_ai_generated`;
    `persist_consumed_score(target_kind='wiki_article',
    metric_name='wiki_suggestion_reviewed', value=1.0 accept / 0.0 reject, source='human')`,
    suggestion_id + action in the comment.
- `app/db/eval_repo.py`: seed `wiki_suggestion_reviewed` (numeric [0,1]).
- `app/main.py`: register both event types.

### Tests (learning, mocked pool / persist helpers)
- wiki.corrected → a 'wiki_article'/'human_edit' correction with diff_class 'other'; the
  flag-off path acks without persisting; empty outbox_id / missing user_id → raises (DLQ).
- wiki.suggestion_reviewed → a `wiki_suggestion_reviewed` score (accept=1/reject=0);
  non-AI article → skipped; flag-off → skipped.
- glossary: M8 emit tests assert the new `user_id` field travels (extend existing).

## Deferred (tracked, with reserved toggles)
- **D-WIKI-M8-FEWSHOT** — inject gold AI→human pairs as few-shot exemplars into
  `prompt.py`/`generate.py` (fetches raw from glossary `wiki_revisions` by article_id).
- **D-WIKI-M8-EVAL-PLUS** — the LLM-judge wiki-quality scoring (expensive; flag-gated when
  enabled, mirrors `_maybe_judge_translation`).
- A UI toggle for the cost flags (env/config is the toggle for now).

## VERIFY
Cross-service (glossary + learning). go build/vet + glossary api suite (emit tests);
learning pytest (handlers). Live-smoke deferred to D-WIKI-M8-LEARNING-LIVE-SMOKE
(inject a wiki.corrected onto the stream → a corrections row).
