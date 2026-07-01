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

    await studio.paletteInput.fill('bottom');
    await expect(page.getByTestId('palette-entry-view.toggleBottom')).toBeVisible();
    await page.keyboard.press('Enter');

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
});
