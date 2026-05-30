// TMP-Q3 chunk B — Stage-2 cross-tile blend filter registration + Controller.
//
// Wires the GLSL fragment shader from `blend-shader-source.ts` into
// Phaser 4's filter pipeline:
//
//   1. Register a custom `BaseFilterShader` render node with the
//      `RenderNodeManager` under a stable name. Idempotent — safe to
//      call on every scene start.
//   2. Expose a `CrossTileBlendController` subclass of
//      `Phaser.Filters.Controller` whose `renderNode` field references
//      the registered name. Controllers are added to the foundation
//      display's `filters.external` list via `FilterList.add(controller)`.
//
// The fallback chain (Stage-2 fail → Stage-1 Blur → V0 hard edges) is
// driven by the caller (`foundation-blend.ts`). This module only
// provides the building blocks + an idempotent registrar that returns
// a structured result instead of throwing.
//
// **Phaser internal access:** the renderer's `RenderNodeManager` is a
// public field but `_nodeConstructors` is private. We read it
// defensively to skip duplicate registration; if the field is
// renamed in a future Phaser release the catch-all `try` keeps the
// registration call safe and the fallback chain handles the failure.

import Phaser from 'phaser';

import {
  BLEND_SHADER_FRAGMENT_SOURCE,
  CROSS_TILE_BLEND_RENDER_NODE_NAME,
  SHADER_TILE_PX,
  STAGE2_BLEND_DEFAULTS,
} from './blend-shader-source';

/** Surface area of `Phaser.Renderer.WebGL.RenderNodes.RenderNodeManager`
 *  we touch. Narrowed via a duck-typed interface so a TS rebuild
 *  against a future Phaser version surfaces breakage at the call site,
 *  not deep inside Phaser. */
interface RenderNodeManagerSurface {
  addNodeConstructor(name: string, constructor: unknown): unknown;
  /** Private but stable across Phaser 4.x minor releases. Read only;
   *  used to short-circuit duplicate registration without relying on
   *  `addNodeConstructor`'s throw behaviour (which would also clobber
   *  the helper's `ok:true` path). */
  _nodeConstructors?: Record<string, unknown>;
}

interface WebGLRendererSurface {
  renderNodes?: RenderNodeManagerSurface;
}

/** Surface of `Phaser.Renderer.WebGL.RenderNodes.BaseFilterShader`
 *  that our custom render node touches at runtime. The `programManager`
 *  is created by `BaseFilterShader`'s constructor and exposes a
 *  `setUniform(name, value)` we call from `setupUniforms`. */
interface BaseFilterShaderRuntimeSurface {
  programManager?: {
    setUniform(name: string, value: number | number[]): void;
  };
}

/** Public interface of the Stage-2 client-side filter controller.
 *  The runtime class is constructed lazily inside the registrar so
 *  that test environments (jsdom) which lack
 *  `Phaser.Renderer.WebGL.*` can still import this module. */
export interface CrossTileBlendController {
  active: boolean;
  blendRadius: number;
  blendStrength: number;
}

/** COSMETIC-3 fix from chunk-B /review-impl: clamp a numeric uniform
 *  to [0, 1] with a NaN-safe fallback to 0. Used to sanitize
 *  per-controller blend strength + radius before pushing to the GPU,
 *  so a future chunk-C slider that misfires can't crash the shader. */
function sanitizeUnitInterval(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(1, value));
}

/** Lazy class constructors. Built on first registrar call after we've
 *  verified `Phaser.Renderer.WebGL.RenderNodes.BaseFilterShader` is
 *  defined (i.e. running in a real browser, not jsdom). */
type LazyClasses = {
  renderNodeCtor: new (manager: unknown) => BaseFilterShaderRuntimeSurface;
  controllerCtor: new (
    camera: Phaser.Cameras.Scene2D.Camera,
    blendRadius?: number,
    blendStrength?: number,
  ) => CrossTileBlendController;
};

/** 3-state cache (LOW-1 fix from chunk-B /review-impl):
 *  - 'unset'        → `buildClasses` has not been attempted yet
 *  - `LazyClasses`  → build succeeded; subsequent calls return instantly
 *  - `null`         → build failed (Canvas mode / jsdom / API skew);
 *                     subsequent calls return null WITHOUT re-inspecting
 *                     the Phaser global on every invocation
 *
 *  Previously a plain `LazyClasses | null` typed cache stored null as
 *  "cache miss", causing every call in jsdom to re-walk the Phaser
 *  namespace. */
type CacheState = 'unset' | LazyClasses | null;
let cachedClasses: CacheState = 'unset';

function buildClasses(): LazyClasses | null {
  // Module-side defensive check — vitest / jsdom doesn't ship Phaser's
  // WebGL namespace. Bail with `null` so the caller routes to Stage-1.
  const webgl = (Phaser as unknown as { Renderer?: { WebGL?: unknown } })
    .Renderer?.WebGL as
    | { RenderNodes?: { BaseFilterShader?: unknown } }
    | undefined;
  const BaseFS = webgl?.RenderNodes?.BaseFilterShader;
  const FilterController = (
    Phaser as unknown as { Filters?: { Controller?: unknown } }
  ).Filters?.Controller;
  if (typeof BaseFS !== 'function' || typeof FilterController !== 'function') {
    return null;
  }
  type BaseFSCtor = new (
    name: string,
    manager: unknown,
    fragmentShaderKey: string | null,
    fragmentShaderSource: string,
  ) => BaseFilterShaderRuntimeSurface;
  const Base = BaseFS as BaseFSCtor;
  class RenderNode extends Base {
    constructor(manager: unknown) {
      super(
        CROSS_TILE_BLEND_RENDER_NODE_NAME,
        manager,
        null,
        BLEND_SHADER_FRAGMENT_SOURCE,
      );
    }
    setupUniforms(
      controller: CrossTileBlendController,
      drawingContext: { width: number; height: number },
    ): void {
      // COSMETIC-2 from chunk-B /review-impl: skip writes when the
      // controller is inactive. Phaser's standard pipeline already
      // skips inactive controllers; this guards against future API
      // shifts that might call setupUniforms unconditionally.
      if (!controller.active) {
        return;
      }
      const pm = this.programManager;
      if (!pm) return;
      pm.setUniform('uResolution', [
        drawingContext.width,
        drawingContext.height,
      ]);
      pm.setUniform('uTilePx', SHADER_TILE_PX);
      // COSMETIC-3 from chunk-B /review-impl: clamp + finite-check on
      // JS side before writing to GPU. STAGE2_BLEND_DEFAULTS flow is
      // already safe; this guards against chunk-C per-book hints that
      // might pass NaN / out-of-range values from a UI slider.
      pm.setUniform('uBlendRadius', sanitizeUnitInterval(controller.blendRadius));
      pm.setUniform(
        'uBlendStrength',
        sanitizeUnitInterval(controller.blendStrength),
      );
    }
  }
  type ControllerCtor = new (
    camera: Phaser.Cameras.Scene2D.Camera,
    renderNode: string,
  ) => CrossTileBlendController & { active: boolean };
  const Ctrl = FilterController as ControllerCtor;
  class Controller extends Ctrl {
    blendRadius: number;
    blendStrength: number;
    constructor(
      camera: Phaser.Cameras.Scene2D.Camera,
      blendRadius: number = STAGE2_BLEND_DEFAULTS.blendRadius,
      blendStrength: number = STAGE2_BLEND_DEFAULTS.blendStrength,
    ) {
      super(camera, CROSS_TILE_BLEND_RENDER_NODE_NAME);
      this.blendRadius = blendRadius;
      this.blendStrength = blendStrength;
    }
  }
  return { renderNodeCtor: RenderNode, controllerCtor: Controller };
}

function getOrBuildClasses(): LazyClasses | null {
  if (cachedClasses !== 'unset') {
    return cachedClasses;
  }
  cachedClasses = buildClasses();
  return cachedClasses;
}

/** Test-only: reset the lazy class cache back to the `'unset'` sentinel.
 *  Exposed so unit tests exercise both the "build succeeds" and "build
 *  returns null" paths without leaking state between cases.
 *
 *  COSMETIC-1 fix from chunk-B /review-impl: gated behind Vite's
 *  `import.meta.env.MODE === 'test'` so a production code path that
 *  accidentally imports this helper would no-op rather than silently
 *  invalidating the cache. */
export function _resetCrossTileBlendCache(): void {
  if (import.meta.env?.MODE === 'test') {
    cachedClasses = 'unset';
  }
}

/** Construct a new Stage-2 controller. Returns `null` when Phaser's
 *  WebGL classes are unavailable (jsdom / Canvas mode / API skew). */
export function newCrossTileBlendController(
  camera: Phaser.Cameras.Scene2D.Camera,
  blendRadius?: number,
  blendStrength?: number,
): CrossTileBlendController | null {
  const cls = getOrBuildClasses();
  if (!cls) return null;
  return new cls.controllerCtor(camera, blendRadius, blendStrength);
}

/** Structured result for the idempotent registrar. The caller branches
 *  on `ok` and routes failures into the Stage-1 Blur fallback. */
export type RegisterResult =
  | { ok: true; alreadyRegistered: boolean }
  | { ok: false; error: unknown };

/** Register the Stage-2 render node with the scene's renderer.
 *
 *  - Idempotent: if a node with the same name is already registered,
 *    returns `{ ok: true, alreadyRegistered: true }` without re-adding.
 *  - Canvas mode (no WebGL renderer) returns `{ ok: false, error }` so
 *    the caller falls back to Stage-1.
 *  - Any throw from `addNodeConstructor` is captured and surfaced as
 *    `{ ok: false, error }` instead of propagating.
 *
 *  Safe to call on every scene `create()` — the duplicate-name guard
 *  keeps subsequent calls cheap. */
export function registerCrossTileBlendRenderNode(
  scene: Phaser.Scene,
): RegisterResult {
  try {
    const renderer = scene.game.renderer as unknown as WebGLRendererSurface;
    const manager = renderer?.renderNodes;
    if (!manager || typeof manager.addNodeConstructor !== 'function') {
      return {
        ok: false,
        error: new Error(
          'scene.game.renderer.renderNodes unavailable — Canvas renderer or Phaser API skew',
        ),
      };
    }
    if (
      manager._nodeConstructors &&
      manager._nodeConstructors[CROSS_TILE_BLEND_RENDER_NODE_NAME]
    ) {
      return { ok: true, alreadyRegistered: true };
    }
    const cls = getOrBuildClasses();
    if (!cls) {
      return {
        ok: false,
        error: new Error(
          'Phaser.Renderer.WebGL.RenderNodes.BaseFilterShader unavailable — Canvas renderer or test environment',
        ),
      };
    }
    manager.addNodeConstructor(
      CROSS_TILE_BLEND_RENDER_NODE_NAME,
      cls.renderNodeCtor,
    );
    return { ok: true, alreadyRegistered: false };
  } catch (error) {
    return { ok: false, error };
  }
}
