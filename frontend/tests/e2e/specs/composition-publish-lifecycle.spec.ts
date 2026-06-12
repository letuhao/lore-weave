import { test, expect } from '@playwright/test';
import { ChapterComposePanel } from '../pages/ChapterComposePanel';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, createChapter, trashBook,
  seedChapterWithRevisions, getChapterEditorial, bumpServerDraft, createCompositionWork,
} from '../helpers/api';

// V0 scenario tests B1.* (Canon Model publish lifecycle) + B7.2 (zero-scene gate).
// All MODEL-FREE: data seeded via API, the publish affordance driven through the
// real editor UI, and the canon-side outcome asserted via the server (editorial
// fields) — not just the badge. These lock the canon=published + OI-2 invariants.
test.describe('Composition publish lifecycle (B1.* / B7.2)', () => {
  test('B1.2: Publish is disabled while the editor is dirty, re-enabled after save', async ({ page, request }) => {
    const token = await getAccessToken(request);
    const { bookId, chapterId } = await seedChapterWithRevisions(request, token, ['hello world']);
    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoEditor(bookId, chapterId);

      // loaded + draft, no composition Work → publish ungated + enabled
      await expect(panel.editorialBadge).toHaveAttribute('data-status', 'draft');
      await expect(panel.publishButton).toBeEnabled();

      // dirty the title (no save) → Publish disabled ("save before publishing")
      await panel.titleInput.click();
      await panel.titleInput.press('End');
      await panel.titleInput.pressSequentially(' edited');
      await expect(panel.publishButton).toBeDisabled();

      // save → not dirty → Publish enabled again
      await panel.saveButton.click();
      await expect(panel.publishButton).toBeEnabled({ timeout: 10_000 });
    } finally {
      await trashBook(request, token, bookId);
    }
  });

  test('B1.3: Re-publish after an edit advances the pinned published_revision_id', async ({ page, request }) => {
    const token = await getAccessToken(request);
    const { bookId, chapterId } = await seedChapterWithRevisions(request, token, ['first body']);
    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoEditor(bookId, chapterId);

      // publish #1 → badge flips, a revision is pinned
      await expect(panel.publishButton).toBeEnabled();
      await panel.publishButton.click();
      await expect(panel.editorialBadge).toHaveAttribute('data-status', 'published', { timeout: 10_000 });
      const first = await getChapterEditorial(request, token, bookId, chapterId);
      expect(first.published_revision_id).toBeTruthy();

      // edit + save → new revision; re-publish → pin advances
      await panel.editTitleAndSave(' v2');
      await expect(panel.publishButton).toBeEnabled({ timeout: 10_000 });
      await panel.publishButton.click();
      // badge stays published; assert the pin moved
      await expect.poll(async () => {
        const e = await getChapterEditorial(request, token, bookId, chapterId);
        return e.published_revision_id;
      }, { timeout: 10_000 }).not.toBe(first.published_revision_id);
    } finally {
      await trashBook(request, token, bookId);
    }
  });

  test('B1.4: Stale publish (OI-2) → conflict toast, no silent clobber', async ({ page, request }) => {
    const token = await getAccessToken(request);
    const { bookId, chapterId } = await seedChapterWithRevisions(request, token, ['body one']);
    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoEditor(bookId, chapterId);
      await expect(panel.editorialBadge).toHaveAttribute('data-status', 'draft');
      await expect(panel.publishButton).toBeEnabled();

      // another tab/device saves → the editor's loaded draft_version goes stale
      await bumpServerDraft(request, token, bookId, chapterId, 'body two from elsewhere');

      // publish with the stale version → 409 CHAPTER_DRAFT_CONFLICT (publish does
      // NOT auto-retry, unlike save) → conflict toast + the chapter stays draft
      await panel.publishButton.click();
      await expect(page.getByText('Draft changed since you opened it')).toBeVisible({ timeout: 10_000 });
      await expect(panel.editorialBadge).toHaveAttribute('data-status', 'draft');
      const e = await getChapterEditorial(request, token, bookId, chapterId);
      expect(e.editorial_status).toBe('draft');
    } finally {
      await trashBook(request, token, bookId);
    }
  });

  test('B1.5: Draft-save does NOT canonize (no publish side effect)', async ({ page, request }) => {
    const token = await getAccessToken(request);
    const { bookId, chapterId } = await seedChapterWithRevisions(request, token, ['draft text']);
    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoEditor(bookId, chapterId);
      await expect(panel.editorialBadge).toHaveAttribute('data-status', 'draft');

      // edit + save (NOT publish) → still draft, nothing pinned (canon = published)
      await panel.editTitleAndSave(' saved-not-published');
      await expect(panel.editorialBadge).toHaveAttribute('data-status', 'draft');
      const e = await getChapterEditorial(request, token, bookId, chapterId);
      expect(e.editorial_status).toBe('draft');
      expect(e.published_revision_id ?? null).toBeNull();
    } finally {
      await trashBook(request, token, bookId);
    }
  });

  test('B1.1: Publishing an empty-body chapter is blocked (no canon from nothing)', async ({ page, request }) => {
    // A fresh chapter has no extractable prose. book-service rejects the publish
    // with 422 CHAPTER_EMPTY_PUBLISH so canon never includes an empty chapter (and
    // extraction never runs on nothing) — the badge stays draft, with a toast.
    const token = await getAccessToken(request);
    const bookId = await createBook(request, token, `E2E empty publish ${Date.now()}`);
    const chapterId = await createChapter(request, token, bookId, 'Empty chapter');
    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoEditor(bookId, chapterId);
      await expect(panel.editorialBadge).toHaveAttribute('data-status', 'draft');
      await expect(panel.publishButton).toBeEnabled();

      await panel.publishButton.click();
      // blocked: an error toast + the chapter stays draft (server confirms)
      await expect(page.getByText('no content to publish')).toBeVisible({ timeout: 10_000 });
      await expect(panel.editorialBadge).toHaveAttribute('data-status', 'draft');
      const e = await getChapterEditorial(request, token, bookId, chapterId);
      expect(e.editorial_status).toBe('draft');
      expect(e.published_revision_id ?? null).toBeNull();
    } finally {
      await trashBook(request, token, bookId);
    }
  });

  test('B7.2: a composition book with zero scenes blocks Publish (chapter-gate)', async ({ page, request }) => {
    const token = await getAccessToken(request);
    const bookId = await createBook(request, token, `E2E zero-scene ${Date.now()}`);
    const chapterId = await createChapter(request, token, bookId, 'Gated chapter');
    await createCompositionWork(request, token, bookId); // Work exists, no scenes
    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoEditor(bookId, chapterId);

      // the gate engages (Work found) → zero scenes → Publish blocked with the
      // PO-decided "create and complete at least one scene" reason.
      await expect(panel.publishButton).toBeDisabled({ timeout: 10_000 });
      await expect(panel.publishButton).toHaveAttribute('title', /at least one scene/i);
    } finally {
      await trashBook(request, token, bookId);
    }
  });
});
