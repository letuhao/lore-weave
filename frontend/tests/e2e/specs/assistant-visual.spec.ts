import { test, expect } from '@playwright/test';
import { AssistantPage } from '../pages/AssistantPage';
import { loginViaUI } from '../helpers/auth';

// QC Track-B — CV / verify-by-EFFECT pass. The Playwright MCP browser was contended by the parallel
// sessions ("already in use"), so this runs through the isolated harness against the BUILT image (:5185) —
// the same intent: confirm the real rendered UI, not a raw stream/unit mock. Captures screenshots at ≥2
// cross-cutting seams (the assistant home; the memory data-rights sheet) and asserts the VISIBLE effect. It
// also walks the accessibility tree as a light exploratory pass (findings → RUN-STATE §6). Non-destructive.
test.describe('Assistant — verify-by-effect (CV) + exploratory pass', () => {
  test('seam 1 — the assistant home renders its controls (screenshot + a11y)', async ({ page }, testInfo) => {
    await loginViaUI(page);
    const a = new AssistantPage(page);
    await a.goto();

    // The effect: the greeting, consent, the autonomous panel + Practice entry are all really painted.
    await expect(a.greeting).toBeVisible();
    await expect(a.consentToggle).toBeVisible();
    await expect(a.autonomousSettings).toBeVisible();
    await expect(a.practiceLink).toBeVisible();

    const shot = await page.screenshot({ fullPage: true });
    await testInfo.attach('assistant-home', { body: shot, contentType: 'image/png' });

    // Light exploratory: the accessibility tree names the switch controls (proves they're real a11y widgets,
    // not decorative divs) — a discoverability + a11y signal.
    const switches = await page.getByRole('switch').count();
    expect(switches, 'the home exposes real switch controls (consent + autonomous)').toBeGreaterThan(0);
  });

  test('seam 2 — the memory data-rights sheet renders forget + erase (screenshot)', async ({ page }, testInfo) => {
    await loginViaUI(page);
    const a = new AssistantPage(page);
    await a.goto();
    await a.openMemorySheet();

    // The effect: recall search + the erase danger-zone are visibly present in the opened sheet.
    await expect(a.memorySearch).toBeVisible();
    await expect(a.eraseAllZone).toBeVisible();

    const shot = await page.screenshot();
    await testInfo.attach('memory-sheet', { body: shot, contentType: 'image/png' });
  });
});
