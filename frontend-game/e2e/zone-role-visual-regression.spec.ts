import { test, expect } from '@playwright/test';

// TMP-Q5 chunk C — Playwright visual regression baseline for the
// zone-role overlay (chunk B's `drawZoneRoles` paint). Two goldens:
//   1. zone-roles-off.png — V0 baseline (showZoneRoles = false default)
//   2. zone-roles-on.png  — overlay tinted per zone role
//
// Uses `/play` + the default `minimal.json` template. The 5 zones
// (capital wilderness + crossroad hub + frontier wilderness + inland_sea
// sea + rival forbidden) provide a 4-role spread, exercising all 4
// `ZONE_ROLE_DEFAULTS` colors at once.
//
// Cross-platform discipline: per-platform PNG (Windows-x86_64 on dev,
// CI rebases on first Linux run) per TMP-Q3 chunk-C LOW-4 precedent.
//
// Content gate per `feedback_visual_goldens_must_gate_on_content`:
// each snapshot is preceded by an assertion that the MetadataPanel
// role breakdown summary lists the expected 4 roles. A silently-wrong
// fixture load (e.g., minimal.json regressed) fails the assertion
// BEFORE Playwright bakes a bad PNG.

const SCREENSHOT_OPTS = {
  // Same calibration as TMP-Q3+Q4 chunk-C goldens: 2% pixel diff
  // tolerance absorbs headless software-WebGL float-precision drift;
  // 30s timeout gives the stability checker time to find two
  // consecutive identical frames at ~9fps headless render rate.
  maxDiffPixelRatio: 0.02,
  timeout: 30_000,
  animations: 'disabled' as const,
};

test.describe('Zone-role visual regression (TMP-Q5 chunk C)', () => {
  test.beforeEach(async ({ request }) => {
    const backendUp = await request
      .get('http://localhost:8220/livez', { timeout: 3_000 })
      .then((r) => r.ok())
      .catch(() => false);
    test.skip(
      !backendUp,
      'tilemap-service backend not reachable. Run cargo run --bin tilemap-service -- serve.',
    );
  });

  async function bootScene(page: import('@playwright/test').Page) {
    await page.goto('/play');
    await expect(page.locator('canvas').first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/HP \d+ \/ \d+/)).toBeVisible();
    // Settle render: foundation + objects + zone-role RT all flush.
    // ~15 frames at headless ~9fps.
    await page.waitForTimeout(1500);
  }

  test('zone-roles OFF — default render (overlay invisible)', async ({
    page,
  }) => {
    await bootScene(page);
    // Content gate per `visual_goldens_must_gate_on_content` memory:
    // the role breakdown summary lists "(N roles · M zones)". minimal.json
    // has 5 zones split across 4 roles (2 wilderness + 1 hub + 1 forbidden
    // + 1 sea). If the fixture regressed or the breakdown helper broke,
    // this gate fails BEFORE Playwright bakes a bad PNG.
    await expect(
      page.locator('summary').filter({ hasText: /^role breakdown \(4 roles · 5 zones\)/ }),
    ).toBeVisible({ timeout: 15_000 });
    const canvas = page.locator('canvas').first();
    await expect(canvas).toHaveScreenshot('zone-roles-off.png', SCREENSHOT_OPTS);
  });

  test('zone-roles ON — overlay tints each zone by role', async ({
    page,
  }) => {
    await bootScene(page);
    await expect(
      page.locator('summary').filter({ hasText: /^role breakdown \(4 roles · 5 zones\)/ }),
    ).toBeVisible({ timeout: 15_000 });
    // Toggle "Zone roles" ON via UI label click (native click pattern
    // shared with chunk-A TMP-Q3 blend tests).
    const checkbox = page
      .locator('label')
      .filter({ hasText: /^Zone roles$/ })
      .locator('input[type="checkbox"]');
    await expect(checkbox).not.toBeChecked();
    await checkbox.evaluate((el) => (el as HTMLInputElement).click());
    await expect(checkbox).toBeChecked();
    // Allow the RT visibility flip to flush.
    await page.waitForTimeout(500);
    const canvas = page.locator('canvas').first();
    await expect(canvas).toHaveScreenshot('zone-roles-on.png', SCREENSHOT_OPTS);
  });
});
