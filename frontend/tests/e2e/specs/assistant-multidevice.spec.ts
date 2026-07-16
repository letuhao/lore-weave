import { test, expect } from '@playwright/test';
import { AssistantPage } from '../pages/AssistantPage';
import { getAccessToken } from '../helpers/api';
import { TEST_USER } from '../helpers/auth';

// QC Track-B — multi-device / server-SSOT (S11). The whole multi-device promise rests on "no localStorage
// for user data": a setting made on device A must appear on device B. Here device A = the API, device B =
// a FRESH browser context (its own storage, nothing shared). Set the proactive gate server-side, then open
// the assistant in a clean context and assert the toggle reflects it — i.e. read from the server, not local
// cache. Self-cleaning.
const bearer = (t: string) => ({ headers: { Authorization: `Bearer ${t}` } });

test.describe('Assistant — multi-device server-SSOT (S11)', () => {
  test('a proactive opt-in made via one device shows in a fresh browser context', async ({ browser, request }) => {
    const token = await getAccessToken(request);
    try {
      // Device A — flip the proactive gate ON server-side (a different "device"/origin than the browser).
      const put = await request.patch('/v1/chat/ai-prefs', { ...bearer(token), data: { assistant: { proactive_enabled: true } } });
      expect(put.ok(), `PATCH ai-prefs ${put.status()}`).toBeTruthy();

      // Device B — a brand-new context with its own (empty) storage: nothing could be cached locally.
      const ctx = await browser.newContext();
      try {
        const page = await ctx.newPage();
        const login = { email: TEST_USER.email, password: TEST_USER.password };
        await page.goto('/login');
        await page.getByTestId('auth-email-input').fill(login.email);
        await page.getByTestId('auth-password-input').fill(login.password);
        await page.getByTestId('auth-submit-button').click();
        await page.waitForURL('**/books', { timeout: 15_000 });

        const a = new AssistantPage(page);
        await a.goto();
        // The toggle read its state from the server (ai-prefs) — proving server-SSOT, not localStorage.
        await expect(a.autonomousToggle('proactive_nudge')).toBeVisible();
        expect(await AssistantPage.isOn(a.autonomousToggle('proactive_nudge')), 'fresh device reflects the server opt-in').toBe(true);
      } finally {
        await ctx.close();
      }
    } finally {
      await request.patch('/v1/chat/ai-prefs', { ...bearer(token), data: { assistant: { proactive_enabled: false } } }).catch(() => {});
    }
  });
});
