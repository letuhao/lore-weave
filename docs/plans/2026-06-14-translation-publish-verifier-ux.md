# Plan — Translation publish/verifier UX + auto-promote (L)

- **Date:** 2026-06-14 · **Branch:** feat/auto-draft-factory-gaps
- **Spec:** `docs/specs/2026-06-14-translation-publish-verifier-ux-investigation.md`
- **Size:** L (logic 7, side effects 3: createJob payload contract, active-promotion behavior change, DB data fix)

## Acceptance criteria
- **AC1** From the workspace TranslationTab, a translated cell is clickable → opens `/books/:bookId/chapters/:chapterId/translations?lang=<lang>` where the user can set a version active.
- **AC2** TranslateModal exposes optional quality-verification (V3): verifier model + qa_depth + max_qa_rounds; `createJob` sends `pipeline_version='v3'` + those fields when enabled. Plus a `force_retranslate` toggle so re-translating an already-done chapter actually produces a new version.
- **AC3** Non-campaign chapter completion auto-promotes the new clean version (`unresolved_high_count=0`) to active UNLESS the current active is `authored_by='human'`. Campaign path converges to the same guarded behavior.
- **AC4** Chapter 1 of book `019eb60e…` is promoted to the Gemma v4 translation.

## Tasks (TDD where it bites)

### BE — auto-promote (item 3)
1. `services/translation-service/app/workers/chapter_worker.py:346-379` — replace the `campaign_id`-branched `_on_conflict` with a single guarded `ON CONFLICT DO UPDATE`:
   ```sql
   ON CONFLICT (chapter_id, target_language) DO UPDATE
     SET chapter_translation_id = EXCLUDED.chapter_translation_id,
         set_by_user_id = EXCLUDED.set_by_user_id,
         set_at = now()
     WHERE COALESCE(
       (SELECT cur.authored_by FROM chapter_translations cur
         WHERE cur.id = active_chapter_translation_versions.chapter_translation_id), 'llm'
     ) <> 'human'
   ```
   Keep the `SELECT ... WHERE COALESCE(unresolved_high_count,0)=0` M5b gate. Rewrite the comment block (policy: auto-promote clean versions; never clobber a human edit; campaign + interactive converge).
2. Tests `services/translation-service/tests/test_chapter_worker.py`:
   - Update `test_block_pipeline_auto_active_gated_on_unresolved_high` (line ~478): assert `DO UPDATE` + human-edit guard clause present.
   - Update `test_non_campaign_job_keeps_human_publish_gate` (line ~527) → rename to `test_non_campaign_job_auto_promotes_with_human_guard`; assert `DO UPDATE` and `authored_by` guard, no `DO NOTHING`.
   - Keep `test_campaign_job_autonomous_publish_promotes_over_existing`; add assertion the guard clause is present.

### FE — verifier + force + payload (item 2)
3. `frontend/src/features/translation/api.ts` — extend `createJob` payload type with optional `pipeline_version`, `qa_depth`, `max_qa_rounds`, `verifier_model_source`, `verifier_model_ref`, `force_retranslate`.
4. `frontend/src/pages/book-tabs/TranslateModal.tsx` — add a collapsible "Kiểm định chất lượng (V3)" section:
   - checkbox `verifyEnabled` → reveals: verifier model `<select>` (optional, reuse `modelsByProvider`), `qa_depth` select (rule_only|standard|thorough, default standard), `max_qa_rounds` number (1-5, default 2).
   - checkbox `force_retranslate` ("Bắt buộc dịch lại — ghi đè bản đã có").
   - `handleSubmit` payload: when `verifyEnabled` → `pipeline_version:'v3'`, `qa_depth`, `max_qa_rounds`, and if verifier model chosen `verifier_model_source:'user_model'`, `verifier_model_ref`. Always pass `force_retranslate`.

### FE — wire route (item 1)
5. `frontend/src/pages/book-tabs/TranslationTab.tsx` — `useNavigate`; for cells with `version_count>0`, render a focusable `<button>` (cursor-pointer, hover, aria-label) that navigates to `/books/${bookId}/chapters/${row.chapter_id}/translations?lang=${lang}`. Untranslated cells stay non-interactive.

### i18n
6. Add new keys to `frontend/src/i18n/locales/{en,ja,vi,zh-TW}/books.json` (modal: verify section labels, force label) and `…/translation.json` if a matrix tooltip/aria string is added.

### Data fix (item 4)
7. After BE verified, run the one-row UPDATE on `loreweave_translation` promoting chapter 1 → `019ec574-e9bc-7d81-8a21-621a038ee41c`.

## Verify
- BE: `pytest services/translation-service/tests/test_chapter_worker.py` green.
- FE: `npm run build` / vitest for touched components; type-check passes.
- Live-smoke (≥2 services? only translation-service BE + FE here — single service BE): a real translate→complete→auto-promote on the stack, or `live infra unavailable` note. Data fix confirmed by re-query.

## Risks / notes
- Campaign promotion now respects human edits (behavior change beyond the literal ask) — conscious, safer; flag at POST-REVIEW.
- Verifier only runs in v3 → FE must send `pipeline_version='v3'` when verify enabled (else silently no-op). Covered.
- `authored_by` default is `'llm'`; human edits set `'human'` (versions.py). Guard keys on that.
