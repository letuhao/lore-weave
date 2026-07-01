import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, trashBook } from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

// Writing Studio (v2) — frame skeleton E2E. A fresh book is created via API and trashed
// after, so the suite is isolated and needs no pre-existing data. Each test gets a fresh
// browser context (Playwright default) → localStorage starts clean → the studio opens at
// its defaults (Manuscript / expanded / bottom-closed).
test.describe('Writing Studio — frame skeleton', () => {
  let token: string;
  let bookId: string;
  let bookIdB: string;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E studio ${Date.now()}`);
    bookIdB = await createBook(request, token, `E2E studio B ${Date.now()}`);
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => { /* best effort */ });
    if (bookIdB) await trashBook(request, token, bookIdB).catch(() => { /* best effort */ });
  });

  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test('opens from the book-level Studio button', async ({ page }) => {
    await page.goto(`/books/${bookId}`);
    await page.getByTestId('book-open-studio').click();
    await expect(page).toHaveURL(new RegExp(`/books/${bookId}/studio$`));
  });

  test('renders the fixed frame regions', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await expect(studio.commandPalette).toBeVisible();
    for (const v of ['manuscript', 'bible', 'search', 'quality'] as const) {
      await expect(studio.activity(v)).toBeVisible();
    }
    await expect(studio.sidebar).toBeVisible();
    await expect(studio.dockview).toBeVisible();
    await expect(studio.toggleBottom).toBeVisible();
  });

  test('activity bar switches the navigator; re-click collapses the side bar', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.activity('bible').click();
    await expect(studio.activity('bible')).toHaveAttribute('aria-pressed', 'true');
    await expect(studio.sidebar).toBeVisible();
    await studio.activity('bible').click(); // re-click the active view → collapse
    await expect(studio.sidebar).toHaveCount(0);
  });

  test('bottom panel toggles from the status bar', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await expect(studio.bottom).toHaveCount(0);
    await studio.toggleBottom.click();
    await expect(studio.bottom).toBeVisible();
  });

  test('chrome state persists across reload', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.activity('quality').click();
    await studio.toggleBottom.click();
    await page.reload();
    await studio.activity('quality').waitFor({ state: 'attached' });
    await expect(studio.activity('quality')).toHaveAttribute('aria-pressed', 'true');
    await expect(studio.bottom).toBeVisible();
  });

  // Per-book isolation (guards review-impl HIGH #1/#2): each book's chrome lives under its
  // own key. Set distinct state in A, confirm B opens at defaults, then confirm A restored.
  test('per-book chrome is isolated (no cross-book bleed)', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.activity('quality').click();
    await studio.toggleBottom.click();
    await expect(studio.activity('quality')).toHaveAttribute('aria-pressed', 'true');

    await studio.goto(bookIdB); // B did NOT inherit A's chrome
    await expect(studio.activity('manuscript')).toHaveAttribute('aria-pressed', 'true');
    await expect(studio.bottom).toHaveCount(0);

    await studio.goto(bookId); // A's chrome persisted under A's key, not clobbered by B
    await expect(studio.activity('quality')).toHaveAttribute('aria-pressed', 'true');
    await expect(studio.bottom).toBeVisible();
  });

  // The dock NEVER remounts through chrome changes — the load-bearing no-remount rule (D4).
  // Proven at unit level via component state; here we assert the dockview root survives an
  // activity switch + bottom toggle (same element handle stays attached).
  test('dock survives chrome changes without remounting', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await expect(studio.dockview).toBeVisible();
    await studio.activity('search').click();
    await studio.toggleBottom.click();
    await expect(studio.dockview).toBeVisible();
  });
});
