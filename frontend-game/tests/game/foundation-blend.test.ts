// TMP-Q3 chunk A — unit tests for the Stage-1 smooth-blend filter
// helper. Verifies the activation path, the disable path, and the
// graceful fallback when the target lacks Phaser's filter API.

import { describe, expect, it, vi } from 'vitest';
import {
  applyBlendFilter,
  STAGE1_BLUR_DEFAULTS,
  type BlendFilterTarget,
} from '@/game/render/foundation-blend';

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
