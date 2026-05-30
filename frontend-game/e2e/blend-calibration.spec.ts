import { test, expect } from '@playwright/test';

// TMP-Q3 chunk A LOW-2 fix — empirical visual calibration for the
// Stage-1 Blur defaults. Captures two screenshots of the foundation
// tilemap (blend ON vs OFF) and asserts the rendered bytes DIFFER.
// This proves the conservative STAGE1_BLUR_DEFAULTS actually produce
// an observable pixel-level change rather than being inert.
//
// This is NOT the full visual regression harness (deferred to chunk C
// per spec AC-BLEND-4). It's a one-shot calibration anchor proving
// the activation path produces a measurable effect on real GPU output.
//
// Skip strategy mirrors AC-DECO-8 / AC-BIOME-8: probe /livez first.

test('Stage-1 Blur visibly changes foundation render (AC-BLEND-2, chunk A LOW-2 calibration)', async ({
  page,
  request,
}) => {
  const backendUp = await request
    .get('http://localhost:8220/livez', { timeout: 3_000 })
    .then((r) => r.ok())
    .catch(() => false);
  test.skip(
    !backendUp,
    'tilemap-service backend not reachable at http://localhost:8220/livez. ' +
      'Run cargo run --bin tilemap-service -- serve to activate this calibration test.',
  );

  await page.goto('/play');
  // Wait for Phaser canvas to mount AND HUD to render (signals
  // foundation tilemap has been built).
  await expect(page.locator('canvas').first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/HP \d+ \/ \d+/)).toBeVisible();

  // Give the GPU a beat to flush the initial render with blend ON.
  await page.waitForTimeout(500);

  // Capture: blend ON (default).
  const blendOnPng = await page.locator('canvas').first().screenshot();
  expect(blendOnPng.byteLength).toBeGreaterThan(1000);

  // Toggle blend OFF via the UI checkbox. Wait for LayerToggles to
  // mount + locate the `<label>` wrapper (the input is nested inside).
  // Clicking the label is the canonical way to toggle a React-controlled
  // checkbox — `input.click()` doesn't always dispatch the React
  // synthetic onChange event reliably.
  const polishSection = page.getByText(/^Polish$/);
  await expect(polishSection).toBeVisible({ timeout: 15_000 });
  const blendLabel = page.locator('label').filter({ hasText: /^Smooth blend$/ });
  const blendCheckbox = blendLabel.locator('input[type="checkbox"]');
  await expect(blendCheckbox).toBeChecked();
  // Dispatch a native click event directly on the input element via
  // the underlying DOM. Native `el.click()` triggers React's onChange
  // handler reliably; Playwright's `.click()` interception path
  // doesn't always cooperate with React-controlled checkboxes under
  // Phaser's pointer-event overlay.
  await blendCheckbox.evaluate((el) => (el as HTMLInputElement).click());
  await expect(blendCheckbox).not.toBeChecked();

  // Let the filter rebuild flush.
  await page.waitForTimeout(500);

  // Capture: blend OFF.
  const blendOffPng = await page.locator('canvas').first().screenshot();
  expect(blendOffPng.byteLength).toBeGreaterThan(1000);

  // Quick byte-level equality check — if the two screenshots are
  // byte-identical, the Stage-1 Blur produced NO observable change
  // (STAGE1_BLUR_DEFAULTS too subtle to register at 1px scale).
  // Fast path: compare buffer lengths first; if equal, compare bytes.
  let identical = blendOnPng.byteLength === blendOffPng.byteLength;
  if (identical) {
    identical = blendOnPng.equals(blendOffPng);
  }
  expect(
    identical,
    `AC-BLEND-2 calibration: blend ON and blend OFF produced byte-identical canvas ` +
      `screenshots (${blendOnPng.byteLength} bytes each). STAGE1_BLUR_DEFAULTS are ` +
      `too subtle to register — bump quality/strength/radius in foundation-blend.ts.`,
  ).toBe(false);

  // Toggle back on for cleanup.
  await blendCheckbox.evaluate((el) => (el as HTMLInputElement).click());
  await expect(blendCheckbox).toBeChecked();
});
