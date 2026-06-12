# Chunk B — Stage 2 Custom Cross-Tile Blend Shader (TMP-Q3)

**Spec:** [`docs/specs/2026-05-30-terrain-blend-shader.md`](../specs/2026-05-30-terrain-blend-shader.md)
**Chunk A:** committed at `e4872521` (Phaser built-in Blur + toggle, AC-BLEND-1/2/3)
**Size:** L (~5 files / 5 logic / 1 side effect = WorldScene shader registration)
**Goal:** Replace Stage-1 Phaser `Blur` with a custom `BaseFilterShader` + `Controller` that does a controlled cross-tile bilinear blend. Same `blendEnabled` toggle. Stage-1 Blur becomes the fallback if shader compile fails.

## Architecture (verified against Phaser 4 source)

Three layers:
1. **Fragment shader source** (`blend-shader.glsl.ts`) — pure string export, no Phaser imports.
2. **`BaseFilterShader` render node** registered ONCE per scene via the renderer's `RenderNodeManager`. Lives under a stable name (e.g. `'FilterCrossTileBlend'`).
3. **`Controller` subclass** wraps the render node + carries shader uniforms (e.g. `uKernelRadius`, `uBlendStrength`). Added to `filters.external` via `filterList.add(myController)`.

### Verified Phaser 4 APIs

| API | Phaser source ref | Used for |
|---|---|---|
| `Phaser.Filters.Controller(camera, renderNodeName)` | `phaser.esm.js:33993` | Base class for our custom controller |
| `FilterList.add(filter, index?)` | `phaser.esm.js:46362` | Append the controller to external filter list |
| `Phaser.Renderer.WebGL.RenderNodes.BaseFilterShader(name, manager, fragmentShaderKey?, fragmentShaderSource?, shaderAdditions?)` | type defs `phaser.d.ts:120108` | Register the GPU-side render node |
| Scene's `renderer.renderNodes.addNodeConstructor(name, ctor)` | Phaser 4 RenderNodeManager | Register a custom render node at runtime |
| Existing `Blur` Controller (`phaser.esm.js:33303`) | Reference model | How `Controller.call(this, camera, 'FilterBlur')` ties to the render-node name |

### Algorithm (`blend-shader.glsl.ts`)

```glsl
precision highp float;
uniform sampler2D uMainSampler;     // input: rendered tilemap (already painted)
uniform vec2 uResolution;           // canvas px size
uniform float uTilePx;              // TILE_PX (32 default)
uniform float uBlendRadius;         // 0..1 — fraction of tile half-width

varying vec2 outTexCoord;

void main() {
    vec2 uv = outTexCoord;
    vec2 pixel = uv * uResolution;
    vec2 tile = pixel / uTilePx;
    vec2 tileFrac = fract(tile);            // 0..1 within current tile
    // Sample radius in pixels, controlled by uBlendRadius * uTilePx/2
    float r = uBlendRadius * uTilePx * 0.5;
    vec2 px = 1.0 / uResolution;
    // 4 diagonal taps + center
    vec4 c0 = texture2D(uMainSampler, uv);
    vec4 cNE = texture2D(uMainSampler, uv + vec2( r, -r) * px);
    vec4 cNW = texture2D(uMainSampler, uv + vec2(-r, -r) * px);
    vec4 cSE = texture2D(uMainSampler, uv + vec2( r,  r) * px);
    vec4 cSW = texture2D(uMainSampler, uv + vec2(-r,  r) * px);
    // Weight diagonals by smoothstep distance from tile center; centers
    // stay sharp, edges blend.
    vec2 dCenter = abs(tileFrac - 0.5) * 2.0;     // 0 at center, 1 at edge
    float edge = max(dCenter.x, dCenter.y);
    float w = smoothstep(0.4, 1.0, edge);          // 0 inside, 1 at edge
    vec4 mix4 = (cNE + cNW + cSE + cSW) * 0.25;
    gl_FragColor = mix(c0, mix4, w);
}
```

Tile centers render sharp (`w=0` → pure center color). Tile edges crossfade with the 4 diagonal neighbors (`w≈1` → averaged). No new art needed; the kernel runs on the already-rendered tilemap so it works with any tileset / book.

## File list (5 modified + 2 new)

| # | File | Action | Lines | Purpose |
|---|---|---|---|---|
| 1 | `frontend-game/src/game/render/blend-shader-source.ts` | NEW | ~60 | Exports the GLSL fragment shader string + uniform names |
| 2 | `frontend-game/src/game/render/cross-tile-blend-filter.ts` | NEW | ~120 | Registers the BaseFilterShader render node (idempotent per game), exports Controller subclass `CrossTileBlendController` |
| 3 | `frontend-game/src/game/render/foundation-blend.ts` | MOD | ~40 | Add `applyBlendFilterV2(target, enabled, scene)` that tries the custom shader path first, falls back to Stage-1 Blur on failure; keep V1 helper for tests |
| 4 | `frontend-game/src/game/scenes/WorldScene.ts` | MOD | ~10 | Pass `this` (the scene) into `applyBlendFilterV2` so the helper can access the renderer for shader registration |
| 5 | `frontend-game/tests/game/foundation-blend.test.ts` | MOD | ~80 | Add tests for V2 path: registration failure falls back to Stage 1, controller addition + removal idempotency |
| 6 | `frontend-game/tests/game/cross-tile-blend-filter.test.ts` | NEW | ~80 | Unit-test the shader registration mock + uniform setting |
| 7 | `frontend-game/e2e/blend-calibration.spec.ts` | MOD | ~10 | Update the calibration test to assert pixel-difference between Stage-1 Blur and Stage-2 shader (proves Stage 2 produces a DIFFERENT effect than Stage 1, not just any blur) |

## Invariants

1. **Stage 2 default ON when supported** — when WebGL + shader compile succeed, Stage 2 ships.
2. **Fallback to Stage 1 on shader compile failure** — catch shader-link errors, log, attempt Stage-1 Blur instead. If Stage-1 also fails, fall through to V0 hard edges.
3. **Idempotent registration** — `registerCrossTileBlendNode(scene)` checks if the render node already exists before registering. Safe across scene restarts.
4. **Toggle parity with chunk A** — `blendEnabled = false` removes BOTH the Stage-2 controller AND any residual Stage-1 Blur; result: V0 hard edges.
5. **No backend changes** — chunk B is frontend-only, same as chunk A.

## Test plan

| Test | File | Verifies |
|---|---|---|
| `cross_tile_blend_register_returns_idempotent` | NEW | Calling `register*` twice on the same scene returns the SAME render node name; no duplicate registration |
| `apply_blend_filter_v2_registers_then_adds_controller` | NEW | Happy path — registration + filter list `.add(controller)` called |
| `apply_blend_filter_v2_falls_back_to_blur_when_shader_register_throws` | NEW | Stage-2 registration throws → fallback path calls Stage-1 `addBlur` |
| `apply_blend_filter_v2_falls_back_when_addController_throws` | NEW | Controller add throws → Stage-1 Blur takes over |
| `apply_blend_filter_v2_when_disabled_clears_both_stages` | NEW | `enabled=false` removes any custom controller + any Blur |
| `e2e: blend-calibration screenshot differs from Stage-1 baseline` | MOD | Stage-2 visually distinct from Stage-1 (use the previously captured Stage-1 byte length OR add toggle-via-evaluate to flip strategy) |

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Phaser's `renderNodes` registration API is internal / changes shape | Wrap registration in try/catch + fall back to Stage-1 Blur; test the fallback path explicitly |
| Fragment shader compile fails on older WebGL drivers | Same fallback chain; e2e test runs on Chromium baseline |
| Custom render node uniforms not picked up by Phaser's draw pass | Verify by reading Phaser 4's `BaseFilterShader.setupUniforms` flow; chunk-B research phase confirms before writing the shader |
| Calibration test flaky if Stage 1 and Stage 2 produce VERY similar byte output | Use a higher kernel radius for the calibration check to widen the visible diff |
| Stage-1 fallback was the chunk-A code path — won't regress because the same helper is reused |

## Out of scope (chunk C)

- Per-book registry blend hints (`TerrainKindDef.blend_radius` field)
- FPS perf probe at Country / Continent tiers
- Playwright screenshot regression baseline (multi-fixture golden)
- Tuning the uniforms based on real visual feedback (defer to chunk C calibration)
