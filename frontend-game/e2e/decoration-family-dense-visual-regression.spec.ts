import { test, expect } from '@playwright/test';

// DEFERRED #048 from TMP-Q6 chunk-C /review-impl MED-3 follow-up —
// visual regression baseline for the MetadataPanel `DecorationFamilyBreakdown`
// section AGAINST A FIXTURE THAT ACTUALLY PRODUCES DECORATIONS.
//
// The chunk-C goldens use `minimal.json` (biome-themed zones → 0
// decorations → empty-state PNG). Those PNGs verify the section header
// + the empty-state path. THESE goldens use `decoration_dense.json`
// (no biome_theme + explicit terrain_types per zone) so DecorationPlacer
// actually places dozens of decorations across multiple families. The
// goldens here verify the populated row-rendering path: row container,
// per-family rows, percent display.
//
// `?fixture=decoration_dense` query param (play.tsx allowlist) injects
// the alternate fixture without touching the shared minimal.json.

const SCREENSHOT_OPTS = {
  maxDiffPixelRatio: 0.02,
  timeout: 30_000,
  animations: 'disabled' as const,
};

test.describe('Decoration-family breakdown DENSE visual regression (chunk D #048)', () => {
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

  async function bootDenseScene(page: import('@playwright/test').Page) {
    // seed=42 pins a productive seed for the dense fixture — seed=1
    // happens to land the placer pipeline in a state where 0
    // decorations end up placed despite the explicit terrain_types,
    // probably because the (24-tile) zone OPEN regions are too small
    // after treasure + road placement on this fixture's geometry.
    // The chunk-D #048 follow-up may revisit the fixture shape; for
    // now seed=42 + seed-override URL param give a stable golden
    // baseline.
    await page.goto('/play?fixture=decoration_dense&seed=42');
    await expect(page.locator('canvas').first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/HP \d+ \/ \d+/)).toBeVisible();
    // Confirm the dense fixture loaded: template id appears in the
    // MetadataPanel "template" row. If a typo / allowlist / fetch
    // failure dropped the fixture, the page falls back to minimal.json
    // (template id `v1_viewer_minimal`) and this assertion fires.
    await expect(
      page.getByText('v1_viewer_decoration_dense'),
    ).toBeVisible({ timeout: 15_000 });
    // Settle render: decorations placed + MetadataPanel rendered.
    await page.waitForTimeout(1500);
  }

  test('dense fixture renders the populated breakdown rows', async ({
    page,
  }) => {
    await bootDenseScene(page);
    // Content gate: section header shows the populated form
    // "(N families · M decorations)" — strict pattern this time
    // because the dense fixture is engineered to land decorations.
    await expect(
      page
        .locator('summary')
        .filter({ hasText: /^decoration families \(\d+ families · \d+ decorations\)$/ }),
    ).toBeVisible({ timeout: 15_000 });
    // Expand the section.
    await page
      .locator('summary')
      .filter({ hasText: /^decoration families/ })
      .click();
    await page.waitForTimeout(200);
    // Verify the row container materializes (NOT the empty-state path).
    await expect(
      page.locator('[data-testid="decoration-family-breakdown"]'),
    ).toBeVisible({ timeout: 5_000 });
    // At least 1 row rendered.
    const rows = page.locator('[data-testid="decoration-family-row"]');
    await expect(rows.first()).toBeVisible({ timeout: 5_000 });
    await expect(await rows.count()).toBeGreaterThanOrEqual(1);
    // Snapshot the populated section.
    const metadataPanel = page.locator('details').filter({
      hasText: /^decoration families/,
    });
    await expect(metadataPanel).toHaveScreenshot(
      'decoration-family-breakdown-dense-expanded.png',
      SCREENSHOT_OPTS,
    );
  });

  test('dense fixture: breakdown row sum equals header decoration count (cross-surface predicate parity)', async ({
    page,
  }) => {
    // Chunk-D #048 MED-1 extension to e2e: the header summary copy
    // "decoration families (N families · M decorations)" claims M
    // decorations across N families. The breakdown rows are the
    // per-family decomposition; their counts must sum to M. Both
    // values flow from the SAME `isDecorationPlacement` predicate
    // (chunk-C MED-1 single-source-of-truth) — if a future refactor
    // makes them disagree, the header and the rows diverge silently
    // without this test.
    await bootDenseScene(page);
    // Read the header text to extract M.
    const summaryText = await page
      .locator('summary')
      .filter({ hasText: /^decoration families \(/ })
      .first()
      .textContent();
    expect(summaryText).toBeTruthy();
    const headerMatch = summaryText?.match(
      /decoration families \((\d+) families · (\d+) decorations\)/,
    );
    expect(headerMatch).toBeTruthy();
    const headerFamiliesCount = Number(headerMatch?.[1] ?? '0');
    const headerDecorationsCount = Number(headerMatch?.[2] ?? '0');
    expect(headerDecorationsCount).toBeGreaterThan(0);

    // Expand the breakdown.
    await page
      .locator('summary')
      .filter({ hasText: /^decoration families/ })
      .click();
    await page.waitForTimeout(200);
    const rowTexts = await page
      .locator('[data-testid="decoration-family-row"]')
      .allTextContents();
    // Each row text: "<family><count> (<percent>%)" — extract the
    // integer count that appears BEFORE the parens.
    let rowSum = 0;
    for (const t of rowTexts) {
      const m = t.match(/(\d+)\s*\(/);
      if (m) rowSum += Number(m[1]);
    }
    expect(rowTexts).toHaveLength(headerFamiliesCount);
    expect(rowSum).toBe(headerDecorationsCount);
  });
});
