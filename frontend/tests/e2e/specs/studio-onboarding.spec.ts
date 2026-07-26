import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, trashBook, resetStudioRolePref } from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

// #19 Wave 1 — Studio onboarding (role picker) + core guided tour + catalog-driven User Guide.
// #19 Wave 2 — "Start Guided Tour" now starts the ACCOUNT'S ROLE tour (falling back to `core`
// only when no role is set — StudioFrame.tsx `tour.start(onboarding.role ?? 'core')`). Since the
// role pref is a server-synced ACCOUNT-level preference (not per-book, not per-test), tests in
// this file share state across each other and across runs — the role-picker test below sets
// `worldbuilder`, so any test that needs the `core` tour specifically resets the role via
// `resetStudioRolePref` (a direct API PATCH) first. Note the UI's own Skip button does NOT clear
// a role once picked (Skip only sets the seen-flag by design — useStudioOnboarding.ts) — this
// broke the original core-tour test the first time Wave 2 shipped, caught by live E2E, not by
// unit tests (each hook's unit tests mock the other, so the cross-hook interaction was invisible
// until real DOM + a real shared account exposed it).
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
    // This suite picks a role (worldbuilder) on the shared account — reset it so other spec
    // files / future runs that assume a no-role default aren't left with a sticky role.
    await resetStudioRolePref(request, token).catch(() => { /* best effort */ });
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

  test('#19: "Studio: Start Guided Tour" runs the core tour end to end (skip mid-tour, no hang)', async ({ page, request }) => {
    // Wave 2: "Start Guided Tour" starts the account's ROLE tour if one is set, else `core` —
    // reset to no-role first (API-level; the UI's Skip button does not clear a role) so this
    // test deterministically gets `core` regardless of what an earlier test in this file (or a
    // previous run) left the shared account's role pref as.
    await resetStudioRolePref(request, token);

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

  test('#19 Wave 2: "Start Guided Tour" runs the account\'s ROLE tour once a role is set', async ({ page, request }) => {
    const studio = new StudioPage(page);
    await studio.goto(bookId);

    // Pick "worldbuilder" — its tour is glossary → wiki → knowledge (catalog tourAnchor-driven,
    // not core's hardcoded selectors).
    await page.keyboard.press('ControlOrMeta+Shift+P');
    await studio.paletteInput.fill('choose your focus');
    await page.getByTestId('palette-entry-studio.chooseYourFocus').click();
    await expect(page.getByTestId('studio-onboarding-overlay')).toBeVisible();
    await page.getByTestId('studio-onboarding-role-worldbuilder').click();
    await expect(page.getByTestId('studio-onboarding-overlay')).toHaveCount(0);

    await page.keyboard.press('ControlOrMeta+Shift+P');
    await studio.paletteInput.fill('start guided tour');
    await page.getByTestId('palette-entry-studio.startGuidedTour').click();
    await expect(studio.commandPaletteModal).toHaveCount(0);

    // Step 1/3 opens Glossary before anchoring on its catalog tourAnchor.
    await expect(page.getByTestId('studio-glossary-panel')).toBeVisible();
    await expect(page.getByTestId('studio-tour-tooltip')).toBeVisible();
    await page.getByTestId('studio-tour-next').click();

    // Step 2/3 opens Wiki.
    await expect(page.getByTestId('studio-wiki-panel')).toBeVisible();
    await expect(page.getByTestId('studio-tour-tooltip')).toBeVisible();
    await page.getByTestId('studio-tour-next').click();

    // Step 3/3 opens Knowledge (the one panel whose tourAnchor testid — studio-knowledge-hub-panel
    // — does NOT match `studio-${id}-panel`, proving the tourAnchor field, not a derived string,
    // is what the tour actually reads).
    await expect(page.getByTestId('studio-knowledge-hub-panel')).toBeVisible();
    await expect(page.getByTestId('studio-tour-tooltip')).toBeVisible();
    await page.getByTestId('studio-tour-next').click();
    await expect(page.getByTestId('studio-tour-tooltip')).toHaveCount(0);

    // Reset the shared account back to no-role (API-level — the UI's Skip button does not clear
    // a role) so later/other runs of this file (or unrelated tests reusing this account) aren't
    // left with `worldbuilder` sticking as the default tour.
    await resetStudioRolePref(request, token);
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
