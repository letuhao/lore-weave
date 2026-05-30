// TMP-Q3 chunk A — Stage-1 smooth-blend post-processing.
//
// Wraps the Phaser 4 Filter API in a duck-typed call site so the
// blend filter activation is unit-testable without mounting a real
// Phaser scene. The actual Phaser GameObject (TilemapGPULayer or
// TilemapLayer fallback) is passed in by `WorldScene`.
//
// Chunk B replaces the `addBlur` call with a custom `BaseFilterShader`
// that does cross-tile bilinear blending. The fallback chain
// (Stage 2 shader fail → Stage 1 Blur → V0 hard edges) is built around
// this same helper.

/** Minimum surface area of a Phaser GameObject that supports the
 *  Filter API. Narrowing via duck-type rather than `instanceof` so a
 *  future fallback render path (plain `Sprite`, `TilemapLayer`, etc.)
 *  doesn't need an import here. */
export interface BlendFilterTarget {
  enableFilters?: () => unknown;
  filters?: {
    external?: {
      clear?: () => void;
      addBlur?: (
        quality?: number,
        x?: number,
        y?: number,
        strength?: number,
        color?: number,
        steps?: number,
      ) => unknown;
    };
  };
}

/** Conservative Stage-1 defaults — single-pass low-quality Blur. Soft
 *  enough to round hard pixel edges without smearing tile centers. */
export const STAGE1_BLUR_DEFAULTS = {
  quality: 1,
  x: 0.5,
  y: 0.5,
  strength: 1,
  color: 0xffffff,
  steps: 4,
} as const;

/** Result of an applyBlendFilter call — what actually happened, so the
 *  caller (or a test) can assert behavior without poking at Phaser
 *  internals. */
export type BlendApplyResult =
  | { ok: true; action: 'enabled' | 'disabled' | 'unsupported' }
  | { ok: false; error: unknown };

/** Apply (or remove) the Stage-1 Blur filter to a foundation display.
 *
 * - When `target.enableFilters` is missing → action `unsupported`
 *   (fallback render path such as a plain `TilemapLayer` that pre-
 *   dates the filter API; V0 hard edges remain).
 * - When `enabled === false` → clears the external filter list +
 *   action `disabled` (V0 hard edges).
 * - When `enabled === true` → enables filters, clears existing, adds
 *   `Blur` with conservative defaults + action `enabled`.
 *
 * The function is idempotent: calling repeatedly with the same flag
 * does not stack filters because `clear()` runs first. */
export function applyBlendFilter(
  target: BlendFilterTarget | null | undefined,
  enabled: boolean,
): BlendApplyResult {
  if (!target) {
    return { ok: true, action: 'unsupported' };
  }
  if (typeof target.enableFilters !== 'function') {
    return { ok: true, action: 'unsupported' };
  }
  try {
    target.enableFilters();
    // LOW-3 fix from chunk-A /review-impl — after enableFilters
    // succeeds, ASSERT that the methods we actually invoke exist on
    // the target. Without this guard, a future Phaser API rename
    // (e.g. addBlur → addGaussianBlur) would silently no-op via the
    // optional chains below, the helper would still return
    // `{ ok: true, action: 'enabled' }`, and nobody would know the
    // blend stopped working. The cast-via-unknown in WorldScene
    // bypasses tsc detection of this drift.
    if (typeof target.filters?.external?.addBlur !== 'function') {
      return {
        ok: false,
        error: new Error(
          'Phaser filters.external.addBlur missing — API skew? ' +
            'Update foundation-blend.ts to match the new Phaser surface.',
        ),
      };
    }
    // Always clear first so a runtime toggle doesn't stack filters
    // across re-applies. Defensive optional-chain — older Phaser
    // builds might lack `clear`; if so, the next `addBlur` is the
    // worst-case "duplicate Blur" which the user can fix by reloading.
    target.filters?.external?.clear?.();
    if (!enabled) {
      return { ok: true, action: 'disabled' };
    }
    target.filters.external.addBlur(
      STAGE1_BLUR_DEFAULTS.quality,
      STAGE1_BLUR_DEFAULTS.x,
      STAGE1_BLUR_DEFAULTS.y,
      STAGE1_BLUR_DEFAULTS.strength,
      STAGE1_BLUR_DEFAULTS.color,
      STAGE1_BLUR_DEFAULTS.steps,
    );
    return { ok: true, action: 'enabled' };
  } catch (error) {
    return { ok: false, error };
  }
}
