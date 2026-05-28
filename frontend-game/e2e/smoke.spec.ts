import { test, expect } from '@playwright/test';

// Cross-browser V0 smoke per spec AC-FG-16 (Chrome + Firefox + Safari).
// Run via Playwright config which spins up dev server automatically.

test.describe('V0 smoke — static routes (no backend)', () => {
  test('/login renders', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));

    await page.goto('/login');
    await expect(page).toHaveTitle(/LoreWeave/);
    await expect(page.getByRole('heading', { name: /Login/ })).toBeVisible();

    expect(errors, 'no uncaught page errors').toEqual([]);
  });

  test('/world-select renders', async ({ page }) => {
    await page.goto('/world-select');
    await expect(page.getByRole('heading', { name: /Select World/ })).toBeVisible();
  });

  test('login → world-select → play navigation', async ({ page }) => {
    await page.goto('/login');
    await page.getByRole('button', { name: /Continue as guest/ }).click();
    await expect(page).toHaveURL(/\/world-select/);

    await page.getByRole('button', { name: /Enter world/ }).click();
    await expect(page).toHaveURL(/\/play/);
  });
});

test.describe('/play smoke — V0 HUD + V1.2 viewer surface', () => {
  // Per-test capture: pageerror + console.error/warning, surfaced on
  // failure so CI logs reveal root cause without artifact download.
  test.beforeEach(async ({ page }, testInfo) => {
    const events: string[] = [];
    page.on('pageerror', (err) => events.push(`[pageerror] ${err.message}`));
    page.on('console', (msg) => {
      if (msg.type() === 'error' || msg.type() === 'warning') {
        events.push(`[console.${msg.type()}] ${msg.text()}`);
      }
    });
    testInfo.attach.bind(testInfo);
    // Stash the capture array onto testInfo for the afterEach hook.
    (testInfo as unknown as { _capturedEvents: string[] })._capturedEvents = events;
  });

  test.afterEach(async ({}, testInfo) => {
    const events = (testInfo as unknown as { _capturedEvents?: string[] })._capturedEvents ?? [];
    if (testInfo.status !== testInfo.expectedStatus && events.length) {
      await testInfo.attach('captured-events', {
        body: events.join('\n'),
        contentType: 'text/plain',
      });
    }
  });

  test('HUD + viewer surface visible on /play (AC-FG-6, V1.2 viewer)', async ({ page }) => {
    await page.goto('/play');

    // HUD bars — pure React DOM overlay, must render even when WebGL
    // is unavailable (firefox CI). PhaserGame catches WebGL init errors
    // defensively so the React subtree stays mounted.
    await expect(page.getByText(/HP \d+ \/ \d+/)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/MP \d+ \/ \d+/)).toBeVisible();

    // V1.2 viewer surface — also pure React DOM.
    await expect(page.getByText(/Tilemap viewer/)).toBeVisible();
    await expect(page.getByRole('button', { name: /render zone|rendering/ })).toBeVisible();
    await expect(page.getByText(/^Layers$/)).toBeVisible();
    await expect(page.getByText(/L0 Foundation/)).toBeVisible();

    // EchoPanel — also DOM-only (status text), tolerant of "connecting".
    await expect(page.getByText(/game-server:/)).toBeVisible();
  });

  test('MetadataPanel shows decorations count ≥ 20 (AC-DECO-8)', async ({ page, request }) => {
    // TMP-Q1 chunk D — verifies the decoration density pass produces
    // visible output end-to-end via the MetadataPanel "decorations: N"
    // row. Requires tilemap-service backend on :8220 to handle
    // /internal/v1/tilemaps/render.
    //
    // Skip strategy (LOW-5 from chunk-D /review-impl): probe /livez
    // first to distinguish "backend down" (skip) from "backend up but
    // MetadataPanel didn't render" (real failure). The original
    // catch-all-on-invisible pattern masked the second case.
    const backendUp = await request
      .get('http://localhost:8220/livez', { timeout: 3_000 })
      .then((r) => r.ok())
      .catch(() => false);
    test.skip(
      !backendUp,
      'tilemap-service backend not reachable at http://localhost:8220/livez. ' +
        'Run cargo run --bin tilemap-service -- serve to activate AC-DECO-8.',
    );

    await page.goto('/play');
    // MetadataPanel's Row component renders `k` and `v` as TWO sibling
    // spans (flex layout), not a single text node. `getByText(/k v/)`
    // doesn't match across siblings; need a parent-div locator whose
    // .textContent() concatenates: "decorations 66".
    const decorationsRow = page
      .locator('div')
      .filter({ hasText: /^decorations\s*\d+$/ })
      .first();
    await expect(decorationsRow).toBeVisible({ timeout: 15_000 });

    const text = (await decorationsRow.textContent()) ?? '';
    const match = text.match(/decorations\s*(\d+)/);
    expect(match, `expected decorations text to match pattern, got: ${text}`).toBeTruthy();
    const count = parseInt(match![1], 10);
    expect(
      count,
      `AC-DECO-8 browser smoke: visible decoration count must be ≥ 20 (got ${count})`,
    ).toBeGreaterThanOrEqual(20);
  });

  test('Phaser canvas mounts (AC-FG-5)', async ({ page, browserName }) => {
    // Phaser 4 only supports WebGL (no canvas fallback). The ubuntu-CI
    // playwright firefox image cannot create a WebGL context
    // (FEATURE_FAILURE_WEBGL_EXHAUSTED_DRIVERS) so canvas is absent on
    // that combination. Chromium and webkit both create WebGL fine.
    // Coverage for firefox lives in the cross-browser HUD test above —
    // that verifies the React tree survives WebGL failure.
    test.skip(
      browserName === 'firefox' && !!process.env.CI,
      'firefox CI has no WebGL; canvas-mount asserted on chromium + webkit only',
    );

    await page.goto('/play');
    // .first() because React StrictMode double-mounts Phaser in dev,
    // briefly producing 2 canvas elements before cleanup.
    await expect(page.locator('canvas').first()).toBeVisible({ timeout: 30_000 });
  });
});
