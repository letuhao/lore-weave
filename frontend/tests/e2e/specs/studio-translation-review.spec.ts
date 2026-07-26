import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, seedRichChapter, trashBook, createTranslationJob, waitForTranslationJob } from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

// 16_chapter_editor_parity_and_retirement.md Phase 3 — the Translate quick-access button +
// TranslationReviewPanel + the DOCK-7 fix on TranslationViewer's Review button. A REAL translate
// job (small chapter, fast local chat model — completes in ~5-15s) rather than a mock, per this
// repo's "prefer real E2E over hand-fed smoke" convention: a mocked version list would prove
// nothing about the actual cross-service wiring these panels depend on.
test.describe('Studio Translation Review (#16 Phase 3)', () => {
  let token: string;
  let bookId: string;
  let chapterId: string;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E translation-review ${Date.now()}`);
    chapterId = await seedRichChapter(
      request, token, bookId, 'Ch1',
      'The old wizard walked slowly through the misty forest, searching for the lost amulet.',
    );
    const jobId = await createTranslationJob(request, token, bookId, chapterId, 'vi');
    await waitForTranslationJob(request, token, jobId);
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => { /* best effort */ });
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  // A brand-new book's first Studio visit shows a "Welcome to Writing Studio" role-picker
  // overlay that blocks the navigator underneath — dismiss it if present.
  async function dismissWelcomeIfPresent(page: import('@playwright/test').Page): Promise<void> {
    const skip = page.getByText('Skip, I', { exact: false });
    if (await skip.isVisible({ timeout: 2000 }).catch(() => false)) await skip.click();
  }

  test('Translate quick-access button opens translation-versions scoped to the open chapter', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await dismissWelcomeIfPresent(page);
    await page.getByTestId(`manuscript-row-${chapterId}`).click();
    await expect(page.getByTestId('studio-editor-panel')).toBeVisible();

    await page.getByTestId('studio-editor-open-translate').click();
    await expect(page.getByTestId('studio-translation-versions')).toBeVisible();
    // The real translated version is there (matrix/language auto-select landed on it).
    await expect(page.getByTestId('studio-translation-versions')).toContainText('vi');
  });

  test('Review button opens TranslationReviewPanel WITHOUT navigating away from the studio (DOCK-7 fix)', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await dismissWelcomeIfPresent(page);
    await page.getByTestId(`manuscript-row-${chapterId}`).click();
    await page.getByTestId('studio-editor-open-translate').click();
    await expect(page.getByTestId('studio-translation-versions')).toBeVisible();

    await page.getByText('Review', { exact: true }).first().click();

    // The DOCK-7 proof: still inside the studio, not a full-page navigate to /review/:versionId.
    await expect(page).toHaveURL(new RegExp(`/books/${bookId}/studio$`));
    await expect(page.getByTestId('studio-translation-review')).toBeVisible();
    // Real block-aligned content from the real job, not a stub.
    await expect(page.getByTestId('studio-translation-review')).toContainText('misty forest');

    // A real sibling dock tab exists (not a full-page swap) — dockview's default tab strip
    // shows both, even though only the active tab's content stays mounted.
    await expect(page.getByText('Translation Versions', { exact: false })).toBeVisible();
  });
});
