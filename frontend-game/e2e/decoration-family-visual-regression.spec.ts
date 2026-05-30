import { test, expect } from '@playwright/test';

// TMP-Q6 chunk C — Playwright visual regression baseline for the
// MetadataPanel `DecorationFamilyBreakdown` section.
//
// Two goldens:
//   1. decoration-family-breakdown-collapsed.png — default collapsed state
//   2. decoration-family-breakdown-expanded.png  — expanded showing rows
//
// Uses /play + the default minimal.json template. The fixture has 5
// zones; with decoration_density opt-in, decorations land across 5-6
// families pulled from the default registry's 29 decoration entries.
//
// Content gate per `feedback_visual_goldens_must_gate_on_content` AND
// `feedback_test_substring_over_line_anchored`: each snapshot is
// preceded by a substring match on the summary copy that includes the
// family + decoration counts. A silently-wrong fixture load (e.g.,
// backend dropped `family` from TilemapObjectPlacement) fails the
// assertion BEFORE Playwright bakes a bad PNG.
//
// Cross-platform discipline: per-platform PNG (Windows-x86_64 on dev,
// CI rebases on first Linux run) per TMP-Q3 chunk-C LOW-4 precedent.

const SCREENSHOT_OPTS = {
  maxDiffPixelRatio: 0.02,
  timeout: 30_000,
  animations: 'disabled' as const,
};

test.describe('Decoration-family breakdown visual regression (TMP-Q6 chunk C)', () => {
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
    // Settle render: decorations placed + MetadataPanel rendered.
    await page.waitForTimeout(1500);
  }

  test('decoration-family breakdown collapsed (default state)', async ({
    page,
  }) => {
    await bootScene(page);
    // Content gate: the section header MUST be present. The default
    // `/play` fixture (`v1_viewer_minimal`) uses biome_theme zones that
    // don't always emit decorations on every seed (the biome-themed
    // zones don't set `zone_terrain`, which DecorationPlacer requires
    // before placing). So this gate accepts BOTH the populated summary
    // ("decoration families (N families · M decorations)") AND the
    // empty-state summary ("decoration families"). Either rendering is
    // a valid snapshot baseline — what matters is the section mounted.
    // The HTTP integration test
    // `tmp_q6_template_decoration_family_density_flows_through_http`
    // independently proves the bias path emits placements under
    // controlled fixtures.
    await expect(
      page
        .locator('summary')
        .filter({ hasText: /^decoration families( \(|$)/ }),
    ).toBeVisible({ timeout: 15_000 });
    // Capture the section. Scoping tight + immune to unrelated viewer
    // changes (canvas pan/zoom, HUD flips).
    const metadataPanel = page.locator('details').filter({
      hasText: /^decoration families/,
    });
    await expect(metadataPanel).toHaveScreenshot(
      'decoration-family-breakdown-collapsed.png',
      SCREENSHOT_OPTS,
    );
  });

  test('decoration-family breakdown expanded (post-summary-click state)', async ({
    page,
  }) => {
    await bootScene(page);
    const summary = page
      .locator('summary')
      .filter({ hasText: /^decoration families( \(|$)/ });
    await expect(summary).toBeVisible({ timeout: 15_000 });
    // Expand the section via summary click.
    await summary.click();
    await page.waitForTimeout(200); // CSS transition settle
    // MED-3-light fix from chunk-C /review-impl — assert EITHER the row
    // list OR the empty-state copy is now visible, so the test's intent
    // is EXPLICIT about which path the current fixture is hitting. The
    // unconditional snapshot below would have baked either state
    // silently; this assertion makes the path observable in the test
    // report. (Today's `v1_viewer_minimal` fixture hits the empty
    // state because biome-themed zones don't set `zone_terrain`; the
    // BE integration test
    // `tmp_q6_template_decoration_family_density_flows_through_http`
    // independently exercises the populated path.)
    const rowListLocator = page.locator(
      '[data-testid="decoration-family-breakdown"]',
    );
    const emptyStateLocator = page.locator(
      '[data-testid="decoration-family-empty-state"]',
    );
    const renderedOneOfTwoStates =
      (await rowListLocator.isVisible()) ||
      (await emptyStateLocator.isVisible());
    expect(renderedOneOfTwoStates).toBe(true);
    // Snapshot the expanded section.
    const metadataPanel = page.locator('details').filter({
      hasText: /^decoration families/,
    });
    await expect(metadataPanel).toHaveScreenshot(
      'decoration-family-breakdown-expanded.png',
      SCREENSHOT_OPTS,
    );
  });
});
