import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, trashBook } from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

// S8 · BLACKBOX-USER JOURNEY — walks a real web-novel author through the translation flow on the
// LIVE app and screenshots each step so a human can judge "is this actually usable?". Not just
// assertions — the screenshots are the evaluation artifact. Runs at 1280x800 (desktop author).
const SHOT = (name: string) => `s8-journey/${name}.png`;

test.describe('S8 Translation — blackbox author journey', () => {
  let token: string;
  let bookId: string;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `Journey — Dracula VI ${Date.now()}`);
    await createChapter(request, token, bookId, 'Chapter I — Jonathan Harker’s Journal');
    await createChapter(request, token, bookId, 'Chapter II — The Castle');
    await createChapter(request, token, bookId, 'Chapter III — A Prisoner');
  });
  test.afterAll(async ({ request }) => { if (bookId) await trashBook(request, token, bookId).catch(() => {}); });
  test.beforeEach(async ({ page }) => { await page.setViewportSize({ width: 1280, height: 800 }); await loginViaUI(page); });

  test('the author opens Translation and reaches a working translate flow', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);

    // Step 1 — open the Translation panel the way a real user does (command palette).
    await studio.openPanel('translation', 'Translation');
    await expect(page.getByTestId('studio-translation-panel')).toBeVisible();
    await page.screenshot({ path: SHOT('1-matrix-fresh-book') });
    // A fresh book has no translations → the empty state must offer a discoverable primary action.
    const cta = page.getByTestId('matrix-translate-cta');
    await expect(cta).toBeVisible();

    // Step 2 — open the translate modal from the header CTA.
    await cta.click();
    await expect(page.getByTestId('translate-modal-body')).toBeVisible();
    await page.screenshot({ path: SHOT('2-translate-modal') });

    // Step 3 — the author picks a target language from the closed picker.
    const picker = page.getByTestId('translate-language-picker');
    await expect(picker).toBeVisible();
    await picker.selectOption('vi');
    await page.screenshot({ path: SHOT('3-language-picked-vi') });

    // Step 4 — the chapter checklist is visible + the author can see what will be translated.
    // (The model picker + summary should be present; a real author needs to see the scope.)
    await page.screenshot({ path: SHOT('4-modal-with-scope') });

    // Step 5 — a book WITH an existing translation shows the coverage matrix with per-chapter rows.
    await page.route('**/v1/translation/books/**/coverage', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        book_id: bookId, known_languages: ['vi', 'ja'],
        coverage: [{ chapter_id: 'seed', languages: { vi: { has_active: true, active_version_num: 1, latest_version_num: 1, latest_status: 'completed', version_count: 1, is_glossary_stale: false } } }],
      }) }),
    );
    await page.keyboard.press('Escape'); // close modal
    await studio.goto(bookId);
    await studio.openPanel('translation', 'Translation');
    await expect(page.getByRole('checkbox', { name: /Jonathan Harker/ })).toBeVisible();
    await page.screenshot({ path: SHOT('5-matrix-with-coverage') });

    // Step 6 — the degraded experience: the service is down. The author must see a clear reason + Retry,
    // never a raw proxy string or a blank panel.
    await page.unroute('**/v1/translation/books/**/coverage');
    await page.route('**/v1/translation/books/**/coverage', (route) =>
      route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ message: 'Error occurred while trying to proxy' }) }),
    );
    await studio.goto(bookId);
    await studio.openPanel('translation', 'Translation');
    await expect(page.getByTestId('translation-error')).toBeVisible();
    await page.screenshot({ path: SHOT('6-degraded-typed-error') });
  });
});
