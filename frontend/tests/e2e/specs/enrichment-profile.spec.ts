import { test, expect } from '@playwright/test';
import { LoginPage } from '../pages/LoginPage';
import { EnrichmentTab } from '../pages/EnrichmentTab';
import { TEST_USER } from '../helpers/auth';

// The seeded demo Fengshen book (owned by the test user). Override via env.
const BOOK = process.env.E2E_BOOK_ID ?? '019e7850-a8d9-78dd-8b2a-f33ccc2396ad';

// LE-068 — browser-layer e2e of the de-bias C3 GUI: it exercises the real chain
// (login → gateway → FE → Enrichment tab → lore-enrichment + book-service) that
// the unit tests mock. The profile tab is the core C3 proof; the gaps detect
// proves the C2 "extract first" signal is wired (and absent for an extracted book).
test.describe('Enrichment GUI — de-bias C3 (profile authoring + gaps)', () => {
  test.beforeEach(async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.expectVisible();
    await login.login(TEST_USER.email, TEST_USER.password);
    await page.waitForURL('**/books', { timeout: 15_000 });
  });

  test('Profile tab loads the seeded book profile + suggest/save controls', async ({ page }) => {
    const enr = new EnrichmentTab(page);
    await enr.goto(BOOK);

    // the enrichment shell renders its tab strip incl. the new Profile tab
    await expect(enr.tab('settings')).toBeVisible();
    await enr.openPanel('settings');

    // ProfileForm renders, seeded from GET /books/{id}/profile (owner-checked via
    // book-service) — for the demo Fengshen book the worldview is non-empty.
    await expect(enr.worldview).toBeVisible();
    await expect(enr.worldview).not.toHaveValue('');
    await expect(enr.suggestButton).toBeVisible();
    await expect(enr.saveButton).toBeVisible();
    // suggest is disabled until a model is picked (no accidental LLM spend)
    await expect(enr.suggestButton).toBeDisabled();
  });

  test('Gaps detect on the extracted demo book never shows the "extract first" state', async ({ page }) => {
    const enr = new EnrichmentTab(page);
    await enr.goto(BOOK);
    await enr.openPanel('gaps');
    await enr.detectButton.click();

    // detect resolves to a gaps table or "no gaps" — but the demo book IS
    // extracted, so the C2 unextracted "extract first" notice must NOT appear.
    await expect(enr.extractFirstNotice).toHaveCount(0, { timeout: 20_000 });
  });
});
