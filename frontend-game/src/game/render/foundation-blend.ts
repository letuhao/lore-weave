// TMP-Q3 chunks A + B — smooth-blend post-processing for the foundation
// tilemap layer.
//
// Two paths share this module:
//   - `applyBlendFilter(target, enabled)`  — Stage-1 Blur (chunk A).
//     Pure helper, no scene access, unit-testable with a duck-typed
//     mock target.
//   - `applyBlendFilterV2(target, enabled, scene)` — Stage-2 custom
//     cross-tile shader (chunk B). Falls back to Stage 1 if shader
//     registration / controller add fails. Falls back to V0 hard
//     edges if Stage 1 also fails.
//
// WorldScene calls the V2 entry point. The V1 entry remains exported
// so chunk-A's tests keep passing without changes.

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

// ──────────────────────────────────────────────────────────────────
// TMP-Q3 chunk B — Stage-2 custom cross-tile blend shader entry
// point + fallback chain.
// ──────────────────────────────────────────────────────────────────

import type Phaser from 'phaser';
import {
  newCrossTileBlendController,
  registerCrossTileBlendRenderNode,
} from './cross-tile-blend-filter';

/** `add(controller)` on `FilterList`. Narrowed via duck-type so the
 *  V2 helper can be unit-tested without touching the real Phaser
 *  Controller class. */
export interface ControllerAddSurface {
  enableFilters?: () => unknown;
  filters?: {
    external?: {
      clear?: () => void;
      add?: (controller: unknown, index?: number) => unknown;
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

/** Outcome of a Stage-2 apply call. `stage: 2` = custom shader running;
 *  `stage: 1` = fell back to chunk-A Blur; `stage: 0` = either disabled
 *  by toggle OR both stages failed (the `action` field disambiguates);
 *  `stage: -1` = target lacks Phaser filters entirely (e.g. plain
 *  `TilemapLayer`).
 *
 *  `action: 'failed'` is the LOW-5 fix from chunk-B /review-impl —
 *  previously stage:0 always reported `action: 'enabled'`, falsely
 *  suggesting a filter was running when both stages had collapsed
 *  to V0 hard edges. */
export type BlendV2Result =
  | {
      ok: true;
      stage: 2 | 1 | 0 | -1;
      action: 'enabled' | 'disabled' | 'unsupported' | 'failed';
    }
  | { ok: false; error: unknown };

/** Minimal `Phaser.Scene` shape the registrar needs. Duck-typed for
 *  unit-test isolation. */
export interface SceneSurface {
  game?: { renderer?: unknown };
  cameras?: { main?: Phaser.Cameras.Scene2D.Camera };
}

/** Apply the Stage-2 custom cross-tile blend filter, falling back to
 *  Stage-1 Blur on any failure, then V0 on Stage-1 failure.
 *
 *  Idempotent: each call clears `filters.external` before attaching.
 *  Toggling `enabled=false` clears both stages' filters. */
export function applyBlendFilterV2(
  target: ControllerAddSurface | null | undefined,
  enabled: boolean,
  scene: SceneSurface | null | undefined,
): BlendV2Result {
  if (!target) {
    return { ok: true, stage: -1, action: 'unsupported' };
  }
  if (typeof target.enableFilters !== 'function') {
    return { ok: true, stage: -1, action: 'unsupported' };
  }
  // Common preamble: enable + clear so we never stack filters from
  // a previous toggle. Mirrors the chunk-A path.
  try {
    target.enableFilters();
    target.filters?.external?.clear?.();
  } catch (error) {
    return { ok: false, error };
  }
  if (!enabled) {
    return { ok: true, stage: 0, action: 'disabled' };
  }
  // Try Stage 2 first: register the render node, then attach a
  // controller. ANY failure routes to Stage-1.
  const camera = scene?.cameras?.main;
  if (scene && camera && typeof target.filters?.external?.add === 'function') {
    const reg = registerCrossTileBlendRenderNode(
      scene as unknown as Phaser.Scene,
    );
    if (reg.ok) {
      try {
        const controller = newCrossTileBlendController(camera);
        if (controller) {
          target.filters.external.add(controller);
          return { ok: true, stage: 2, action: 'enabled' };
        }
      } catch {
        // Fall through to Stage 1.
      }
    }
  }
  // Stage-2 unavailable or threw — clear any partially-applied state
  // and route to Stage-1 Blur.
  try {
    target.filters?.external?.clear?.();
  } catch {
    /* best effort */
  }
  const stage1 = applyBlendFilter(target, true);
  if (stage1.ok && stage1.action === 'enabled') {
    return { ok: true, stage: 1, action: 'enabled' };
  }
  // LOW-5 fix: stage:0 here means BOTH Stage-2 and Stage-1 failed —
  // V0 hard edges render. Use action:'failed' rather than 'enabled'
  // so any caller branching on `action` doesn't mistake this for a
  // running filter.
  return { ok: true, stage: 0, action: 'failed' };
}
