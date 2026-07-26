import { test, expect } from '@playwright/test';
import type { APIRequestContext } from '@playwright/test';
import { getAccessToken } from '../helpers/api';
import { TEST_USER } from '../helpers/auth';

// QC Track-B — S13: the mobile first-run runs ONCE, server-gated (not localStorage). Reset the
// `assistantFirstRunDone` pref server-side, load /assistant on a phone viewport → the safe-defaults
// first-run shows with consent OFF; complete it → it never shows again (the flag is on the server, so a
// fresh reload — even a fresh context — stays past it). Self-restoring (the completion re-sets the flag).
const bearer = (t: string) => ({ headers: { Authorization: `Bearer ${t}` } });
const PHONE = { width: 390, height: 844 };

async function setFirstRunDone(request: APIRequestContext, token: string, value: boolean | null) {
  const r = await request.patch('/v1/me/preferences', { ...bearer(token), data: { prefs: { assistantFirstRunDone: value } } });
  expect(r.ok(), `set pref ${r.status()}`).toBeTruthy();
}

test.describe('Assistant — mobile first-run, server-gated + once (S13)', () => {
  test.use({ viewport: PHONE });

  test('first-run shows once (consent OFF), then never again after completion', async ({ page, request }) => {
    const token = await getAccessToken(request);
    await setFirstRunDone(request, token, null); // reset: pretend this account never onboarded

    // Log in on the phone viewport.
    await page.goto('/login');
    await page.getByTestId('auth-email-input').fill(TEST_USER.email);
    await page.getByTestId('auth-password-input').fill(TEST_USER.password);
    await page.getByTestId('auth-submit-button').click();
    await page.waitForURL('**/books', { timeout: 15_000 });

    await page.goto('/assistant');
    // The first-run screen leads with the privacy promise + a FAIL-CLOSED consent (OFF).
    await expect(page.getByTestId('assistant-first-run')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('first-run-privacy')).toBeVisible();
    expect(await page.getByTestId('first-run-consent').getAttribute('aria-checked'), 'consent OFF by default').toBe('false');

    // Complete it — the flag is written to the server.
    await page.getByTestId('first-run-start').click();
    await expect(page.getByTestId('assistant-first-run')).toBeHidden();

    // Server-gated: a full reload does NOT bring it back (not a per-device localStorage flag).
    await page.goto('/assistant');
    await expect(page.getByTestId('assistant-first-run')).toBeHidden();
    // And the server truly holds it (a fresh read reflects done).
    const prefs = await request.get('/v1/me/preferences', bearer(token));
    expect(prefs.ok()).toBeTruthy();
  });
});
