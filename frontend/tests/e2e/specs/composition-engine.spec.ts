import { test, expect } from '@playwright/test';
import { ChapterComposePanel } from '../pages/ChapterComposePanel';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, createChapter, trashBook,
  listChatModels, createCompositionWork, createCompositionScene,
} from '../helpers/api';

// V0 scenario tests B4.* — the co-write engine UI. B4.1 (generate gating) is
// model-free; B4.4 (discard) + the reasoning badge + B4.2 (stop mid-stream) are
// MODEL-GATED (need LM Studio + a chat drafter, reasoning off so a thinking model
// streams prose). B4.3 (rapid-supersede) and B5.* (critic skip/degrade/dismiss)
// are covered by the 29 M6 unit tests and are not deterministically reproducible
// in a browser, so they stay unit-only here.
test.describe('Composition co-write engine (B4.*)', () => {
  test('B4.1: Generate is gated until both a scene and a model are picked', async ({ page, request }) => {
    const token = await getAccessToken(request);
    const bookId = await createBook(request, token, `E2E gate-gen ${Date.now()}`);
    const chapterId = await createChapter(request, token, bookId, 'Gen gate chapter');
    await createCompositionWork(request, token, bookId); // Work, no scenes yet
    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoEditor(bookId, chapterId);
      await panel.openComposeTab();

      // no scene → "pick a scene" hint + Generate disabled
      await expect(panel.needScene).toBeVisible();
      await expect(panel.generate).toBeDisabled();

      // add a scene → it auto-selects → now the missing piece is the model
      await panel.addScene.click();
      await expect(panel.needModel).toBeVisible();
      await expect(panel.generate).toBeDisabled();
    } finally {
      await trashBook(request, token, bookId);
    }
  });

  test('B4.4 + reasoning badge: generate → ghost + resolved badge → discard clears it [model-gated]', async ({ page, request }) => {
    test.setTimeout(180_000);
    const token = await getAccessToken(request);
    const chatModels = await listChatModels(request, token);
    test.skip(chatModels.length < 1, 'needs a chat-tagged drafter + LM Studio');
    const drafter = chatModels.find((m) => /qwen3\.6-35b/.test(m.provider_model_name)) ?? chatModels[0];

    const bookId = await createBook(request, token, `E2E discard ${Date.now()}`);
    const chapterId = await createChapter(request, token, bookId, 'Discard chapter');
    const projectId = await createCompositionWork(request, token, bookId);
    await createCompositionScene(request, token, projectId, chapterId, 'Opening');
    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoEditor(bookId, chapterId);
      await panel.openComposeTab();
      await expect(panel.modelSelect).toBeVisible();
      await panel.selectModel(drafter.user_model_id);
      await panel.reasoningSelect.selectOption('off');

      // generate → ghost streams; the auto-reasoning badge resolves (off → no thinking)
      await expect(panel.generate).toBeEnabled();
      await panel.generate.click();
      await expect(panel.reasoningBadge).toBeVisible({ timeout: 30_000 });
      await expect(panel.ghost).toBeVisible({ timeout: 120_000 });
      await expect.poll(async () => (await panel.ghost.innerText()).trim().length, { timeout: 120_000 })
        .toBeGreaterThan(10);
      // wait for the stream to finish (Discard only shows when not streaming)
      await expect(panel.discard).toBeVisible({ timeout: 120_000 });

      // discard → ghost removed (never inserted into the editor doc, SC4)
      await panel.discard.click();
      await expect(panel.ghost).toBeHidden();
    } finally {
      await trashBook(request, token, bookId);
    }
  });

  test('B4.2: Stop mid-stream halts streaming and keeps the partial ghost [model-gated]', async ({ page, request }) => {
    test.setTimeout(180_000);
    const token = await getAccessToken(request);
    const chatModels = await listChatModels(request, token);
    test.skip(chatModels.length < 1, 'needs a chat-tagged drafter + LM Studio');
    const drafter = chatModels.find((m) => /qwen3\.6-35b/.test(m.provider_model_name)) ?? chatModels[0];

    const bookId = await createBook(request, token, `E2E stop ${Date.now()}`);
    const chapterId = await createChapter(request, token, bookId, 'Stop chapter');
    const projectId = await createCompositionWork(request, token, bookId);
    await createCompositionScene(request, token, projectId, chapterId, 'Opening');
    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoEditor(bookId, chapterId);
      await panel.openComposeTab();
      await panel.selectModel(drafter.user_model_id);
      await panel.reasoningSelect.selectOption('off');

      await panel.generate.click();
      // wait until streaming has produced some prose, then stop
      await expect(panel.stop).toBeVisible({ timeout: 30_000 });
      await expect.poll(async () => (await panel.ghost.innerText()).trim().length, { timeout: 120_000 })
        .toBeGreaterThan(5);
      const partialLen = (await panel.ghost.innerText()).trim().length;
      await panel.stop.click();

      // streaming stopped → Generate is back; the partial ghost is retained (not cleared)
      await expect(panel.generate).toBeVisible({ timeout: 15_000 });
      expect((await panel.ghost.innerText()).trim().length).toBeGreaterThanOrEqual(partialLen);
    } finally {
      await trashBook(request, token, bookId);
    }
  });
});
