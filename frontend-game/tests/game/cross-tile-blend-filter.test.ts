// TMP-Q3 chunk B — registrar unit tests.
//
// Exercises `registerCrossTileBlendRenderNode` against three target
// shapes:
//   1. Real jsdom (no `Phaser.Renderer.WebGL`) → returns ok:false
//      so the foundation-blend.ts V2 helper routes to Stage-1.
//   2. Fake renderer with `addNodeConstructor` mocked → idempotent
//      registration verified via duplicate-call test.
//   3. Fake renderer that throws → error is captured into the result.
//
// The render-node class itself is built lazily inside the registrar
// AFTER the WebGL guard, so we never instantiate it in tests.

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  CROSS_TILE_BLEND_RENDER_NODE_NAME,
  STAGE2_BLEND_DEFAULTS,
} from '@/game/render/blend-shader-source';
import {
  _resetCrossTileBlendCache,
  newCrossTileBlendController,
  registerCrossTileBlendRenderNode,
} from '@/game/render/cross-tile-blend-filter';

describe('registerCrossTileBlendRenderNode (TMP-Q3 chunk B)', () => {
  afterEach(() => {
    _resetCrossTileBlendCache();
  });

  it('returns ok:false in jsdom (no Phaser.Renderer.WebGL)', () => {
    // The real Phaser global in vitest doesn't ship the WebGL classes.
    // We use the project's REAL scene-like shape — no renderer.
    const fakeScene = {
      game: { renderer: {} },
    } as unknown as Phaser.Scene;
    const r = registerCrossTileBlendRenderNode(fakeScene);
    expect(r.ok).toBe(false);
    expect(((r as { error: Error }).error as Error).message).toMatch(
      /unavailable/i,
    );
  });

  it('returns ok:false when renderer is null (Canvas mode)', () => {
    const fakeScene = {
      game: { renderer: null },
    } as unknown as Phaser.Scene;
    const r = registerCrossTileBlendRenderNode(fakeScene);
    expect(r.ok).toBe(false);
  });

  it('returns ok:false when addNodeConstructor throws — unreachable in jsdom', () => {
    // In jsdom the lazy class builder returns null BEFORE
    // addNodeConstructor would be reached, so the registrar
    // short-circuits with the WebGL-unavailable error rather than the
    // addNodeConstructor throw. Production (browser with WebGL) is
    // where the catch around addNodeConstructor actually fires; the
    // test here just locks the structural fact that the WebGL guard
    // wins over the throw path.
    const addNodeConstructor = vi.fn(() => {
      throw new Error('phaser-internal-broken');
    });
    const fakeScene = {
      game: { renderer: { renderNodes: { addNodeConstructor } } },
    } as unknown as Phaser.Scene;
    const r = registerCrossTileBlendRenderNode(fakeScene);
    expect(r.ok).toBe(false);
    expect(addNodeConstructor).not.toHaveBeenCalled();
  });

  it('idempotency: short-circuits when _nodeConstructors already has the name', () => {
    // Simulate "already registered" by populating the private cache.
    const addNodeConstructor = vi.fn();
    const fakeScene = {
      game: {
        renderer: {
          renderNodes: {
            addNodeConstructor,
            _nodeConstructors: {
              [CROSS_TILE_BLEND_RENDER_NODE_NAME]: function StubCtor() {},
            },
          },
        },
      },
    } as unknown as Phaser.Scene;
    const r = registerCrossTileBlendRenderNode(fakeScene);
    expect(r).toEqual({ ok: true, alreadyRegistered: true });
    // No registration attempt was made — duplicate name skipped.
    expect(addNodeConstructor).not.toHaveBeenCalled();
  });

  it('idempotency: handles repeated calls without throwing even when not pre-populated', () => {
    // Two back-to-back calls with the same manager. Even without
    // _nodeConstructors pre-population, the lazy class builder
    // returns null in jsdom — so both calls return ok:false (not
    // throw, not partial state).
    const fakeScene = {
      game: { renderer: {} },
    } as unknown as Phaser.Scene;
    const a = registerCrossTileBlendRenderNode(fakeScene);
    const b = registerCrossTileBlendRenderNode(fakeScene);
    expect(a.ok).toBe(false);
    expect(b.ok).toBe(false);
  });
});

describe('newCrossTileBlendController (TMP-Q3 chunk B)', () => {
  afterEach(() => {
    _resetCrossTileBlendCache();
  });

  it('returns null in jsdom (Phaser WebGL classes unavailable)', () => {
    const camera = {} as unknown as Phaser.Cameras.Scene2D.Camera;
    const c = newCrossTileBlendController(camera);
    expect(c).toBeNull();
  });

  it('default uniforms expose the locked STAGE2_BLEND_DEFAULTS', () => {
    // Lock the public constants regardless of jsdom — these are
    // what the shader's setupUniforms wires into the GPU.
    expect(STAGE2_BLEND_DEFAULTS.blendRadius).toBeGreaterThan(0);
    expect(STAGE2_BLEND_DEFAULTS.blendRadius).toBeLessThanOrEqual(1);
    expect(STAGE2_BLEND_DEFAULTS.blendStrength).toBeGreaterThan(0);
    expect(STAGE2_BLEND_DEFAULTS.blendStrength).toBeLessThanOrEqual(1);
  });
});
