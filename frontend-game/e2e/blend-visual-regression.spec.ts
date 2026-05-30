import { test, expect } from '@playwright/test';

// TMP-Q3 chunk C — Playwright visual regression baseline for the
// blend pipeline. Captures canvas screenshots in two states (V0
// hard edges, Stage-2 ACTIVE with default hints) and compares against
// stored goldens via `toHaveScreenshot()`.
//
// First run creates the goldens under
// `frontend-game/e2e/blend-visual-regression.spec.ts-snapshots/`.
// Subsequent runs compare with a 2% pixel-diff tolerance to absorb
// headless software-WebGL float-precision drift.
//
// LOW-4 fix from chunk-C /review-impl — cross-platform golden capture:
//   Playwright stores per-platform goldens with names like
//   `blend-on-stage2-default-chromium-win32.png` /
//   `*-chromium-linux.png` / `*-chromium-darwin.png`. A new platform
//   has NO golden ⇒ Playwright fails (does not auto-create unless
//   `--update-snapshots`). To regenerate goldens on a new platform:
//
//     pnpm exec playwright test blend-visual-regression \
//       --project=chromium --update-snapshots --workers=1
//
//   Commit ALL platform-suffixed PNGs (don't just commit one platform
//   and expect CI to backfill). Cross-platform diffs > 2% are
//   expected (software-vs-hardware WebGL, driver vs driver) — pin
//   per-platform rather than rebaselining to one.
//
// Skip strategy mirrors blend-calibration.spec.ts: probe /livez first.

const SCREENSHOT_OPTS = {
  // Allow up to 2% pixel diff to absorb headless WebGL driver noise.
  // Calibrated during chunk-C VERIFY: Stage-2 in headless chromium
  // renders at ~9fps with software rasterisation, so back-to-back
  // screenshots have ~0.5-1% float-precision drift even on stable
  // input. Real-browser hardware accel is more deterministic.
  maxDiffPixelRatio: 0.02,
  // Phaser's WebGL render loop runs continuously; allow extra time
  // for Playwright's stability checker to find two consecutive
  // identical frames. Default is 5s which is shorter than the
  // ~110ms-per-frame headless render rate × the retry budget.
  timeout: 30_000,
  // Disable CSS animations (HUD pulse, etc.) — doesn't affect WebGL
  // canvas but keeps overlay state stable.
  animations: 'disabled' as const,
};

test.describe('Blend visual regression (TMP-Q3 chunk C)', () => {
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
    // Wait for the foundation render + blend filter activation to flush.
    // Stage-2 runs at ~9fps in headless chromium (software WebGL), so
    // give it ~15 frames of stability before snapshotting. Bumped from
    // 700ms in chunk-C VERIFY when initial run was visually flaky.
    await page.waitForTimeout(1500);
  }

  test('blend ON — Stage-2 default render captures pixel-identical to golden', async ({
    page,
  }) => {
    await bootScene(page);
    const canvas = page.locator('canvas').first();
    await expect(canvas).toHaveScreenshot('blend-on-stage2-default.png', SCREENSHOT_OPTS);
  });

  test('blend OFF — V0 hard edges captures pixel-identical to golden', async ({
    page,
  }) => {
    await bootScene(page);
    // Toggle blend OFF via UI (label click via DOM native click).
    const blendCheckbox = page
      .locator('label')
      .filter({ hasText: /^Smooth blend$/ })
      .locator('input[type="checkbox"]');
    await blendCheckbox.evaluate((el) => (el as HTMLInputElement).click());
    await expect(blendCheckbox).not.toBeChecked();
    // Settle.
    await page.waitForTimeout(500);
    const canvas = page.locator('canvas').first();
    await expect(canvas).toHaveScreenshot('blend-off-v0.png', SCREENSHOT_OPTS);
  });
});
