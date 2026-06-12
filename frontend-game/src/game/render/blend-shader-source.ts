// TMP-Q3 chunk B — Stage-2 cross-tile blend shader source.
//
// Pure GLSL fragment shader as a string export. Lives in its own
// module so it can be imported by both the render-node registrar
// (cross-tile-blend-filter.ts) and any future Vite asset preloader
// without dragging Phaser type imports.
//
// Algorithm: for each output pixel, sample the rendered tilemap at
// 4 diagonal offsets (NE/NW/SE/SW) at half-tile distance. Compute the
// fragment's normalized distance from the nearest TILE CENTER. At
// tile centers the output is the unblended sample; near tile edges
// the output is the 4-neighbor average. The transition is smoothstep
// so the perceived effect is "sharp tile centers with softened
// boundaries" — exactly the polish target for the foundation layer
// without losing readability of individual tile sprites.
//
// Uniforms:
//   uMainSampler  — input texture (rendered tilemap layer)
//   uResolution   — canvas pixel dimensions (width, height)
//   uTilePx       — tile size in pixels (matches TILE_PX constant)
//   uBlendRadius  — kernel half-radius as a fraction of tile half-width
//                   (0.0 = no offset / pure passthrough; 1.0 = full tile)
//   uBlendStrength— blend mix factor at tile EDGE (0..1; 0 = no blend,
//                   1 = full neighbor average; tile center stays sharp)
//
// Fallback: Stage-1 Phaser `Blur` filter remains the safety net when
// this shader fails to compile / link / register.

export const BLEND_SHADER_FRAGMENT_SOURCE = `
precision highp float;

uniform sampler2D uMainSampler;
uniform vec2 uResolution;
uniform float uTilePx;
uniform float uBlendRadius;
uniform float uBlendStrength;

varying vec2 outTexCoord;

void main () {
  vec2 uv = outTexCoord;
  vec2 pixel = uv * uResolution;
  vec2 tile = pixel / max(uTilePx, 1.0);
  vec2 tileFrac = fract(tile);

  // Kernel half-radius in pixels (capped to avoid sampling across
  // multiple tiles even at large uBlendRadius values).
  float r = clamp(uBlendRadius, 0.0, 1.0) * uTilePx * 0.5;
  vec2 px = 1.0 / max(uResolution, vec2(1.0));

  vec4 c0 = texture2D(uMainSampler, uv);
  vec4 cNE = texture2D(uMainSampler, uv + vec2( r, -r) * px);
  vec4 cNW = texture2D(uMainSampler, uv + vec2(-r, -r) * px);
  vec4 cSE = texture2D(uMainSampler, uv + vec2( r,  r) * px);
  vec4 cSW = texture2D(uMainSampler, uv + vec2(-r,  r) * px);

  // Distance from tile center on [0, 1] per axis; edge factor in
  // [0, 1] — 0 at tile center, 1 at tile boundary.
  vec2 dCenter = abs(tileFrac - 0.5) * 2.0;
  float edge = max(dCenter.x, dCenter.y);

  // smoothstep keeps centers sharp; blend ramps up only in the outer
  // 60% of the tile. Multiply by uBlendStrength so the toggle in
  // viewer-store can interpolate or dial back the effect.
  float w = smoothstep(0.4, 1.0, edge) * clamp(uBlendStrength, 0.0, 1.0);

  vec4 mix4 = (cNE + cNW + cSE + cSW) * 0.25;
  gl_FragColor = mix(c0, mix4, w);
}
`;

/** Stable name under which the render node is registered with Phaser's
 *  RenderNodeManager. Used by both the Controller's `renderNode`
 *  field and the registration guard that prevents double-add. */
export const CROSS_TILE_BLEND_RENDER_NODE_NAME = 'CrossTileBlendFilter';

/** Default uniform values. The chunk-B calibration test (which gates
 *  the chunk's VERIFY phase) proves these defaults produce a
 *  pixel-observable cross-tile blend in real Chromium AND that the
 *  Stage-2 path is the active one (no silent fallback to Stage-1
 *  Blur). It does NOT yet verify the kernel produces an aesthetically
 *  pleasant blend.
 *
 *  LOW-3 from chunk-B /review-impl: aesthetic visual calibration
 *  deferred to chunk C, which lands per-book registry blend hints +
 *  a Playwright screenshot regression baseline. Until then, these
 *  numbers are structural references — they should be tuned with
 *  visual feedback before chunk C's regression baseline is captured.
 */
export const STAGE2_BLEND_DEFAULTS = {
  blendRadius: 0.85,
  blendStrength: 0.65,
} as const;

/** Constant tile size in pixels. Mirrors `frontend-game/src/game/
 *  config/constants.ts:TILE_PX` (32). Re-exported here so the shader
 *  registration code can populate uniforms without a circular import. */
export const SHADER_TILE_PX = 32;
