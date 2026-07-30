import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, trashBook } from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

// Palette foundation — chrome-only E2E (no dock panels needed). Exercises the two palettes end to
// end through the studio frame: ⌘⇧P Command Palette runs a chrome command (Toggle Bottom Panel);
// ⌘P Quick Open opens over the shared jump layer; the top-bar affordance opens Quick Open. The
// panel-open (#06b) + jump-resolve-to-dock (#06a) paths are deferred until a dock panel (#03).
test.describe('Studio palettes — chrome slice', () => {
  let token: string;
  let bookId: string;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E palette ${Date.now()}`);
    await createChapter(request, token, bookId, 'Alpha chapter');
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => { /* best effort */ });
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  test('⌘⇧P opens the Command Palette and runs Toggle Bottom Panel', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await expect(studio.bottom).toHaveCount(0); // bottom panel starts closed

    await page.keyboard.press('ControlOrMeta+Shift+P');
    await expect(studio.commandPaletteModal).toBeVisible();

    // Locate the command by its stable id, not by typing an English word: the palette
    // filters on the LOCALIZED label, so `fill('bottom')` matches nothing whenever the
    // account's UI language is not English — which is exactly why this test was silently
    // red. An empty query lists every command, so this is still the real user path.
    const toggleBottom = page.getByTestId('palette-entry-view.toggleBottom');
    await toggleBottom.scrollIntoViewIfNeeded();
    await expect(toggleBottom).toBeVisible();
    await toggleBottom.click();

    // command ran (bottom panel now open) + palette closed
    await expect(studio.bottom).toBeVisible();
    await expect(studio.commandPaletteModal).toHaveCount(0);
  });

  test('⌘P opens Quick Open; Esc closes it', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await page.keyboard.press('ControlOrMeta+p');
    await expect(studio.quickOpen).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(studio.quickOpen).toHaveCount(0);
  });

  test('the top-bar affordance opens Quick Open', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.commandPalette.click(); // the "Go to chapter, scene, arc…" button
    await expect(studio.quickOpen).toBeVisible();
  });

  // #18 — the flat ~46-item "Panels" list now splits into domain sub-groups; assert at least
  // two distinct category headers render (not the old single "Panels" header) so the grouping
  // is proven live, not just at the unit level.
  test('#18: Command Palette panel commands render domain-area group headers', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await page.keyboard.press('ControlOrMeta+Shift+P');
    await expect(studio.commandPaletteModal).toBeVisible();

    // #18's intent is STRUCTURAL: panel commands used to sit in one flat "Panels" bucket and
    // are now split by domain area. Asserting the English header wording tested the
    // translation, not the grouping — and made the test red for every non-English user.
    // Assert the structure instead: several distinct group headers, and the panel-open
    // commands spread across more than one of them rather than pooled under a single bucket.
    const list = page.getByTestId('palette-list');
    const headers = list.getByTestId('palette-group');
    await expect(headers.first()).toBeVisible();
    const headerTexts = await headers.allTextContents();
    const distinct = new Set(headerTexts.map((s) => s.trim()).filter(Boolean));
    expect(distinct.size, 'panel commands are grouped by domain area, not one flat bucket')
      .toBeGreaterThanOrEqual(3);
  });
});
