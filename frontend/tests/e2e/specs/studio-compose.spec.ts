import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, trashBook } from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

// #03 Compose dock panel — the first stateful panel. It's openable from the Command Palette via
// the static panel catalog (a CLOSED panel must still be openable — the mount-scoped registry
// can't do that). Opening it mounts the embedded chat (reused AS-IS) inside a dock tab.
test.describe('Studio Compose panel', () => {
  let token: string;
  let bookId: string;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E compose ${Date.now()}`);
    await createChapter(request, token, bookId, 'Alpha chapter');
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => { /* best effort */ });
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  test('⌘⇧P → "Studio: Open Compose" mounts the chat panel in the dock', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);

    await page.keyboard.press('ControlOrMeta+Shift+P');
    await expect(studio.commandPaletteModal).toBeVisible();
    await studio.paletteInput.fill('Compose');
    await expect(page.getByTestId('palette-entry-studio.openPanel.compose')).toBeVisible();
    await page.keyboard.press('Enter');

    // The compose dock panel is now mounted (its embedded chat renders inside).
    await expect(page.getByTestId('studio-compose-panel')).toBeVisible();
  });
});
