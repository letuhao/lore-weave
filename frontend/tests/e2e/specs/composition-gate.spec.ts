import { test, expect } from '@playwright/test';
import { ChapterComposePanel } from '../pages/ChapterComposePanel';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, trashBook } from '../helpers/api';

// V0 scenario tests U1, U2, B3.1, B7.* — the OI-1 chapter-gate. Generation needs
// a model, so this spec exercises only the model-free path: set up the co-writer,
// add a scene, and prove Publish is gated until the scene is marked done (and
// that the gate is satisfiable from the UI — the /review-impl dead-gate lock).
test.describe('Composition chapter-gate (U1/U2/B3/B7)', () => {
  test('U1+U2+B7: co-writer ready, add a scene, Publish gated until the scene is done', async ({ page, request }) => {
    const token = await getAccessToken(request);
    const bookId = await createBook(request, token, `E2E gate ${Date.now()}`);
    const chapterId = await createChapter(request, token, bookId, 'Gate chapter');
    try {
      await loginViaUI(page);
      const panel = new ChapterComposePanel(page);
      await panel.gotoStudio(bookId, chapterId);

      // B7.3 — "no composition Work yet → Publish is ungated" can no longer be reached from the
      // Writing Studio: every book has a Work by the time the Studio shows it (see U1). The
      // fail-open behaviour itself is still pinned, at the layer that can still reach it:
      // usePublishGate.test.tsx — "no composition Work → ungated (blocked:false)".

      // U1 — in the Writing Studio the co-writer is READY without a setup step: the book got its
      // Work when it was created (book-service provisions it, plan 2026-09-18 T7) and the Studio
      // ensures one on open (useEnsureWork). The legacy page's "Set up co-writer" click described
      // a state the Studio never shows, so the Studio's form of the claim is: no setup button, and
      // the scene controls are already there.
      await panel.openComposeTab();
      await expect(panel.addScene).toBeVisible();
      await expect(panel.setupButton).toHaveCount(0);

      // U2 — add a scene; it appears in the picker.
      await expect(panel.addScene).toBeVisible();
      await panel.addScene.click();
      // ONE scene: the guided "Opening scene" seed (useGuidedFirstRun.runGuided) fires only from
      // the setup click, which the Studio no longer needs, so "+ Scene" is the only scene here.
      await expect(panel.sceneSelect.locator('option')).toHaveCount(1);

      // B7.1 — a Work + a not-done scene → Publish (in the Editor panel) is now DISABLED (chapter-gate).
      await panel.showEditor();
      await expect(panel.publishButton).toBeDisabled();
      await panel.openComposeTab();

      // B3.1 + B7.4 + B7.5 — Mark done from the UI re-enables Publish (no reload,
      // no API back-door — the gate is satisfiable through the affordance).
      // The gate counts EVERY scene ("1 of 2 scenes not yet done" is what the disabled
      // button's own title said), so every scene has to be marked done through the UI --
      // which is the claim: the gate is satisfiable through the affordance, not a back door.
      await expect(panel.markDone).toBeVisible();
      const options = panel.sceneSelect.locator('option');
      for (let i = 0; i < (await options.count()); i++) {
        const value = await options.nth(i).getAttribute('value');
        if (value) await panel.sceneSelect.selectOption(value);
        if (await panel.markDone.isVisible()) await panel.markDone.click();
      }
      await panel.showEditor();
      await expect(panel.publishButton).toBeEnabled({ timeout: 10_000 });
    } finally {
      await trashBook(request, token, bookId);
    }
  });
});
