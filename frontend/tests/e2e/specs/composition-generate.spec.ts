import { test, expect } from '@playwright/test';
import { ChapterComposePanel } from '../pages/ChapterComposePanel';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, createChapter, trashBook,
  listChatModels, listActiveModels, createCompositionWork, createCompositionScene, setWorkCriticModel,
} from '../helpers/api';

// V0 scenario tests U3 + U4 — co-write generate (ghost → accept) + advisory
// critic. MODEL-GATED: needs LM Studio up + ≥2 active chat user-models (drafter +
// a DISTINCT critic). The drafter runs with reasoning_effort="none" so a thinking
// model (qwen3.6-35b-a3b) streams prose instead of burning the budget on hidden
// reasoning. Skipped (not failed) when the models aren't available.
test.describe('Composition co-write generate + critic (U3/U4) [model-gated]', () => {
  test('drafts a scene (thinking off) and runs the distinct-model critic on accept', async ({ page, request }) => {
    test.setTimeout(180_000); // real LLM streaming + a second critic call

    const token = await getAccessToken(request);
    // drafter: a chat-tagged model (shown in the UI picker), preferring the
    // thinking model so we exercise reasoning-off. critic: ANY distinct active
    // model (set via API, so it needn't be chat-tagged or picker-visible).
    const chatModels = await listChatModels(request, token);
    const allModels = await listActiveModels(request, token);
    test.skip(chatModels.length < 1 || allModels.length < 2,
      'needs a chat-tagged drafter + ≥1 distinct active critic model + LM Studio');

    const drafter = chatModels.find((m) => /qwen3\.6-35b/.test(m.provider_model_name)) ?? chatModels[0];
    const critic = allModels.find((m) => m.user_model_id !== drafter.user_model_id)!;

    const bookId = await createBook(request, token, `E2E cowrite ${Date.now()}`);
    const chapterId = await createChapter(request, token, bookId, 'Co-write chapter');
    const projectId = await createCompositionWork(request, token, bookId);
    await createCompositionScene(request, token, projectId, chapterId, 'Opening');
    await setWorkCriticModel(request, token, projectId, critic.user_model_id);

    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoEditor(bookId, chapterId);
      await panel.openComposeTab();

      // pick the drafter model + disable hidden thinking (U3 setup)
      await expect(panel.modelSelect).toBeVisible();
      await panel.selectModel(drafter.user_model_id);
      await panel.reasoningSelect.selectOption('off');

      // U3 — generate streams prose into the ghost (NOT empty — proves the
      // reasoning-off path through the whole stack on a thinking model).
      await expect(panel.generate).toBeEnabled();
      await panel.generate.click();
      await expect(panel.ghost).toBeVisible({ timeout: 120_000 });
      await expect.poll(async () => (await panel.ghost.innerText()).trim().length, { timeout: 120_000 })
        .toBeGreaterThan(20);

      // U4 — accept inserts the prose + runs the advisory critic (distinct model).
      await expect(panel.accept).toBeVisible({ timeout: 30_000 });
      await panel.accept.click();
      await expect(panel.critic).toBeVisible({ timeout: 90_000 });
    } finally {
      await trashBook(request, token, bookId);
    }
  });
});
