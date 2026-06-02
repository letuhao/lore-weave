import { test, expect } from '@playwright/test';

// TMP-Q4 chunk C — Playwright visual regression baseline for the
// per-pile badges (chunk B) + zone-tier treasure-band overlay (chunk C).
// Goldens are captured against the dedicated treasure-demo template
// (capital tier=high band, frontier tier=mid band, borderlands tier=low
// band) so the band coloring is observably visible.
//
// Two scenarios:
//   1. badges-only (overlay OFF, default) — verifies the per-pile
//      badge layer renders on a treasure-bearing template.
//   2. badges + overlay (showTreasureBands ON) — verifies the
//      zone-tier translucent tint paints over each zone's assigned
//      tiles per chunk-C design.
//
// Cross-platform discipline mirrors `blend-visual-regression.spec.ts`
// (LOW-4 from chunk-C TMP-Q3 /review-impl): each platform pins its own
// PNG; CI on Linux + dev on Windows produces different goldens; commit
// all platform-suffixed PNGs.
//
// Skip strategy: probe /livez first to distinguish "backend down"
// (skip) from "backend up but FE didn't render" (real failure).

const SCREENSHOT_OPTS = {
  // Same calibration as TMP-Q3 chunk-C blend goldens: 2% pixel-diff
  // tolerance absorbs headless software-WebGL float-precision drift;
  // 30s timeout gives Playwright stability checker time to find two
  // consecutive identical frames at ~9 fps headless render rate.
  maxDiffPixelRatio: 0.02,
  timeout: 30_000,
  animations: 'disabled' as const,
};

test.describe('Treasure bands visual regression (TMP-Q4 chunk C)', () => {
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

  async function bootSceneWithTreasureDemo(
    page: import('@playwright/test').Page,
  ): Promise<void> {
    // Navigate to /play with the treasure-demo template param. The
    // FE selects /templates/treasure-demo.json which has populated
    // treasure_tiers across capital/frontier/borderlands; sea + rival
    // zones stay empty (no piles expected there).
    await page.goto('/play?template=treasure-demo');
    await expect(page.locator('canvas').first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/HP \d+ \/ \d+/)).toBeVisible();
    // Wait for foundation render + badge stamping + Stage-2 blend
    // activation to settle. ~15 frames at headless ~9 fps.
    await page.waitForTimeout(1500);
  }

  test('badges-only — Stage-2 default with treasure piles (overlay OFF)', async ({
    page,
  }) => {
    await bootSceneWithTreasureDemo(page);
    // LOW-3 from chunk-C /review-impl — gate the golden capture on a
    // content assertion so a silently-wrong template load (e.g., URL
    // param parsing regressed) can't bake a bad PNG into the baseline.
    // The breakdown summary says "(3 zones · Σ N gold)" iff the FE
    // resolved treasure-demo's three treasure-bearing zones; if it
    // resolved minimal.json instead, this assertion fails BEFORE
    // toHaveScreenshot writes the golden.
    await expect(
      page.locator('summary').filter({ hasText: /^treasure breakdown \(3 zones/ }),
    ).toBeVisible({ timeout: 15_000 });
    const canvas = page.locator('canvas').first();
    await expect(canvas).toHaveScreenshot(
      'treasure-badges-only.png',
      SCREENSHOT_OPTS,
    );
  });

  test('badges + bands — overlay ON tints each zone by max-tier color', async ({
    page,
  }) => {
    await bootSceneWithTreasureDemo(page);
    // LOW-3 from chunk-C /review-impl — gate-before-snapshot (same
    // rationale as the badges-only test above).
    await expect(
      page.locator('summary').filter({ hasText: /^treasure breakdown \(3 zones/ }),
    ).toBeVisible({ timeout: 15_000 });
    // Toggle "Treasure bands" ON via UI label click (same native-click
    // pattern as the blend-visual-regression tests).
    const bandsCheckbox = page
      .locator('label')
      .filter({ hasText: /^Treasure bands$/ })
      .locator('input[type="checkbox"]');
    await expect(bandsCheckbox).not.toBeChecked();
    await bandsCheckbox.evaluate((el) => (el as HTMLInputElement).click());
    await expect(bandsCheckbox).toBeChecked();
    // Allow the overlay's bandsRt.visible flip to flush.
    await page.waitForTimeout(500);
    const canvas = page.locator('canvas').first();
    await expect(canvas).toHaveScreenshot(
      'treasure-badges-with-bands.png',
      SCREENSHOT_OPTS,
    );
  });

  test('MetadataPanel treasure breakdown lists capital + frontier + borderlands', async ({
    page,
  }) => {
    // Empty-zones-omitted invariant (LOW-1): inland_sea and rival have
    // no treasure_tiers, so they MUST NOT appear in the breakdown
    // (which shows `<n> zones` in its summary). Capital + frontier +
    // borderlands DO have piles; the summary must include them.
    await bootSceneWithTreasureDemo(page);
    // The breakdown summary uses parens: "treasure breakdown (3 zones ..."
    const breakdownSummary = page
      .locator('summary')
      .filter({ hasText: /^treasure breakdown/ });
    await expect(breakdownSummary).toBeVisible({ timeout: 15_000 });
    const text = (await breakdownSummary.textContent()) ?? '';
    const match = text.match(/(\d+) zones/);
    expect(
      match,
      `expected breakdown summary to match "(N zones ..." pattern, got: ${text}`,
    ).toBeTruthy();
    const zoneCount = parseInt(match![1]!, 10);
    expect(
      zoneCount,
      `expected 3 treasure-bearing zones (capital + frontier + borderlands); got ${zoneCount}`,
    ).toBe(3);
  });
});
