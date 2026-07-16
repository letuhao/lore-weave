import { test, expect } from '@playwright/test';
import { AssistantPage } from '../pages/AssistantPage';
import { loginViaUI, TEST_USER } from '../helpers/auth';

// QC Track-B — REAL-USER experiential pass. The MCP browsers are contended (F-QC-2), so this drives the
// real built app (:5185) and captures screenshots of each user-facing state for a human-perspective UX
// review (the agent reads + evaluates the PNGs). Read-only on the shared account (no distill/erase); the
// mobile first-run is exercised on a throwaway pref reset. Screenshots → tests/e2e/test-results/journey/.
const DIR = 'tests/e2e/test-results/journey';

test.describe('Assistant — real-user journey (screenshots for UX eval)', () => {
  test('desktop: landing → home → memory → autonomous', async ({ page }) => {
    test.setTimeout(60_000);
    await loginViaUI(page);

    // 1) What a user sees the moment they open the assistant (before we dismiss anything).
    await page.goto('/assistant');
    await page.waitForTimeout(1500); // let provisioning + any modal settle (capture the real first impression)
    await page.screenshot({ path: `${DIR}/01-landing-raw.png`, fullPage: true });

    // 2) The working home (dialog dismissed) — the actual control surface.
    const a = new AssistantPage(page);
    await expect(a.greeting).toBeVisible({ timeout: 20_000 });
    await a.dismissNewChatDialog();
    await page.screenshot({ path: `${DIR}/02-home.png`, fullPage: true });

    // 3) The memory / data-rights sheet.
    await a.openMemorySheet();
    await page.screenshot({ path: `${DIR}/03-memory.png`, fullPage: true });
  });

  test('mobile: first-run onboarding', async ({ page, request }) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width: 390, height: 844 });
    // Reset the first-run flag so we see the real onboarding a newcomer gets.
    const token = await (await import('../helpers/api')).getAccessToken(request);
    await request.patch('/v1/me/preferences', { headers: { Authorization: `Bearer ${token}` }, data: { prefs: { assistantFirstRunDone: null } } });

    await page.goto('/login');
    await page.getByTestId('auth-email-input').fill(TEST_USER.email);
    await page.getByTestId('auth-password-input').fill(TEST_USER.password);
    await page.getByTestId('auth-submit-button').click();
    await page.waitForURL('**/books', { timeout: 15_000 });

    await page.goto('/assistant');
    await expect(page.getByTestId('assistant-first-run')).toBeVisible({ timeout: 20_000 });
    await page.screenshot({ path: `${DIR}/04-mobile-firstrun.png`, fullPage: true });

    // complete it so we don't leave the account mid-onboarding
    await page.getByTestId('first-run-start').click();
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${DIR}/05-mobile-home.png`, fullPage: true });
  });
});
