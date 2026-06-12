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

  test('MetadataPanel + render API confirm biome painter ran (AC-BIOME-8)', async ({
    page,
    request,
  }) => {
    // TMP-Q2 chunk C — two-prong verification of BiomeThemePainter
    // end-to-end:
    //  1. UI smoke: MetadataPanel "distinct terrains: N" row visible
    //     and ≥5 (proxy for "biome painter ran"; V2 baseline is 3-5).
    //  2. Authoritative HTTP check: POST minimal.json to /render and
    //     assert specific biome mix kinds present (Forest from
    //     forest_temperate, Mountain from mountain_alpine). This
    //     catches "stale backend silently dropped biome_theme via
    //     serde-skip-unknown" — a real false-pass mode discovered
    //     during chunk-C verification (MED-1 from chunk-C /review-impl).
    //
    // Skip strategy mirrors AC-DECO-8 (LOW-5 from chunk-D /review-impl):
    // probe /livez first to distinguish "backend down" (skip) from
    // "backend up but MetadataPanel didn't render" (real failure).
    const backendUp = await request
      .get('http://localhost:8220/livez', { timeout: 3_000 })
      .then((r) => r.ok())
      .catch(() => false);
    test.skip(
      !backendUp,
      'tilemap-service backend not reachable at http://localhost:8220/livez. ' +
        'Run cargo run --bin tilemap-service -- serve to activate AC-BIOME-8.',
    );

    // ── Prong 1 — UI smoke (MetadataPanel row visible) ──────────────
    await page.goto('/play');
    // MetadataPanel's Row component renders `k` and `v` as TWO sibling
    // spans (flex layout). Use a parent-div locator whose textContent()
    // concatenates the children (same pattern as AC-DECO-8 above).
    const distinctRow = page
      .locator('div')
      .filter({ hasText: /^distinct terrains\s*\d+$/ })
      .first();
    await expect(distinctRow).toBeVisible({ timeout: 15_000 });

    const text = (await distinctRow.textContent()) ?? '';
    const match = text.match(/distinct terrains\s*(\d+)/);
    expect(match, `expected distinct terrains text to match pattern, got: ${text}`).toBeTruthy();
    const distinctCount = parseInt(match![1], 10);
    // Empirical calibration (chunk-C VERIFY): 100-seed sweep via
    // `scripts/check_biome_variety.js sweep 1 100` produced min=6,
    // max=9, mean=7.29 distinct kinds. V2 baseline (no biome) sits
    // at 3-5. Threshold ≥6 separates "biome ran" from "stale backend
    // dropped opt-in" with zero flake risk across the sweep.
    expect(
      distinctCount,
      `AC-BIOME-8 UI smoke: distinct terrains count must be ≥ 6 (got ${distinctCount})`,
    ).toBeGreaterThanOrEqual(6);

    // ── Prong 2 — HTTP histogram assertion (MED-1 fix) ──────────────
    // Without this prong, AC-BIOME-8 was passing against a stale docker
    // backend that silently dropped biome_theme (serde-skip-unknown) —
    // the UI saw V2 baseline 3-5 kinds + Sea Water + Road = 5+ kinds
    // and the proxy threshold held. Calling /render with the same
    // template and inspecting histogram makes the test biome-specific.
    const templateRes = await request.get('/templates/minimal.json');
    expect(templateRes.ok(), 'minimal.json must be reachable').toBe(true);
    const template = await templateRes.json();
    const renderRes = await request.post(
      'http://localhost:8220/internal/v1/tilemaps/render',
      {
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer dev_internal_token',
        },
        data: {
          channel_id: 'ch_ac_biome_8',
          tier: 'town',
          grid_size: { width: 48, height: 48 },
          seed: 1,
          template,
        },
        timeout: 15_000,
      },
    );
    expect(renderRes.ok(), `render must succeed: ${renderRes.status()}`).toBe(true);
    const view = await renderRes.json();
    const layer: number[] = view.terrain_layer;
    // TerrainKind discriminants (mirrors backend types/tile.rs and
    // frontend types/tilemap.ts TerrainKind enum).
    const Forest = 2;
    const Mountain = 3;
    const hist: Record<number, number> = {};
    for (const v of layer) hist[v] = (hist[v] ?? 0) + 1;
    expect(
      hist[Forest] ?? 0,
      `AC-BIOME-8 HTTP: capital biome_theme=forest_temperate must paint ≥100 Forest ` +
        `tiles (70% of zone tiles). Got ${hist[Forest] ?? 0}. ` +
        `If 0, backend silently dropped biome_theme (chunk B not deployed). hist=${JSON.stringify(hist)}`,
    ).toBeGreaterThanOrEqual(100);
    expect(
      hist[Mountain] ?? 0,
      `AC-BIOME-8 HTTP: frontier biome_theme=mountain_alpine must paint ≥100 Mountain ` +
        `tiles (70% of zone tiles). Got ${hist[Mountain] ?? 0}. ` +
        `If 0, backend silently dropped biome_theme. hist=${JSON.stringify(hist)}`,
    ).toBeGreaterThanOrEqual(100);
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
