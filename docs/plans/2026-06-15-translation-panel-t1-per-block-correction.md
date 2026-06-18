# Plan — T1 Per-block Translation Correction Panel (`D-TRANSL-PANEL-T1-CORRECTION`)

> Size L · branch `feat/auto-draft-factory-gaps` · spec [`2026-06-15-translation-panel-overhaul.md`](../specs/2026-06-15-translation-panel-overhaul.md) §3 · RAID-free · no DB migration.

## Acceptance criteria (from CLARIFY, PO-approved)
- AC1 each translation block editable inline; source pane read-only anchor.
- AC2 save → get-or-create **one** human-version/(chapter,lang) (`authored_by='human'`), **patch block in place** (no new version per edit).
- AC3 each block save emits **per-block** gold (`translation.corrected`: before=LLM base block, after=human block, block_index).
- AC4 LLM never overwrites human-version (existing `_PROMOTE_ACTIVE_SQL` guard); panel shows a "newer machine translation available" banner; adopting needs explicit confirm (reuse set-active+ack).
- AC5 per-block patch via `jsonb_set` → concurrent edits to different blocks merge (row-lock serialize).
- AC6 reuse glossary quick-confirm + dirty indicators; **no** per-block re-translate button (deferred).

## BE — translation-service (no migration)
1. **Model** `PatchTranslationBlockRequest` (models.py): `target_language: str`, `base_version_id: UUID`, `block_index: int`, `block: dict`, `source_block_text: Optional[str]`.
2. **Endpoint** `PATCH /v1/translation/chapters/{chapter_id}/versions/blocks` (versions.py):
   - Resolve book from `base_version_id`; `authorize_book(EDIT)`; lang-match guard (422).
   - In a txn: `pg_advisory_xact_lock(hashtext(chapter_id||'|'||lang))` → get-or-create the human-version:
     - SELECT latest `authored_by='human'` row for (chapter,lang). If none, INSERT seeded from base (copy `translated_body/_json/_format`, `authored_by='human'`, `edited_from_version_id=base`, `version_num=max+1`, `status='completed'`, `owner_user_id=caller`) + upsert `active_chapter_translation_versions` to it.
   - Validate `0 <= block_index < len(translated_body_json)` (422 if out of range; 422 if version is text-format — per-block only for json).
   - Read `before` = base version's `translated_body_json[block_index]` (LLM anchor).
   - `UPDATE chapter_translations SET translated_body_json = jsonb_set(translated_body_json, ARRAY[$idx::text], $block::jsonb, false), updated_at=now() WHERE id=<hv>` then recompute `translated_body` (flat text join over the patched array) + UPDATE it.
   - Best-effort post-commit gold: `translation.corrected` outbox `{user_id, book_id, chapter_id, chapter_translation_id=hv, edited_from_version_id=base, target_language, block_index, before:{block}, after:{block}, source_block_text}`.
   - Return updated `ChapterTranslation`.
3. **Tests** (test_versions.py, real-PG): first call creates human-version (get-or-create) + sets active; second call patches in place (no new version, version_num unchanged); `jsonb_set` touches only the target index (other blocks unchanged); per-block gold emitted; EDIT-grant gate (403/404); index OOR 422; lang mismatch 422; text-format 422.

## FE — features/translation
4. **api.ts** `versionsApi.patchBlock(token, chapterId, {target_language, base_version_id, block_index, block, source_block_text})`.
5. **BlockAlignedReview** gains optional `editable?: boolean` + `onBlockEdit?(index, newBlock)`; when editable, the translation pane of a `translate` block renders a textarea seeded from its text; on commit build `{...block, content:[{type:'text', text}]}` and call back. (Inline-mark loss on plain-text edit = accepted v1; compound blocks fall back to read-only with a "edit in full editor" hint.)
6. **useBlockCorrection** hook (hooks/): owns editingIndex, draft text, dirty set, `saveBlock` (calls patchBlock against the human-version, base_version_id = the version being corrected), glossary quick-confirm trigger. Self-contained.
7. **Wire** a "Correct" mode into `ChapterTranslationsPage`/`TranslationReviewPage`: mounts the editable panel against the human-version (lazily get-or-created on first save); never ternary-unmount (CSS/branch). Banner for AC4 (newer LLM base than human's `edited_from`).
8. **i18n** correction labels ×4 (en/vi/ja/zh-TW).
9. **Tests** (FE): useBlockCorrection/panel — editing block → patchBlock called with right index/block + base_version_id; dirty indicator; no duplicate get-or-create.

## VERIFY
- BE: `pytest` translation-service (new patch_block tests, real-PG) green; `python -m compileall`/ruff clean.
- FE: `tsc` 0 + vitest (new panel/hook tests + existing translation green).
- Cross-service? Only translation-service + FE (FE→BE contract). Live-smoke: PATCH a block on a real version via gateway → human-version created/patched + gold row. (Or `live infra unavailable` if stack not up.)

## Risks / decisions
- get-or-create race → advisory lock (no unique-index migration).
- `translated_body` recompute keeps flat text consistent for json-format (reader uses json anyway).
- text-format versions: per-block N/A → 422, keep existing whole-version edit path.
- AC4 deep adopt-merge (re-apply human edits onto a new LLM base) = follow-up; v1 = banner + set-active-with-confirm.
