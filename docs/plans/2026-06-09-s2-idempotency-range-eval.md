# S2 — translation idempotency + knowledge range + eval per-user

> **Slice:** S2 of the Auto-Draft Factory. Parent: [`2026-06-08-auto-draft-factory-architecture-readiness.md`](2026-06-08-auto-draft-factory-architecture-readiness.md).
> **Size:** XL · **Mode:** v2.2 (no AMAW, PO-chosen) · one loom A+B+C.
> **PO (CLARIFY 2026-06-09):** skip emits a done-signal so a resumed campaign converges; v2.2.

Closes **G3** (translation double-spend — reproduced live), **G2 / D-K16.2-02b** (knowledge ignores chapter_range), and folds **D-EVAL-JUDGE-PER-USER**.

---

## The PO-locked principle (idempotency)

Re-translating an already-successfully-translated chapter, when the user didn't ask, is a **bug** (wasted spend). Declarative model: *ensure (chapter, lang) is translated*. Only **three** valid (re)translate triggers — **never-translated · inputs-changed (stale) · explicit force**; everything else SKIPS.

```
to-do(chapter, lang) =
  NOT (active version exists AND status='completed' AND is_glossary_stale=false)
  OR force_retranslate
```

The signals already exist (S1 readiness audit): `active_chapter_translation_versions` (PK `(chapter_id,target_language)` → the active version), `chapter_translations.status` (`completed`/`failed`), `chapter_translations.is_glossary_stale` (M5c/M6b: glossary changed since translation). Nothing in the translate flow gates on them today — the coordinator fans out **every** id.

---

## A. Translation idempotency — `_resolve_and_create_job` (the shared core)

The filter lives in `_resolve_and_create_job` (translation `routers/jobs.py`) so **both** the public route and the S1 internal dispatch get it.

1. New `CreateJobPayload.force_retranslate: bool = False` (+ same on `InternalDispatchPayload`).
2. After `target_language` is resolved, classify the requested `chapter_ids`:
   ```sql
   -- SKIP set: fresh successful active translations for this language.
   SELECT acv.chapter_id
   FROM active_chapter_translation_versions acv
   JOIN chapter_translations ct ON ct.id = acv.chapter_translation_id
   WHERE acv.target_language = $1
     AND acv.chapter_id = ANY($2::uuid[])
     AND ct.status = 'completed'
     AND ct.is_glossary_stale = false
   ```
   `todo = chapter_ids − skip` (force_retranslate ⇒ `skip = ∅`).
3. Insert `chapter_translations` rows + publish the job **only for `todo`**; `total_chapters = len(todo)`. If `todo = ∅`, mark the job `completed` immediately (no fan-out) — a clean "nothing to do" result.
4. For each **skipped** chapter, emit a `chapter.translation_skipped` outbox event (post-commit, best-effort) so a resumed campaign converges (decision below).

### Skip done-signal: `chapter.translation_skipped` (NOT `chapter.translated`)

PO chose "emit a done-signal on skip". Implementation finding: `statistics-service` inserts a `translation_events` row for **every** `chapter.translated` unconditionally → reusing it would log a phantom 0-token translation. So skip emits a **distinct** `chapter.translation_skipped` (aggregate_type `chapter` → `loreweave:events:chapter`), payload `{user_id, book_id, chapter_id, target_language, status:'already_current'}`. The **campaign consumer** maps it to translation-done; **statistics ignores** it (no case). Same convergence, zero stats/billing pollution. *(Refinement vs the literal option — flagged at POST-REVIEW.)*

Campaign-service consumer: add `"chapter.translation_skipped": "translation"` to `EVENT_STAGE` (the language guard already applies — payload carries `target_language`).

---

## B. Knowledge `chapter_range` — worker-ai runner (D-K16.2-02b)

`scope_range` already flows to `JobRow.scope_range` (worker-ai `_get_running_jobs` selects it); `_enumerate_chapters` just drops it. Fix (3 small edits in `worker-ai/app/runner.py`):
1. `_enumerate_chapters(book_client, book_id, cursor, scope_range)` — new param.
2. After the published-revision gate, before resume-cursor: if `scope_range.chapter_range = [lo, hi]`, keep `lo <= ch.sort_order <= hi` (`sort_order` is on `ChapterInfo`).
3. Call site (`process_job`, scope ∈ chapters/all) passes `job.scope_range`.

This aligns the actual job with the cost-estimate (which already ranges via `book_client.count_chapters`), clearing the under-report note. `chapters_pending` (event drain) is out of scope — the range applies to the batch path the campaign uses.

---

## C. `D-EVAL-JUDGE-PER-USER` — bill the content owner, not the operator

The content-owner `user_id` is available at every judge call site; today the online judges pass the operator's env `user_id`. Swap (with env fallback for backward-compat / testing):
- learning `events/handlers.py` (`_maybe_judge_translation`): `user_id = str(content_owner) if content_owner else settings.online_judge_user_id`.
- learning `events/eval_runner.py` (`_maybe_judge`): `user_id = str(run["user_id"]) if run.get("user_id") else settings.online_judge_user_id`.
- knowledge coref already falls back correctly (`judge_user or user_id`) — add a clarifying comment only.
- config: note `online_judge_user_id` is an override; empty ⇒ inherit content owner.

---

## File inventory

- translation: `app/models.py` (+force_retranslate), `app/routers/jobs.py` (idempotency filter + skip emit), `app/routers/internal_dispatch.py` (+force passthrough); tests.
- campaign-service: `app/events/consumer.py` (+`chapter.translation_skipped` mapping); test.
- worker-ai: `app/runner.py` (range filter); test.
- learning-service: `app/events/handlers.py`, `app/events/eval_runner.py`, `app/config.py`; tests.

## Test plan (TDD)

- **idempotency:** skip fresh+done; translate never/failed/stale; `force_retranslate` translates all; `todo=∅` → completed 0-chapter job; skip emits `chapter.translation_skipped` with target_language; `total_chapters` = |todo|; internal dispatch path idempotent too.
- **range:** filter by `[lo,hi]`; no range = all; out-of-range excluded; estimate/actual align.
- **eval:** judge billed to content owner; env fallback when owner absent.
- **campaign consumer:** `chapter.translation_skipped` advances translation stage (with language guard).

## VERIFY

≥2 services (translation, campaign, worker-ai, learning) → live-smoke token. Full idempotency loop needs a stack-up → likely `LIVE-SMOKE deferred to D-S2-IDEMPOTENCY-LIVE-SMOKE`; unit suites of all touched services green.

## Deferred / notes

- `D-S2-IDEMPOTENCY-LIVE-SMOKE` — real re-run shows skip (0 new spend) + campaign convergence via `chapter.translation_skipped`.
- Clears: `D-K16.2-02b` (range), `D-TRANSL-IDEMPOTENCY`/`D-TRANSL-RESUME` (G3), `D-EVAL-JUDGE-PER-USER`.
