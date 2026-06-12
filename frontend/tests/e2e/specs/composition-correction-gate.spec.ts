import { test, expect } from '@playwright/test';
import { ChapterComposePanel } from '../pages/ChapterComposePanel';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, createChapter, trashBook,
  listChatModels, createCompositionWork, createCompositionScene,
} from '../helpers/api';
import { dbAvailable, queryDb } from '../helpers/db';

// V1 slice 3 — the controlled-auto human gate in the browser (realizes
// D-COMP-SLICE3-PLAYWRIGHT). MODEL-GATED (needs LM Studio + a chat drafter): the
// diverge→converge generate is a real ~40s K-draft run. Proves the K-candidate
// cards render, the winner is badged, and using a NON-winner card both resolves
// the gate AND captures a pick_different correction all the way into the learning
// store (browser → composition → relay → learning), the slice 1+2+3 loop.
test.describe('Composition controlled-auto correction gate (slice 3) [model-gated]', () => {
  test('Diverge → K cards → use a non-winner captures pick_different + resolves the gate', async ({ page, request }) => {
    test.setTimeout(180_000);
    const token = await getAccessToken(request);
    const chatModels = await listChatModels(request, token);
    test.skip(chatModels.length < 1, 'needs a chat-tagged drafter + LM Studio');
    const drafter = chatModels.find((m) => /qwen3\.6-35b/.test(m.provider_model_name)) ?? chatModels[0];

    const bookId = await createBook(request, token, `E2E corr-gate ${Date.now()}`);
    const chapterId = await createChapter(request, token, bookId, 'Gate chapter');
    const projectId = await createCompositionWork(request, token, bookId);
    await createCompositionScene(request, token, projectId, chapterId, 'Opening');
    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoEditor(bookId, chapterId);
      await panel.openComposeTab();
      await expect(panel.modelSelect).toBeVisible();
      await panel.modelSelect.selectOption(drafter.user_model_id);
      await panel.reasoningSelect.selectOption('off');

      // turn on Diverge (K options) → Generate runs the non-streaming auto path
      await panel.divergeToggle.check();
      await expect(panel.generate).toBeEnabled();
      await panel.generate.click();

      // the K candidate cards appear; exactly one is badged as the AI's pick
      await expect(panel.candidatesView).toBeVisible({ timeout: 150_000 });
      await expect.poll(async () => panel.candidateCards.count(), { timeout: 10_000 })
        .toBeGreaterThanOrEqual(2);
      await expect(panel.candidateWinnerBadge).toHaveCount(1);

      // pick a NON-winner card → captures pick_different (cand_j ≻ winner_i)
      const cards = panel.candidateCards;
      const n = await cards.count();
      let nonWinner = -1;
      for (let i = 0; i < n; i++) {
        if ((await cards.nth(i).getAttribute('data-winner')) === 'false') { nonWinner = i; break; }
      }
      expect(nonWinner, 'a non-winner card must exist').toBeGreaterThanOrEqual(0);
      await cards.nth(nonWinner).getByTestId('candidate-use').click();

      // the gate resolved — cards gone (the picked prose was inserted into the editor)
      await expect(panel.candidatesView).toBeHidden();

      // browser → relay → learning: the pick_different correction reached the store
      if (dbAvailable()) {
        const deadline = Date.now() + 60_000;
        let found = false;
        while (Date.now() < deadline) {
          const c = Number(queryDb('loreweave_learning',
            `SELECT count(*) FROM corrections WHERE project_id='${projectId}' ` +
            `AND origin_service='composition' AND op='pick_different'`).trim());
          if (c >= 1) { found = true; break; }
          await new Promise((r) => setTimeout(r, 4000));
        }
        expect(found, 'the pick_different correction must reach the learning store').toBe(true);
      }
    } finally {
      // clean the cross-DB capture rows the trashBook cleanup does not reach
      if (dbAvailable()) {
        try {
          queryDb('loreweave_learning', `DELETE FROM corrections WHERE project_id='${projectId}'`);
          queryDb('loreweave_composition',
            `DELETE FROM generation_correction WHERE project_id='${projectId}'; ` +
            `DELETE FROM generation_job WHERE project_id='${projectId}'; ` +
            `DELETE FROM outline_node WHERE project_id='${projectId}'; ` +
            `DELETE FROM composition_work WHERE project_id='${projectId}';`);
        } catch { /* best-effort cleanup */ }
      }
      await trashBook(request, token, bookId);
    }
  });
});
