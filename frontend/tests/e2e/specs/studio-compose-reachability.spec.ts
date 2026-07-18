import { test, expect } from '@playwright/test';
import { StudioComposePanels } from '../pages/StudioComposePanels';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, createChapter, trashBook,
  createCompositionWork, createCompositionScene,
} from '../helpers/api';

// S1 §2-bar #2/#3 — REACHABILITY + not-a-skeleton. NO LLM: proves the studio-dock compose panels are
// palette-openable and mount the REAL loop controls (the "cho có / skeleton" failure this whole track
// exists to kill). Always runs in CI — it needs no model.
test.describe('Studio compose panels — reachability + real mount (no model)', () => {
  let token: string;
  let bookId: string;
  let chapterId: string;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E s1-reach ${Date.now()}`);
    chapterId = await createChapter(request, token, bookId, 'Reach chapter');
    const projectId = await createCompositionWork(request, token, bookId);
    await createCompositionScene(request, token, projectId, chapterId, 'Opening scene');
  });

  test.afterAll(async ({ request }) => {
    await trashBook(request, token, bookId).catch(() => {});
  });

  test('scene-compose is palette-openable and mounts the real draft loop (scene + model + Generate)', async ({ page }) => {
    await loginViaUI(page);
    const s = new StudioComposePanels(page);
    await s.gotoStudio(bookId, chapterId);
    await s.openSceneCompose();

    // Real loop, not a skeleton: the scene selector, the model picker, and Generate are all present.
    await expect(s.sceneSelect).toBeVisible();
    await expect(s.modelSelect).toBeVisible();
    await expect(s.generate).toBeVisible();
  });

  test('chapter-assemble is palette-openable and mounts the real assemble loop (mode + Generate + Stitch)', async ({ page }) => {
    await loginViaUI(page);
    const s = new StudioComposePanels(page);
    await s.gotoStudio(bookId, chapterId);
    await s.openChapterAssemble();

    await expect(s.assembleModePerScene).toBeVisible();
    await expect(s.assembleModeChapter).toBeVisible();
    await expect(s.generateChapter).toBeVisible();
    await expect(s.stitch).toBeVisible();
  });

  test('a compose panel survives a dock close + reopen (dockview unmount/remount, no crash)', async ({ page }) => {
    await loginViaUI(page);
    const s = new StudioComposePanels(page);
    await s.gotoStudio(bookId, chapterId);
    await s.openSceneCompose();
    await expect(s.sceneComposePanel).toBeVisible();
    await s.studio.closePanel('Scene Compose');
    await expect(s.sceneComposePanel).toHaveCount(0);
    await s.openSceneCompose(); // reopen — must remount cleanly
    await expect(s.generate).toBeVisible();
  });

  test('both panels appear in the User Guide with non-empty guide copy (§2-bar #3 discoverable)', async ({ page }) => {
    await loginViaUI(page);
    const s = new StudioComposePanels(page);
    await s.gotoStudio(bookId);
    await s.studio.openPanel('user-guide', 'User Guide');
    // The guide renders every openable panel by category; scene-compose + chapter-assemble carry a
    // guideBodyKey with real en copy (panelCatalogContract enforces it), so their titles render here.
    await expect(page.getByText('Scene Compose', { exact: false }).first()).toBeVisible();
    await expect(page.getByText('Chapter Assemble', { exact: false }).first()).toBeVisible();
  });
});
