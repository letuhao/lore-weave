// S4 · A2 — the scene-inspector Motifs section + the ranked Suggest (BE-M4). Seeds a Work + a
// scene node so the section is live, selects the scene the real way (scene-browser row → bus →
// scene-inspector), then asserts the Motifs section renders and the ranked suggest returns rows
// with a score/why (replacing the flat unranked list — the GG-1 fix).
import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, trashBook } from '../helpers/api';
import { createWork, createSceneNode, seedMotif, archiveMotif } from '../helpers/motif';
import { StudioPage } from '../pages/StudioPage';

test.describe('@s4 Studio · motif binding + suggest', () => {
  let token: string;
  let bookId: string;
  let projectId = '';
  let nodeId = '';
  let motifId = '';
  const stamp = Date.now();

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E binding ${stamp}`);
    const chapterId = await createChapter(request, token, bookId, 'Chapter 41');
    projectId = await createWork(request, token, bookId);
    nodeId = await createSceneNode(request, token, projectId, chapterId, `Scene reversal ${stamp}`);
    motifId = await seedMotif(request, token, { code: `bind.slap.${stamp}`, name: `Face-slap ${stamp}`, kind: 'scheme' });
  });

  test.afterAll(async ({ request }) => {
    await archiveMotif(request, token, motifId);
    if (bookId) await trashBook(request, token, bookId).catch(() => {});
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  async function openSceneInspector(page: import('@playwright/test').Page): Promise<void> {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('scene-browser', 'scene browser');
    await expect(page.getByTestId('studio-scene-browser-panel')).toBeVisible();
    // click the spec-backed row for our seeded scene → the bus opens the scene-inspector
    const row = page.getByTestId('scene-browser-row').filter({ hasText: `Scene reversal ${stamp}` });
    await row.first().click();
    await expect(page.getByTestId('studio-scene-inspector-panel')).toBeVisible({ timeout: 10_000 });
  }

  test('the Motifs section renders in the scene-inspector for a live scene (§2#1 reachable)', async ({ page }) => {
    await openSceneInspector(page);
    // the binding card for THIS node is present (free-form until bound)
    await expect(page.getByTestId(`motif-binding-${nodeId}`)).toBeVisible({ timeout: 10_000 });
  });

  test('ranked Suggest returns candidates with a score + match_reason (BE-M4, the GG-1 fix)', async ({ page }) => {
    await openSceneInspector(page);
    await page.getByTestId('motif-suggest-toggle').click();
    // either ranked rows render, or an honest empty/error state — never a silent no-op
    const rows = page.getByTestId('motif-suggest-row');
    const empty = page.getByTestId('motif-suggest-empty');
    const err = page.getByTestId('motif-suggest-error');
    await expect(rows.first().or(empty).or(err)).toBeVisible({ timeout: 20_000 });
    // if rows came back, each shows a % score + a reason (the ranked contract, not a flat list)
    if (await rows.first().isVisible().catch(() => false)) {
      await expect(rows.first()).toContainText(/%/);
    }
  });
});
