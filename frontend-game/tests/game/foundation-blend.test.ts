// TMP-Q3 chunks A + B — unit tests for the smooth-blend filter
// helpers. Verifies the chunk-A Stage-1 Blur activation/disable/
// fallback paths AND the chunk-B Stage-2 cross-tile shader entry
// with its automatic Stage-1 fallback chain.

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  applyBlendFilter,
  applyBlendFilterV2,
  dominantTerrainKind,
  dominantTerrainKinds,
  pickBlendHints,
  STAGE1_BLUR_DEFAULTS,
  type BlendFilterTarget,
  type ControllerAddSurface,
  type SceneSurface,
} from '@/game/render/foundation-blend';
import { _resetCrossTileBlendCache } from '@/game/render/cross-tile-blend-filter';

/** Build a fake Phaser GameObject with the minimum filter API surface
 *  that `applyBlendFilter` calls. Returns the target + spies so each
 *  test can assert what was invoked. */
function mockTarget(): {
  target: BlendFilterTarget;
  enableFilters: ReturnType<typeof vi.fn>;
  clear: ReturnType<typeof vi.fn>;
  addBlur: ReturnType<typeof vi.fn>;
} {
  const enableFilters = vi.fn();
  const clear = vi.fn();
  const addBlur = vi.fn();
  const target: BlendFilterTarget = {
    enableFilters,
    filters: { external: { clear, addBlur } },
  };
  return { target, enableFilters, clear, addBlur };
}

describe('applyBlendFilter (TMP-Q3 chunk A)', () => {
  it('returns unsupported when target is null', () => {
    const r = applyBlendFilter(null, true);
    expect(r).toEqual({ ok: true, action: 'unsupported' });
  });

  it('returns unsupported when target is undefined', () => {
    const r = applyBlendFilter(undefined, true);
    expect(r).toEqual({ ok: true, action: 'unsupported' });
  });

  it('returns unsupported when target lacks enableFilters', () => {
    // Pre-Phaser-4 fallback path (e.g. TilemapLayer) doesn't expose
    // enableFilters — must NOT throw, must NOT call addBlur.
    const target: BlendFilterTarget = {
      filters: { external: { clear: vi.fn(), addBlur: vi.fn() } },
    };
    const r = applyBlendFilter(target, true);
    expect(r).toEqual({ ok: true, action: 'unsupported' });
  });

  it('enabled=true → calls enableFilters, clears prior, adds Blur with defaults', () => {
    // AC-BLEND-2 happy path — the Blur filter is added with the
    // conservative defaults locked in STAGE1_BLUR_DEFAULTS.
    const { target, enableFilters, clear, addBlur } = mockTarget();
    const r = applyBlendFilter(target, true);
    expect(r).toEqual({ ok: true, action: 'enabled' });
    expect(enableFilters).toHaveBeenCalledTimes(1);
    expect(clear).toHaveBeenCalledTimes(1);
    expect(addBlur).toHaveBeenCalledTimes(1);
    expect(addBlur).toHaveBeenCalledWith(
      STAGE1_BLUR_DEFAULTS.quality,
      STAGE1_BLUR_DEFAULTS.x,
      STAGE1_BLUR_DEFAULTS.y,
      STAGE1_BLUR_DEFAULTS.strength,
      STAGE1_BLUR_DEFAULTS.color,
      STAGE1_BLUR_DEFAULTS.steps,
    );
  });

  it('enabled=false → clears the filter list but does NOT add Blur', () => {
    // AC-BLEND-1 V0 preservation path.
    const { target, enableFilters, clear, addBlur } = mockTarget();
    const r = applyBlendFilter(target, false);
    expect(r).toEqual({ ok: true, action: 'disabled' });
    expect(enableFilters).toHaveBeenCalledTimes(1);
    expect(clear).toHaveBeenCalledTimes(1);
    expect(addBlur).not.toHaveBeenCalled();
  });

  it('idempotent re-apply with enabled=true does not stack filters', () => {
    // Calling twice with the SAME flag must clear before each add.
    const { target, clear, addBlur } = mockTarget();
    applyBlendFilter(target, true);
    applyBlendFilter(target, true);
    expect(clear).toHaveBeenCalledTimes(2);
    expect(addBlur).toHaveBeenCalledTimes(2);
  });

  it('runtime toggle on→off clears the filter without re-adding', () => {
    const { target, clear, addBlur } = mockTarget();
    applyBlendFilter(target, true);
    expect(addBlur).toHaveBeenCalledTimes(1);
    applyBlendFilter(target, false);
    expect(clear).toHaveBeenCalledTimes(2);
    expect(addBlur).toHaveBeenCalledTimes(1);
  });

  it('enableFilters throwing → ok:false with the captured error', () => {
    // AC-BLEND-1 fallback path: WebGL extension missing, context
    // lost, Phaser API skew — surfaces as ok:false so the caller can
    // log + degrade to V0 rendering.
    const target: BlendFilterTarget = {
      enableFilters: () => {
        throw new Error('WebGL context lost');
      },
      filters: { external: { clear: vi.fn(), addBlur: vi.fn() } },
    };
    const r = applyBlendFilter(target, true);
    expect(r.ok).toBe(false);
    expect((r as { error: Error }).error).toBeInstanceOf(Error);
    expect(((r as { error: Error }).error as Error).message).toContain('WebGL context lost');
  });

  it('addBlur missing after enableFilters succeeds → ok:false API-skew error', () => {
    // LOW-3 fix from chunk-A /review-impl: even when enableFilters
    // succeeds, if filters.external.addBlur isn't a function (Phaser
    // API rename, partial Phaser build, etc.), the helper must
    // surface it as ok:false rather than silently no-op via the
    // optional-chain.
    const target: BlendFilterTarget = {
      enableFilters: () => undefined,
      filters: {
        external: {
          clear: vi.fn(),
          // addBlur intentionally missing
        },
      },
    };
    const r = applyBlendFilter(target, true);
    expect(r.ok).toBe(false);
    expect(((r as { error: Error }).error as Error).message).toContain('addBlur missing');
    expect(((r as { error: Error }).error as Error).message).toContain('API skew');
  });

  it('addBlur throwing → ok:false with the captured error', () => {
    // Defensive: addBlur compilation failure (e.g. Blur shader unavail-
    // able) must NOT crash the scene. Returns ok:false instead.
    const target: BlendFilterTarget = {
      enableFilters: () => undefined,
      filters: {
        external: {
          clear: () => undefined,
          addBlur: () => {
            throw new Error('Blur shader unavailable');
          },
        },
      },
    };
    const r = applyBlendFilter(target, true);
    expect(r.ok).toBe(false);
    expect(((r as { error: Error }).error as Error).message).toContain('Blur shader unavailable');
  });
});

// ──────────────────────────────────────────────────────────────────
// TMP-Q3 chunk B — applyBlendFilterV2 + fallback chain to Stage 1.
// ──────────────────────────────────────────────────────────────────

function v2Mock(): {
  target: ControllerAddSurface;
  enableFilters: ReturnType<typeof vi.fn>;
  clear: ReturnType<typeof vi.fn>;
  add: ReturnType<typeof vi.fn>;
  addBlur: ReturnType<typeof vi.fn>;
} {
  const enableFilters = vi.fn();
  const clear = vi.fn();
  const add = vi.fn();
  const addBlur = vi.fn();
  const target: ControllerAddSurface = {
    enableFilters,
    filters: { external: { clear, add, addBlur } },
  };
  return { target, enableFilters, clear, add, addBlur };
}

const fakeCamera = {} as unknown as Phaser.Cameras.Scene2D.Camera;
const fakeScene: SceneSurface = {
  game: { renderer: {} },
  cameras: { main: fakeCamera },
};

describe('applyBlendFilterV2 (TMP-Q3 chunk B)', () => {
  afterEach(() => {
    // jsdom: Phaser.Renderer.WebGL is unavailable, so the lazy class
    // builder returns null and the cache holds that null. Resetting
    // here is defensive against any test that monkeypatches the
    // Phaser global to inject WebGL classes.
    _resetCrossTileBlendCache();
  });

  it('returns unsupported when target is null', () => {
    const r = applyBlendFilterV2(null, true, fakeScene);
    expect(r).toEqual({ ok: true, stage: -1, action: 'unsupported' });
  });

  it('returns unsupported when target lacks enableFilters', () => {
    const target: ControllerAddSurface = {
      filters: { external: { clear: vi.fn(), add: vi.fn(), addBlur: vi.fn() } },
    };
    const r = applyBlendFilterV2(target, true, fakeScene);
    expect(r).toEqual({ ok: true, stage: -1, action: 'unsupported' });
  });

  it('enabled=false clears filters and returns disabled stage:0', () => {
    const { target, enableFilters, clear, add, addBlur } = v2Mock();
    const r = applyBlendFilterV2(target, false, fakeScene);
    expect(r).toEqual({ ok: true, stage: 0, action: 'disabled' });
    expect(enableFilters).toHaveBeenCalledTimes(1);
    expect(clear).toHaveBeenCalledTimes(1);
    expect(add).not.toHaveBeenCalled();
    expect(addBlur).not.toHaveBeenCalled();
  });

  it('falls back to Stage-1 Blur when Phaser WebGL classes unavailable (jsdom)', () => {
    // In the vitest environment Phaser.Renderer.WebGL is undefined,
    // so registerCrossTileBlendRenderNode returns ok:false and the
    // V2 helper routes through Stage-1 Blur. Asserts the WHOLE
    // fallback chain.
    const { target, add, addBlur } = v2Mock();
    const r = applyBlendFilterV2(target, true, fakeScene);
    expect(r.ok).toBe(true);
    expect((r as { stage: number }).stage).toBe(1);
    expect((r as { action: string }).action).toBe('enabled');
    // Stage-2 controller was NOT added (no WebGL classes); Stage-1
    // Blur was added instead.
    expect(add).not.toHaveBeenCalled();
    expect(addBlur).toHaveBeenCalledTimes(1);
    expect(addBlur).toHaveBeenCalledWith(
      STAGE1_BLUR_DEFAULTS.quality,
      STAGE1_BLUR_DEFAULTS.x,
      STAGE1_BLUR_DEFAULTS.y,
      STAGE1_BLUR_DEFAULTS.strength,
      STAGE1_BLUR_DEFAULTS.color,
      STAGE1_BLUR_DEFAULTS.steps,
    );
  });

  it('falls back to V0 (stage:0, action:failed) when both Stage-2 and Stage-1 fail', () => {
    // addBlur throws → Stage-1 helper returns ok:false → V2 helper
    // surfaces stage:0 + action:'failed' (LOW-5 fix from chunk-B
    // /review-impl: action used to be 'enabled' here which was a
    // semantic mismatch — nothing is rendering).
    const { target } = v2Mock();
    target.filters!.external!.addBlur = () => {
      throw new Error('Stage-1 Blur also broken');
    };
    const r = applyBlendFilterV2(target, true, fakeScene);
    expect(r.ok).toBe(true);
    expect((r as { stage: number; action: string }).stage).toBe(0);
    expect((r as { stage: number; action: string }).action).toBe('failed');
  });

  it('runtime toggle on→off clears filters without leaving Stage-2 residue', () => {
    const { target, clear, add, addBlur } = v2Mock();
    applyBlendFilterV2(target, true, fakeScene);
    applyBlendFilterV2(target, false, fakeScene);
    // Multiple clears across the two calls.
    expect(clear.mock.calls.length).toBeGreaterThanOrEqual(2);
    // addBlur was called on the ON pass (stage-1 fallback), NOT on OFF.
    expect(addBlur).toHaveBeenCalledTimes(1);
    expect(add).not.toHaveBeenCalled();
  });

  it('enableFilters throwing → ok:false', () => {
    const target: ControllerAddSurface = {
      enableFilters: () => {
        throw new Error('WebGL context lost');
      },
      filters: { external: { clear: vi.fn(), add: vi.fn(), addBlur: vi.fn() } },
    };
    const r = applyBlendFilterV2(target, true, fakeScene);
    expect(r.ok).toBe(false);
    expect(((r as { error: Error }).error as Error).message).toContain('WebGL context lost');
  });

  it('no scene provided → falls back to Stage-1 Blur (no Stage-2 attempt)', () => {
    const { target, add, addBlur } = v2Mock();
    const r = applyBlendFilterV2(target, true, null);
    expect(r.ok).toBe(true);
    expect((r as { stage: number }).stage).toBe(1);
    expect(add).not.toHaveBeenCalled();
    expect(addBlur).toHaveBeenCalledTimes(1);
  });

  it('view passed but no per-kind hints → falls back to Stage-1 in jsdom', () => {
    // TMP-Q3 chunk C — V2 helper accepts an optional view arg. With
    // no hints declared in terrain_vocabulary, the picker returns an
    // empty override + the controller construction in jsdom returns
    // null, which routes to Stage-1.
    const { target, addBlur } = v2Mock();
    // Pass only the duck-typed shape `BlendHintSource` needs (no
    // primitive/tag); a real TilemapView would have those.
    const view = {
      terrain_layer: [1, 1, 2, 2],
      terrain_vocabulary: [{}, {}, {}],
    };
    const r = applyBlendFilterV2(target, true, fakeScene, view);
    expect(r.ok).toBe(true);
    expect((r as { stage: number }).stage).toBe(1);
    expect(addBlur).toHaveBeenCalledTimes(1);
  });
});

// ──────────────────────────────────────────────────────────────────
// TMP-Q3 chunk C — dominant-kind picker + per-book hint lookup.
// ──────────────────────────────────────────────────────────────────

describe('dominantTerrainKind (TMP-Q3 chunk C)', () => {
  it('returns the highest-count u8 excluding void (0)', () => {
    const layer = [1, 1, 1, 2, 2, 0, 0, 0];
    expect(dominantTerrainKind(layer)).toBe(1);
  });

  it('tie-break: lowest u8 wins (deterministic)', () => {
    // Equal count for kinds 2 and 3 — kind 2 wins.
    const layer = [2, 2, 3, 3];
    expect(dominantTerrainKind(layer)).toBe(2);
  });

  it('returns null for empty layer', () => {
    expect(dominantTerrainKind([])).toBe(null);
  });

  it('returns null for all-void layer', () => {
    expect(dominantTerrainKind([0, 0, 0, 0])).toBe(null);
  });

  it('excludes void from counting even when it dominates', () => {
    // Mostly void with a single Grass tile — Grass still wins.
    const layer = [0, 0, 0, 0, 0, 0, 0, 1];
    expect(dominantTerrainKind(layer)).toBe(1);
  });
});

describe('pickBlendHints (TMP-Q3 chunk C)', () => {
  it('returns empty override when view is null', () => {
    expect(pickBlendHints(null)).toEqual({});
  });

  it('returns empty override when terrain_vocabulary is absent', () => {
    expect(pickBlendHints({ terrain_layer: [1, 2, 3] })).toEqual({});
  });

  it('returns empty override when no kind dominates (all-void)', () => {
    expect(
      pickBlendHints({
        terrain_layer: [0, 0],
        terrain_vocabulary: [{ blend_radius: 0.9 }],
      }),
    ).toEqual({});
  });

  it('looks up the dominant kind in the vocabulary and returns its hints', () => {
    // Kind 4 (Water) dominates; vocab[4] has hints.
    const view = {
      terrain_layer: [4, 4, 4, 1, 1],
      terrain_vocabulary: [
        {},
        { blend_radius: 0.3, blend_strength: 0.3 },
        {},
        {},
        { blend_radius: 0.95, blend_strength: 0.55 },
      ],
    };
    expect(pickBlendHints(view)).toEqual({
      blendRadius: 0.95,
      blendStrength: 0.55,
    });
  });

  it('returns empty when dominant kind exists but vocabulary entry is missing', () => {
    // Kind 5 dominates but vocab only has 3 entries — index 5 is undefined.
    const view = {
      terrain_layer: [5, 5, 5],
      terrain_vocabulary: [{}, {}, {}],
    };
    expect(pickBlendHints(view)).toEqual({});
  });

  it('passes through undefined hints when vocab entry has no blend fields', () => {
    const view = {
      terrain_layer: [1, 1, 1],
      terrain_vocabulary: [{}, { /* no hints */ }],
    };
    expect(pickBlendHints(view)).toEqual({
      blendRadius: undefined,
      blendStrength: undefined,
    });
  });

  it('LOW-2: tied kinds — prefers the one that DECLARES blend hints', () => {
    // Equal count for kinds 1 (no hints) and 2 (has hints).
    // Old behavior: kind 1 wins by lowest-u8 tie-break → no hints.
    // New behavior (LOW-2 fix): kind 2 wins because it declares hints.
    const view = {
      terrain_layer: [1, 2],
      terrain_vocabulary: [{}, {}, { blend_radius: 0.4, blend_strength: 0.6 }],
    };
    expect(pickBlendHints(view)).toEqual({
      blendRadius: 0.4,
      blendStrength: 0.6,
    });
  });

  it('LOW-2: tied kinds with neither declaring hints — falls back to lowest u8', () => {
    // Both 3 and 5 tied; neither has hints. Lowest u8 (3) wins.
    const view = {
      terrain_layer: [3, 5],
      terrain_vocabulary: [{}, {}, {}, {}, {}, {}],
    };
    expect(pickBlendHints(view)).toEqual({
      blendRadius: undefined,
      blendStrength: undefined,
    });
  });

  it('LOW-2: NO ties — preserves dominant-kind behaviour', () => {
    // Kind 1 dominates (3 tiles) over kind 2 (1 tile). Even though
    // kind 2 has hints, kind 1 is the dominant winner — its absent
    // hints are returned (frontend falls back to STAGE2_BLEND_DEFAULTS).
    const view = {
      terrain_layer: [1, 1, 1, 2],
      terrain_vocabulary: [{}, {}, { blend_radius: 0.4 }],
    };
    expect(pickBlendHints(view)).toEqual({
      blendRadius: undefined,
      blendStrength: undefined,
    });
  });
});

describe('dominantTerrainKinds (TMP-Q3 chunk C — LOW-2 helper)', () => {
  it('returns all kinds tied for highest count, ascending', () => {
    // 1 and 2 tied with 2 each, sorted ascending.
    expect(dominantTerrainKinds([1, 1, 2, 2, 3])).toEqual([1, 2]);
  });

  it('returns single kind when there is a clear winner', () => {
    expect(dominantTerrainKinds([1, 1, 1, 2])).toEqual([1]);
  });

  it('returns empty array for empty layer', () => {
    expect(dominantTerrainKinds([])).toEqual([]);
  });
});
