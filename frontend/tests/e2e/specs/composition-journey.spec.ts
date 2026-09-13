import { test, expect } from '@playwright/test';
import { ChapterComposePanel } from '../pages/ChapterComposePanel';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, createChapter, trashBook,
  listChatModels, getChapterEditorial,
} from '../helpers/api';

// V0 scenario test — the end-to-end USER journey U1→U7 in one continuous session:
// set up the co-writer → add a scene → co-write (generate→accept) → save → mark the
// scene done → publish. MODEL-GATED (real drafter). This is the integration the
// piecewise specs don't cover: that the whole flow chains, and that accepted AI
// prose persists to a non-empty draft that then passes the empty-publish guard.
// (U8 flywheel / extraction assert lives in the DB-assert batch — async + KG.)
test.describe('Composition happy-path journey (U1→U7) [model-gated]', () => {
  test('set up → scene → co-write → accept → save → mark done → publish', async ({ page, request }) => {
    test.setTimeout(200_000);
    const token = await getAccessToken(request);
    const chatModels = await listChatModels(request, token);
    test.skip(chatModels.length < 1, 'needs a chat-tagged drafter + LM Studio');
    const drafter = chatModels.find((m) => /qwen3\.6-35b/.test(m.provider_model_name)) ?? chatModels[0];

    const bookId = await createBook(request, token, `E2E journey ${Date.now()}`);
    const chapterId = await createChapter(request, token, bookId, 'Journey chapter');
    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoEditor(bookId, chapterId);

      // U1 — set up the co-writer (no Work yet)
      await panel.openComposeTab();
      await expect(panel.setupButton).toBeVisible();
      await panel.setupButton.click();

      // U2 — add a scene
      await expect(panel.addScene).toBeVisible();
      await panel.addScene.click();
      // TWO scenes, not one: the GUIDED first run seeds an "Opening scene"
      // (CompositionPanel.tsx:192, guarded against a second by useGuidedFirstRun)
      // and addScene adds its own beside it. Asserting 1 used to PASS by racing the
      // guided seed's arrival, then the run failed 40 lines later on a gate that was
      // correct -- "1 of 2 scenes not yet done". composition-gate.spec.ts:35 already
      // pins 2 for this same sequence.
      await expect(panel.sceneSelect.locator('option')).toHaveCount(2);

      // U7 (pre) — Work + a not-done scene → Publish is gated
      await expect(panel.publishButton).toBeDisabled();

      // U3 — co-write: generate → ghost → accept (inserts into the editor)
      await panel.selectModel(drafter.user_model_id);
      await panel.setReasoning('off');
      await expect(panel.generate).toBeEnabled();
      await panel.generate.click();
      await expect(panel.ghost).toBeVisible({ timeout: 120_000 });
      await expect.poll(async () => (await panel.ghost.innerText()).trim().length, { timeout: 120_000 })
        .toBeGreaterThan(10);
      await expect(panel.accept).toBeVisible({ timeout: 30_000 });
      await panel.accept.click();
      await expect(panel.ghost).toBeHidden();

      // accept leaves the editor dirty → Publish stays disabled until we save the
      // prose (the accepted draft must persist before it can be canonized)
      await expect(panel.publishButton).toBeDisabled();
      await panel.saveButton.click();

      // U7 — still gated until EVERY scene is done; mark them all done → publish enables.
      // A user with two scenes must finish both, and the button says so: it stayed
      // disabled with title="1 of 2 scenes not yet done" while one was outstanding.
      await expect(panel.publishButton).toBeDisabled();
      const sceneOptions = panel.sceneSelect.locator('option');
      const sceneCount = await sceneOptions.count();
      for (let i = 0; i < sceneCount; i++) {
        const value = await sceneOptions.nth(i).getAttribute('value');
        if (!value) continue;
        await panel.sceneSelect.selectOption(value);
        await panel.markDone.click();
      }
      await expect(panel.publishButton).toBeEnabled({ timeout: 10_000 });
      await panel.publishButton.click();

      // published: the accepted prose was non-empty, so it passed the empty guard
      await expect(panel.editorialBadge).toHaveAttribute('data-status', 'published', { timeout: 15_000 });
      const e = await getChapterEditorial(request, token, bookId, chapterId);
      expect(e.editorial_status).toBe('published');
      expect(e.published_revision_id).toBeTruthy();
    } finally {
      await trashBook(request, token, bookId);
    }
  });
});
