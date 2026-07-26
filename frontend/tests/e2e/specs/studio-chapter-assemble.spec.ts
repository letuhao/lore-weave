import { test, expect } from '@playwright/test';
import { StudioComposePanels } from '../pages/StudioComposePanels';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, createChapter, trashBook,
  createCompositionWork, createCompositionScene, setSceneStatus, listChatModels,
} from '../helpers/api';

// S1-B2 — the chapter-assemble loop in the STUDIO DOCK. The assemble controls are gated on a model
// being SELECTED (canGen = !!modelRef) AND every scene being done (stitch) — so all scenarios pick a
// model first (picking needs no LLM; only Generate/Regenerate actually call the model).
test.describe('Studio chapter-assemble (S1-B2)', () => {
  let token: string;
  let bookId: string;
  let chapterId: string;
  let sceneId: string;
  let drafter: string | undefined;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    const chatModels = await listChatModels(request, token);
    drafter = (chatModels.find((m) => /Qwen2\.5 7B|non-reasoning|fast/i.test(m.provider_model_name ?? m.alias ?? ''))
      ?? chatModels[0])?.user_model_id;
    bookId = await createBook(request, token, `E2E s1-assemble ${Date.now()}`);
    chapterId = await createChapter(request, token, bookId, 'Assemble chapter');
    const projectId = await createCompositionWork(request, token, bookId);
    sceneId = await createCompositionScene(request, token, projectId, chapterId, 'Opening scene');
  });

  test.afterAll(async ({ request }) => {
    await trashBook(request, token, bookId).catch(() => {});
  });

  test.beforeEach(() => {
    test.skip(!drafter, 'needs ≥1 chat-tagged user-model (to select — no LLM call for the gate tests)');
  });

  test('Stitch is gated until every scene is done — no silent enable', async ({ page, request }) => {
    await setSceneStatus(request, token, sceneId, 'drafting'); // NOT done
    await loginViaUI(page);
    const s = new StudioComposePanels(page);
    await s.gotoStudio(bookId, chapterId);
    await s.openChapterAssemble();
    await s.pickAssembleModel(drafter!); // enable canGen so the ONLY remaining gate is scenes-done
    await expect(s.stitch).toBeDisabled(); // scene not done → blocked

    await setSceneStatus(request, token, sceneId, 'done');
    await page.reload();
    await s.openChapterAssemble();
    await s.pickAssembleModel(drafter!);
    await expect(s.stitch).toBeEnabled(); // gate opened
  });

  test('Assembly mode toggle persists across a reload (per_scene ↔ chapter)', async ({ page }) => {
    await loginViaUI(page);
    const s = new StudioComposePanels(page);
    await s.gotoStudio(bookId, chapterId);
    await s.openChapterAssemble();
    await s.assembleModeChapter.click();
    await expect(s.assembleModeChapter).toBeDisabled(); // active mode = disabled button
    await page.reload();
    await s.openChapterAssemble();
    await expect(s.assembleModeChapter).toBeDisabled(); // persisted (patchWork)
  });

  test.describe('[model-gated]', () => {
    test.beforeEach(() => {
      test.setTimeout(180_000);
    });

    test('Generate chapter → editable preview → Accept inserts into the Editor', async ({ page, request }) => {
      await setSceneStatus(request, token, sceneId, 'drafting'); // generate needs a scene present
      await loginViaUI(page);
      const s = new StudioComposePanels(page);
      await s.gotoStudio(bookId, chapterId); // opens the editor (accept target)
      await s.openChapterAssemble();
      await s.pickAssembleModel(drafter!);

      await expect(s.generateChapter).toBeEnabled();
      await s.generateChapter.click();
      await expect(s.assemblePreview).toBeVisible({ timeout: 120_000 });
      await expect.poll(async () => (await s.assemblePreview.inputValue()).trim().length, { timeout: 120_000 })
        .toBeGreaterThan(20);

      await s.assembleAccept.click();
      await expect(s.assemblePreview).toHaveCount(0); // accepted → preview cleared (landed)
      await s.openEditor();
      await expect.poll(async () => (await s.editorText()).length).toBeGreaterThan(20);
    });

    test('Regenerate captures a correction (second producer of the flywheel)', async ({ page }) => {
      await loginViaUI(page);
      const s = new StudioComposePanels(page);
      await s.gotoStudio(bookId, chapterId);
      await s.openChapterAssemble();
      await s.pickAssembleModel(drafter!);
      await s.generateChapter.click();
      await expect(s.assemblePreview).toBeVisible({ timeout: 120_000 });

      const correction = page.waitForResponse(
        (r) => /\/jobs\/.+\/correction/.test(r.url()) && r.request().method() === 'POST',
        { timeout: 30_000 },
      );
      await s.assembleRegenerate.click();
      const resp = await correction;
      expect(resp.status()).toBeGreaterThanOrEqual(200);
      expect(resp.status()).toBeLessThan(300);
    });
  });
});
