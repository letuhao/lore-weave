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
    // The panel's title is "Co-writer Chat" (studio.json panels.compose.title), so typing
    // "Compose" correctly matches nothing -- it was renamed. Rather than swap in the new
    // English word and be broken again by the next rename or a translation, the entry is
    // reached BY TESTID, which is the language-agnostic contract (E2E CONVENTIONS S1), and
    // CLICKED rather than Enter-ed: Enter runs whatever is highlighted, which is an assumption
    // about list order, not about this command.
    const entry = page.getByTestId('palette-entry-studio.openPanel.compose');
    await entry.scrollIntoViewIfNeeded();
    await expect(entry).toBeVisible();
    await entry.click();

    // The compose dock panel is now mounted (its embedded chat renders inside).
    await expect(page.getByTestId('studio-compose-panel')).toBeVisible();
  });
});
