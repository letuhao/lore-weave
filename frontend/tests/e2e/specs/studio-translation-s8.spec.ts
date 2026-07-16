import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, trashBook } from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

// S8 · Translation (spec 29) — drives the REAL `translation` studio panel end to end: the matrix
// operability core (T1/T2), the modal + closed-set language picker (D1/D13), the selection hand-off
// (T8), and degraded-mode (T4/D9) via a forced coverage failure. data-testid selectors only
// (i18n-agnostic, per tests/e2e/CONVENTIONS.md).
test.describe('S8 Translation — matrix operability', () => {
  let token: string;
  let bookId: string;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E s8-translation ${Date.now()}`);
    await createChapter(request, token, bookId, 'Chapter One');
    await createChapter(request, token, bookId, 'Chapter Two');
    await createChapter(request, token, bookId, 'Chapter Three');
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => { /* best effort */ });
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  async function openMatrix(page: import('@playwright/test').Page) {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('translation', 'Translation');
    await expect(page.getByTestId('studio-translation-panel')).toBeVisible();
  }

  /** Force the matrix past the fresh-book empty state (D2): a non-empty known_languages makes
   *  visibleLangs > 0, so every real chapter renders as a left-joined row (T2/D3). */
  async function withTranslatedLanguage(page: import('@playwright/test').Page) {
    await page.route('**/v1/translation/books/**/coverage', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ book_id: bookId, known_languages: ['vi'], coverage: [] }) }),
    );
  }

  test('T1: the header Translate CTA outlives the empty state (enabled for an owner with chapters)', async ({ page }) => {
    await openMatrix(page);
    const cta = page.getByTestId('matrix-translate-cta');
    await expect(cta).toBeVisible();
    await expect(cta).toBeEnabled();
    // C2: an owner sees no view-only banner
    await expect(page.getByTestId('matrix-view-only')).toHaveCount(0);
  });

  test('T2/D3: with a translated language, every chapter (incl. untranslated) renders as a selectable row', async ({ page }) => {
    await withTranslatedLanguage(page);
    await openMatrix(page);
    for (const title of ['Chapter One', 'Chapter Two', 'Chapter Three']) {
      await expect(page.getByRole('checkbox', { name: title })).toBeVisible();
    }
  });

  test('D1/D13: the header CTA opens the modal with a closed-set language picker (registry only)', async ({ page }) => {
    await openMatrix(page);
    await page.getByTestId('matrix-translate-cta').click();
    await expect(page.getByTestId('translate-modal-body')).toBeVisible();
    const picker = page.getByTestId('translate-language-picker');
    await expect(picker).toBeVisible();
    // the closed registry is offered (vi/ja present) …
    await expect(picker.locator('option[value="vi"]')).toHaveCount(1);
    await expect(picker.locator('option[value="ja"]')).toHaveCount(1);
    // … and the legacy free-text value is NOT selectable (D13: if you can't pick it you can't submit it)
    await expect(picker.locator('option[value="Vietnamese"]')).toHaveCount(0);
  });

  test('T8: ticking chapters + Translate Selected opens the modal (selection handed off, not discarded)', async ({ page }) => {
    await withTranslatedLanguage(page);
    await openMatrix(page);
    await page.getByRole('checkbox', { name: 'Chapter Two' }).check();
    await page.getByRole('checkbox', { name: 'Chapter Three' }).check();
    await page.getByTestId('matrix-translate-selected').click();
    await expect(page.getByTestId('translate-modal-body')).toBeVisible();
    // the language picker renders immediately (T5: pickers are not gated on the chapter-list fetch)
    await expect(page.getByTestId('translate-language-picker')).toBeVisible();
  });

  test('T4/D9: a coverage failure renders a typed error + Retry, never a raw proxy string', async ({ page }) => {
    // Force the coverage call to fail (deterministic degraded-mode — no need to stop the service).
    await page.route('**/v1/translation/books/**/coverage', (route) =>
      route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ code: 'X', message: 'Error occurred while trying to proxy' }) }),
    );
    await openMatrix(page);
    const err = page.getByTestId('translation-error');
    await expect(err).toBeVisible();
    await expect(err).toHaveAttribute('data-kind', 'retryable');
    await expect(page.getByTestId('translation-error-retry')).toBeVisible();
    // the raw proxy string is never shown to the user
    await expect(page.getByText(/trying to proxy/)).toHaveCount(0);
  });
});
