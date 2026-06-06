import { test, expect } from '@playwright/test';
import { ChapterComposePanel } from '../pages/ChapterComposePanel';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, trashBook } from '../helpers/api';

// V0 scenario tests U1, U2, B3.1, B7.* — the OI-1 chapter-gate. Generation needs
// a model, so this spec exercises only the model-free path: set up the co-writer,
// add a scene, and prove Publish is gated until the scene is marked done (and
// that the gate is satisfiable from the UI — the /review-impl dead-gate lock).
test.describe('Composition chapter-gate (U1/U2/B3/B7)', () => {
  test('U1+U2+B7: setup co-writer, add a scene, Publish gated until the scene is done', async ({ page, request }) => {
    const token = await getAccessToken(request);
    const bookId = await createBook(request, token, `E2E gate ${Date.now()}`);
    const chapterId = await createChapter(request, token, bookId, 'Gate chapter');
    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoEditor(bookId, chapterId);

      // B7.3 — no composition Work yet → Publish is ungated (CM-FE preserved).
      await expect(panel.publishButton).toBeEnabled();

      // U1 — set up the co-writer (POST /work).
      await panel.openComposeTab();
      await expect(panel.setupButton).toBeVisible();
      await panel.setupButton.click();

      // U2 — add a scene; it appears in the picker.
      await expect(panel.addScene).toBeVisible();
      await panel.addScene.click();
      await expect(panel.sceneSelect.locator('option')).toHaveCount(1);

      // B7.1 — a Work + a not-done scene → Publish is now DISABLED (chapter-gate).
      await expect(panel.publishButton).toBeDisabled();

      // B3.1 + B7.4 + B7.5 — Mark done from the UI re-enables Publish (no reload,
      // no API back-door — the gate is satisfiable through the affordance).
      await expect(panel.markDone).toBeVisible();
      await panel.markDone.click();
      await expect(panel.publishButton).toBeEnabled({ timeout: 10_000 });
    } finally {
      await trashBook(request, token, bookId);
    }
  });
});
