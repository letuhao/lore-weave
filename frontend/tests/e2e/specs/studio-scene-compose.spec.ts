import { test, expect } from '@playwright/test';
import { StudioComposePanels } from '../pages/StudioComposePanels';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, createChapter, trashBook,
  createCompositionWork, createCompositionScene, listChatModels,
} from '../helpers/api';

// S1-B1 — the scene draft loop in the STUDIO DOCK (scene-compose), end-to-end with a REAL local model.
// MODEL-GATED: skipped (not failed) when LM Studio + a chat model aren't available. Mirrors
// composition-generate.spec.ts (the legacy-page equivalent), but drives the dock panel + the
// cross-panel accept→editor handoff that S1 built.
test.describe('Studio scene-compose draft loop (S1-B1) [model-gated]', () => {
  let token: string;
  let bookId: string;
  let chapterId: string;
  let drafter: string | undefined;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    const chatModels = await listChatModels(request, token);
    // prefer a fast non-reasoning model so we stream prose, not hidden thinking.
    drafter = (chatModels.find((m) => /Qwen2\.5 7B|non-reasoning|fast/i.test(m.provider_model_name ?? m.alias ?? ''))
      ?? chatModels[0])?.user_model_id;
    bookId = await createBook(request, token, `E2E s1-scene ${Date.now()}`);
    chapterId = await createChapter(request, token, bookId, 'Scene chapter');
    const projectId = await createCompositionWork(request, token, bookId);
    await createCompositionScene(request, token, projectId, chapterId, 'Opening scene');
  });

  test.afterAll(async ({ request }) => {
    await trashBook(request, token, bookId).catch(() => {});
  });

  test.beforeEach(() => {
    test.skip(!drafter, 'needs LM Studio + ≥1 chat-tagged user-model');
    test.setTimeout(180_000); // real LLM streaming
  });

  test('Generate → ghost streams → Accept inserts the prose into the Editor', async ({ page }) => {
    await loginViaUI(page);
    const s = new StudioComposePanels(page);
    await s.gotoStudio(bookId, chapterId); // opens the editor on this chapter (accept target)
    await s.openSceneCompose();

    await s.pickModel(drafter!);
    await s.generateGhost();
    await s.accept.click();
    await expect(s.ghost).toHaveCount(0); // accepted → ghost cleared (onAccept returned true)

    // the accepted prose landed in the Editor doc (was empty on a fresh chapter).
    await s.openEditor();
    await expect.poll(async () => (await s.editorText()).length).toBeGreaterThan(20);
  });

  test('Regenerate captures a correction (the flywheel S1 owns) then re-streams', async ({ page }) => {
    await loginViaUI(page);
    const s = new StudioComposePanels(page);
    await s.gotoStudio(bookId, chapterId);
    await s.openSceneCompose();
    await s.pickModel(drafter!);
    await s.generateGhost();

    // Regenerate = a genuine dissatisfaction signal → composition.generation_corrected.
    const correction = page.waitForResponse(
      (r) => /\/jobs\/.+\/correction/.test(r.url()) && r.request().method() === 'POST',
      { timeout: 30_000 },
    );
    await s.regenerate.click();
    const resp = await correction;
    expect(resp.status()).toBeGreaterThanOrEqual(200);
    expect(resp.status()).toBeLessThan(300);
  });

  // NOTE — the GAP-2 guard (Accept never loses the draft when no editor is open on this chapter) is
  // covered by UNIT tests (ComposeView/ChapterAssembleView "Accept that FAILS keeps the draft", +
  // useAcceptIntoEditor's return-false path). It is intentionally NOT an E2E here: the editorBridge's
  // handle is the Tier-4 ManuscriptUnit hoist's editorRef, which lives ABOVE the dock, so simply
  // CLOSING the Editor panel does NOT null the target — the doc persists and Accept still lands
  // correctly (a GOOD property: the draft-loss window is narrower than the audit feared). Reproducing
  // a truly-absent editor target requires no manuscript unit at all, which the studio always loads.

});
