import { test, expect } from '@playwright/test';

// TMP-Q3 chunk C — FPS perf probe for the blend pipeline.
// Measures requestAnimationFrame callback rate over a fixed window
// to catch significant regressions when Stage-1 / Stage-2 lands a
// future change.
//
// Headless-chromium calibration (chunk-C VERIFY):
//   - Blend OFF (V0 hard edges) → ~60fps headless. Threshold: 30fps.
//   - Blend ON  (Stage-2 shader) → ~9fps headless (no hardware accel;
//     5-tap fragment shader on 1080p is software-rasterised). Threshold:
//     5fps — catches catastrophic regression (shader hangs / 0fps) but
//     accepts the headless software-render reality. Real browsers with
//     hardware accel render Stage-2 much faster (visual proof: the
//     blend-calibration test shows STAGE-2 ACTIVE in real chromium).
//
// The probe captures relative regression detection, NOT absolute
// perf truth. Reading FPS from a JS clock approximates wall-clock
// paints; the GPU may actually be faster (or vsync-throttled).
//
// Backend must be reachable for /play to render a real tilemap;
// skip otherwise (mirrors AC-DECO-8 / AC-BIOME-8 / AC-BLEND-2).

interface FpsProbeResult {
  frames: number;
  elapsedMs: number;
  fps: number;
}

async function measureFps(
  page: import('@playwright/test').Page,
  durationMs: number,
): Promise<FpsProbeResult> {
  return await page.evaluate<FpsProbeResult, number>(async (duration) => {
    const start = performance.now();
    const deadline = start + duration;
    let frames = 0;
    await new Promise<void>((resolve) => {
      const tick = () => {
        const now = performance.now();
        if (now >= deadline) {
          resolve();
          return;
        }
        frames++;
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    const elapsedMs = performance.now() - start;
    return { frames, elapsedMs, fps: (frames * 1000) / elapsedMs };
  }, durationMs);
}

/** Different thresholds for blend ON vs OFF because headless chromium's
 *  software-rasterised WebGL pipeline drops to ~9fps under Stage-2's
 *  per-pixel shader work but stays at ~60fps with no filter. Both
 *  thresholds are below normal headless rates so a fail is a real
 *  regression.
 *
 *  **COSMETIC-2 from chunk-C /review-impl — threshold sensitivity:**
 *  `MIN_FPS_BLEND_ON = 5` only catches catastrophic regressions
 *  (shader compile loops, infinite branches, near-zero throughput).
 *  A 3× slowdown (e.g., shader regression from 5 taps → 25 taps per
 *  pixel) would still pass headless. Real-browser FPS would catch it
 *  but isn't covered here — that calibration belongs in a manual
 *  pre-merge smoke (cross-referenced as a chunk-C deferred item). */
const MIN_FPS_BLEND_OFF = 30;
const MIN_FPS_BLEND_ON = 5;
const PROBE_DURATION_MS = 3000;
const WARMUP_MS = 500;

test('FPS holds above 30 with blend ON (Stage-2 / Stage-1) (AC-BLEND-5)', async ({
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
      'Run cargo run --bin tilemap-service -- serve to activate this probe.',
  );

  await page.goto('/play');
  await expect(page.locator('canvas').first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/HP \d+ \/ \d+/)).toBeVisible();

  // Warm-up: let the initial render + first-blend filter activation
  // flush before measuring. Initial frames are I/O bound (texture
  // upload, shader compile, etc.) and would skew the average down.
  await page.waitForTimeout(WARMUP_MS);

  const onResult = await measureFps(page, PROBE_DURATION_MS);
  test.info().annotations.push({
    type: 'fps-blend-on',
    description: `${onResult.fps.toFixed(1)} fps (${onResult.frames} frames / ${onResult.elapsedMs.toFixed(0)}ms)`,
  });
  expect(
    onResult.fps,
    `Blend ON FPS dropped below ${MIN_FPS_BLEND_ON}: got ${onResult.fps.toFixed(1)} ` +
      `(${onResult.frames} frames in ${onResult.elapsedMs.toFixed(0)}ms). ` +
      `Headless chromium typically renders Stage-2 at ~9fps; below ${MIN_FPS_BLEND_ON} ` +
      `suggests catastrophic shader regression (compile fail looping, infinite ` +
      `loop, etc.). Real browsers with hardware accel are much faster.`,
  ).toBeGreaterThanOrEqual(MIN_FPS_BLEND_ON);
});

test('FPS holds above 30 with blend OFF (V0 baseline) (AC-BLEND-5)', async ({
  page,
  request,
}) => {
  const backendUp = await request
    .get('http://localhost:8220/livez', { timeout: 3_000 })
    .then((r) => r.ok())
    .catch(() => false);
  test.skip(!backendUp, 'backend down — skip FPS baseline');

  await page.goto('/play');
  await expect(page.locator('canvas').first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/HP \d+ \/ \d+/)).toBeVisible();

  // Toggle blend OFF via the UI checkbox (native click through evaluate
  // — same pattern as blend-calibration.spec.ts).
  const blendCheckbox = page
    .locator('label')
    .filter({ hasText: /^Smooth blend$/ })
    .locator('input[type="checkbox"]');
  await expect(blendCheckbox).toBeChecked();
  await blendCheckbox.evaluate((el) => (el as HTMLInputElement).click());
  await expect(blendCheckbox).not.toBeChecked();

  await page.waitForTimeout(WARMUP_MS);

  const offResult = await measureFps(page, PROBE_DURATION_MS);
  test.info().annotations.push({
    type: 'fps-blend-off',
    description: `${offResult.fps.toFixed(1)} fps (${offResult.frames} frames / ${offResult.elapsedMs.toFixed(0)}ms)`,
  });
  expect(
    offResult.fps,
    `Blend OFF (V0) FPS dropped below ${MIN_FPS_BLEND_OFF}: got ${offResult.fps.toFixed(1)}. ` +
      `V0 has no filter cost — if this fails, the regression is elsewhere ` +
      `(Phaser, scene setup, render loop).`,
  ).toBeGreaterThanOrEqual(MIN_FPS_BLEND_OFF);
});
