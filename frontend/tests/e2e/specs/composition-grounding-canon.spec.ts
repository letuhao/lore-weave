import { test, expect } from '@playwright/test';
import { ChapterComposePanel } from '../pages/ChapterComposePanel';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, createChapter, trashBook,
  createCompositionWork, createCompositionScene,
} from '../helpers/api';

// V0 scenario tests U5/B6.1 (grounding preview + honest no-graph signal) and U6
// (canon-rule add/list/archive). MODEL-FREE: the grounding/canon UI is driven for
// real against the live composition packer; data seeded via API.
test.describe('Composition grounding + canon UI (U5/U6/B6.1)', () => {
  test('U5+B6.1: a book with no knowledge graph shows an honest "thin" grounding signal', async ({ page, request }) => {
    const token = await getAccessToken(request);
    const bookId = await createBook(request, token, `E2E grounding ${Date.now()}`);
    const chapterId = await createChapter(request, token, bookId, 'Scene chapter');
    const projectId = await createCompositionWork(request, token, bookId);
    await createCompositionScene(request, token, projectId, chapterId, 'Opening');
    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoEditor(bookId, chapterId);
      await panel.openComposeTab();

      // open Grounding → the packer runs for the selected scene; with no published
      // chapters there is no KG, so the signal is honest (available=false) + a warning
      await panel.subtabGrounding.click();
      await expect(panel.groundingSignal).toBeVisible({ timeout: 15_000 });
      await expect(panel.groundingSignal).toHaveAttribute('data-available', 'false');
      await expect(panel.groundingWarning).toBeVisible();
      // token count is reported (the packer still assembled the structural blocks)
      await expect(panel.groundingSignal).toContainText(/tokens/i);
    } finally {
      await trashBook(request, token, bookId);
    }
  });

  test('U6: add a canon rule → it lists; archive removes it from the active set', async ({ page, request }) => {
    const token = await getAccessToken(request);
    const bookId = await createBook(request, token, `E2E canon ${Date.now()}`);
    const chapterId = await createChapter(request, token, bookId, 'Canon chapter');
    await createCompositionWork(request, token, bookId);
    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoEditor(bookId, chapterId);
      await panel.openComposeTab();

      await panel.subtabCanon.click();
      await expect(panel.canonInput).toBeVisible();
      await expect(panel.canonRules).toHaveCount(0); // none yet

      // add a world-scoped rule
      await panel.canonInput.fill('Magic always has a blood cost');
      await panel.canonScope.selectOption('world');
      await panel.canonAdd.click();
      await expect(panel.canonRules).toHaveCount(1);
      await expect(panel.canonRules.first()).toContainText('Magic always has a blood cost');

      // archive → removed from the active set
      await panel.canonArchive.first().click();
      await expect(panel.canonRules).toHaveCount(0);
    } finally {
      await trashBook(request, token, bookId);
    }
  });
});
