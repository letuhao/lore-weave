import { test, expect } from '@playwright/test';
import { StudioComposePanels } from '../pages/StudioComposePanels';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken, createBook, trashBook, seedRichChapter,
  createCompositionWork, createCompositionScene, setSceneStatus,
} from '../helpers/api';

// S1-B4 — the publish gate in the STUDIO Editor (EditorPublishGate). NO MODEL. Proves the §2-bar:
// reachable, gated with a VISIBLE reason (no silent fail), transitions correctly, and publishes.
test.describe('Studio editor publish gate (S1-B4)', () => {
  let token: string;
  let bookId: string;
  let chapterId: string;
  let sceneId: string;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E s1-publish ${Date.now()}`);
    // A publishable chapter needs real prose (an empty chapter is rejected). seedRichChapter fetches
    // the draft version internally, so no stale-version conflict.
    chapterId = await seedRichChapter(request, token, bookId, 'Publish chapter', 'A first chapter of prose to publish, long enough to be a real chapter body.');
    const projectId = await createCompositionWork(request, token, bookId);
    sceneId = await createCompositionScene(request, token, projectId, chapterId, 'Opening scene');
  });

  test.afterAll(async ({ request }) => {
    await trashBook(request, token, bookId).catch(() => {});
  });

  test('gated with a visible reason → mark scene done → enables → publishes', async ({ page, request }) => {
    await setSceneStatus(request, token, sceneId, 'drafting'); // NOT done → publish must be blocked
    await loginViaUI(page);
    const s = new StudioComposePanels(page);
    await s.gotoStudio(bookId, chapterId); // opens the editor
    await s.openEditor();

    // Blocked — and it SAYS WHY (no silent fail): the button is disabled + carries a non-empty reason.
    await expect(s.publishButton).toBeDisabled();
    expect(await s.publishButton.getAttribute('title')).toBeTruthy();

    // Satisfy the gate → the control must transition to enabled on reload.
    await setSceneStatus(request, token, sceneId, 'done');
    await page.reload();
    await s.openEditor();
    await expect(s.publishButton).toBeEnabled();

    // Publish runs to a real result (a successful publish POST) — operable, not a dead button.
    const publish = page.waitForResponse(
      (r) => /\/chapters\/.+\/publish/.test(r.url()) && r.request().method() === 'POST',
      { timeout: 30_000 },
    );
    await s.publishButton.click();
    const resp = await publish;
    expect(resp.status()).toBeGreaterThanOrEqual(200);
    expect(resp.status()).toBeLessThan(300);
  });
});
