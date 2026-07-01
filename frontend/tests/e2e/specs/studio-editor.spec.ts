import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, trashBook } from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

// #04 · navigator → dock (Debt #1 cleared) + the Tier-4 manuscript-unit hoist. Selecting a chapter
// in the navigator publishes it on the bus + opens the editor dock; the ManuscriptUnitProvider
// (above dockview) loads the draft and the thin editor panel renders it.
test.describe('Studio manuscript editor (Tier-4 hoist)', () => {
  let token: string;
  let bookId: string;
  let chapterId: string;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E editor ${Date.now()}`);
    chapterId = await createChapter(request, token, bookId, 'Alpha chapter');
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => { /* best effort */ });
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  test('selecting a chapter in the navigator opens the editor dock + loads the draft', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await expect(page.getByTestId(`manuscript-row-${chapterId}`)).toBeVisible();

    // Navigator → dock: click the chapter row.
    await page.getByTestId(`manuscript-row-${chapterId}`).click();

    // The editor dock panel mounts and loads the unit (the loaded view has a Save affordance;
    // the empty-placeholder view does not).
    await expect(page.getByTestId('studio-editor-panel')).toBeVisible();
    await expect(page.getByTestId('studio-editor-save')).toBeVisible();
  });
});
