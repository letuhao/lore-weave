import { test, expect } from '@playwright/test';
import { LoginPage } from '../pages/LoginPage';

// F15 — the app must load when the font CDN does not answer.
//
// Found as a "page.goto: Timeout 15000ms exceeded" that recurred across three full runs and was
// first blamed on host starvation. A host sampler disproved that (CPU 26-45%, 17 GB free, no model
// running), and the failing trace named the real cause: `index.html` loads Google Fonts as a normal
// <link rel="stylesheet">, a stylesheet blocks the load event, and the one request that never
// completed was https://fonts.googleapis.com/css2?... — status -1. Every other resource had
// finished in under 200ms.
//
// That is a user-visible defect, not a test hazard: LoreWeave is self-hostable and ships a zh-CN
// locale, and on a network that cannot reach Google (air-gapped, filtered) every page would hang
// behind a cosmetic font. This test makes the CDN hang ON PURPOSE, which is what turns an
// intermittent timeout into a deterministic one.
test.describe('Loads without the font CDN', () => {
  test('login renders when fonts.googleapis.com never answers', async ({ page }) => {
    await page.route(/fonts\.(googleapis|gstatic)\.com/, () => new Promise<void>(() => { /* never answer */ }));
    const login = new LoginPage(page);
    await login.goto();          // waits for "load" — the event a blocking stylesheet withholds
    await login.expectVisible();
    // The fallback stacks already exist (tailwind: Inter → system-ui → sans-serif), so the page is
    // usable in them; the web fonts are an enhancement and must not gate the app.
  });
});
