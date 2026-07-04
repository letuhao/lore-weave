import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, trashBook } from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

// #19 Wave 1 — Studio onboarding (role picker) + core guided tour + catalog-driven User Guide.
// The role-picker's first-run gate is a server-synced account-level preference (not per-book),
// and this shared test account has likely already completed it in a prior run — so these tests
// exercise the two Command Palette commands ("Studio: Choose Your Focus" / "Studio: Start Guided
// Tour") that re-trigger both flows on demand, rather than depending on first-run state.
test.describe('Studio onboarding — role picker + guided tour + user guide', () => {
  let token: string;
  let bookId: string;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E onboarding ${Date.now()}`);
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => { /* best effort */ });
  });

  test.beforeEach(async ({ page }) => { await loginViaUI(page); });

  test('#19: "Studio: Choose Your Focus" reopens the role picker; picking a role dismisses it', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);

    await page.keyboard.press('ControlOrMeta+Shift+P');
    await studio.commandPaletteModal.waitFor({ state: 'visible' });
    await studio.paletteInput.fill('choose your focus');
    await page.getByTestId('palette-entry-studio.chooseYourFocus').click();
    await expect(studio.commandPaletteModal).toHaveCount(0);

    await expect(page.getByTestId('studio-onboarding-overlay')).toBeVisible();
    await page.getByTestId('studio-onboarding-role-worldbuilder').click();
    await expect(page.getByTestId('studio-onboarding-overlay')).toHaveCount(0);
  });

  test('#19: the role picker is always skippable (Esc), never a trap', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await page.keyboard.press('ControlOrMeta+Shift+P');
    await studio.paletteInput.fill('choose your focus');
    await page.getByTestId('palette-entry-studio.chooseYourFocus').click();
    await expect(page.getByTestId('studio-onboarding-overlay')).toBeVisible();

    await page.getByTestId('studio-onboarding-skip').click();
    await expect(page.getByTestId('studio-onboarding-overlay')).toHaveCount(0);
  });

  test('#19: "Studio: Start Guided Tour" runs the core tour end to end (skip mid-tour, no hang)', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);

    await page.keyboard.press('ControlOrMeta+Shift+P');
    await studio.paletteInput.fill('start guided tour');
    await page.getByTestId('palette-entry-studio.startGuidedTour').click();
    await expect(studio.commandPaletteModal).toHaveCount(0);

    // Step 1/4 (manuscript, chrome-only) — the tooltip renders anchored live.
    await expect(page.getByTestId('studio-tour-tooltip')).toBeVisible();
    await page.getByTestId('studio-tour-next').click();
    // Step 2/4 (command palette, chrome-only).
    await expect(page.getByTestId('studio-tour-tooltip')).toBeVisible();
    await page.getByTestId('studio-tour-next').click();

    // Step 3/4 opens the Compose panel before anchoring — proves the idempotent-open-per-step path.
    await expect(page.getByTestId('studio-compose-panel')).toBeVisible();
    await expect(page.getByTestId('studio-tour-tooltip')).toBeVisible();

    // Skip mid-tour — must close cleanly (no hang, no leftover overlay).
    await page.getByTestId('studio-tour-skip').click();
    await expect(page.getByTestId('studio-tour-tooltip')).toHaveCount(0);
  });

  test('#19: the User Guide panel opens from the palette and its Open buttons open panels', async ({ page }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('user-guide', 'user guide');

    await expect(page.getByTestId('studio-user-guide-panel')).toBeVisible();
    await expect(page.getByTestId('studio-user-guide-group-editor')).toBeVisible();
    await expect(page.getByTestId('studio-user-guide-open-editor')).toBeVisible();

    await page.getByTestId('studio-user-guide-open-editor').click();
    await expect(page.getByTestId('studio-editor-panel')).toBeVisible();
  });
});
