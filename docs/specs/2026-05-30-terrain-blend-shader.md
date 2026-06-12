# Terrain-Blend Shader — TerrainPainter Polish (TMP-Q3)

**Status:** DRAFT
**Author:** Claude (Opus 4.7) + letuhao1994 (PO)
**Created:** 2026-05-30
**Branch:** `mmo-rpg/terrain-blend-shader` (fresh, off `main` post PR #10)
**Driver:** TerrainPainter+BiomeThemePainter produce per-tile `TerrainKind` values, but `TilemapGPULayer` renders them with **hard pixel borders** between adjacent tile sprites. Result: even with biome-themed Perlin patches (chunks A→C of biome arc), the visual seams between `Forest`/`Grass`/`Rough` look pixel-grid-grid-like rather than Tale-of-Immortal painterly. PO locked "smooth GPU blend" approach over auto-tile or dithered borders.

---

## 1. Goal

Soften the hard pixel boundaries between adjacent `TerrainKind` values in the foundation tilemap layer without:
- Requiring new transition sprites per terrain pair (`project_multi_book_asset_constraint`)
- Breaking the V0 baseline rendering (graceful fallback when GPU shader unavailable)
- Changing the backend wire shape (frontend-only polish)

Two-stage approach:
1. **Stage 1 (chunk A — quick win):** Apply Phaser 4's built-in Blur filter at low strength + the `MakeSmoothPixelArt` shader addition to soften pixel edges. No GLSL written.
2. **Stage 2 (chunk B — true blend):** Custom `BaseFilterShader` reading the tilemap's render texture + sampling 4-neighbor `TerrainKind` from a data texture, doing per-pixel bilinear blend between adjacent tile sprites.

## 2. Non-Goals

- Auto-tile / 47-bitmask transition sprites (asset-heavy, rejected by PO)
- Backend-side blend hints (no `BlendProfile` on `TerrainKindDef` in chunks A/B; reserved for chunk C tuning if needed)
- Per-pixel decoration sprite blending (`TilemapObjectKind` overlays untouched)
- Voronoi / painterly distortion (vector-warp aesthetics are V3.1 work)
- Mobile WebGL 1.0 perf optimization (default Phaser 4 perf target sufficient for now)

## 3. Acceptance Criteria

| ID | Criterion | Verifier |
|---|---|---|
| **AC-BLEND-1** | V0 baseline rendering still works when filter pipeline unavailable (graceful fallback to hard-edge `TilemapGPULayer`) | Vitest unit test on `WorldScene.buildFoundationLayer` fallback branch + manual smoke |
| **AC-BLEND-2** | Stage 1 filter pipeline activates by default; visible edge softening at 1× zoom | Playwright screenshot diff (chunk A) |
| **AC-BLEND-3** | Filter pipeline can be toggled off via viewer-store `blendEnabled` flag for debug | Vitest unit test + viewer panel control |
| **AC-BLEND-4** | Stage 2 custom shader (chunk B) produces visually-distinct cross-tile blend vs Stage 1 built-ins | Playwright screenshot diff (chunk B) |
| **AC-BLEND-5** | FPS at Town (48²) and Country (192²) tiers stays within 10% of V0 baseline | Manual perf probe + reported in chunk C |
| **AC-BLEND-6** | No WebGL context errors in Chromium/Firefox console at any chunk | Playwright `pageerror` capture |

## 4. Architecture

### Stage 1 (chunk A) — Built-in filters

```ts
this.foundationDisplay.enableFilters();
this.foundationDisplay.filters.external.addBlur(/* low strength */);
// Optional: also wire MakeSmoothPixelArt via the TilemapGPULayer's
// shader-addition config IF Phaser 4 API allows post-construction
// addition. If not, stage-1 ships Blur-only and stage-2 takes over.
```

The `Blur` filter is GPU-accelerated and operates on the rendered tilemap texture. At low strength (quality=1, x=0.5, y=0.5) it softens the pixel grid without erasing tile identity.

### Stage 2 (chunk B) — Custom `BaseFilterShader`

```glsl
// Pseudo-fragment-shader (final form in chunk B)
uniform sampler2D uMainSampler;      // rendered tilemap (input)
uniform sampler2D uLayerData;        // data texture: per-tile TerrainKind u8
uniform sampler2D uTileset;          // raw tile spritesheet
uniform vec2 uGridSize;
uniform float uTilePx;
uniform float uBlendRadius;          // tunable softness (0..1)

void main() {
  vec2 tileCoord = vTexCoord * uGridSize;
  vec2 corner = fract(tileCoord);
  // Sample 4 neighbor TerrainKind values from uLayerData
  // Sample 4 corresponding tile sprites from uTileset at proper UV
  // Bilinear blend the 4 sprite colors using `corner` weights + smoothstep
  // Apply MakeSmoothPixelArt-style derivative-driven AA at the output
}
```

Backed by a `Phaser.Renderer.WebGL.RenderNodes.BaseFilterShader` instance, attached to the foundation layer's filter list. Falls back to Stage 1 (Blur) if shader compilation fails.

### Fallback chain

```
Stage 2 custom shader
    ↓ if compile fails or context lost
Stage 1 built-in Blur filter
    ↓ if enableFilters() throws
V0 baseline TilemapGPULayer (hard edges)
    ↓ if TilemapGPULayer construction fails
TilemapLayer (standard 2D context)
```

V0 fallback paths already exist in `WorldScene.buildFoundationLayer`. This work ADDS layers on top; it does not replace existing fallbacks.

## 5. Chunk Plan

| Chunk | Size | Files | Scope |
|---|---|---|---|
| **A — Stage 1 built-in Blur + toggle** | M (~5 files) | `WorldScene.ts` (enableFilters + addBlur), `viewer-store.ts` (`blendEnabled` flag default true), `viewer panel` (toggle UI), unit tests | Quick-win polish via Phaser built-ins. Toggle off → V0 baseline. |
| **B — Stage 2 custom shader** | L (~6 files) | NEW `frontend-game/src/game/render/blend-shader.ts` (BaseFilterShader subclass + GLSL string), NEW `blend-shader.glsl.ts` (frag source), WorldScene wire-up, fallback chain, unit tests, Playwright screenshot diff baseline | True cross-tile blend. Uniforms tuned for V3 aesthetic. |
| **C — Per-book tuning + perf + visual regression** | M (~4 files) | `WorldScene.ts` (read registry blend hints if present), backend `TerrainKindDef` optional `blend_radius` field (additive), perf probe script, Playwright golden screenshots | Final polish + regression net + DEFERRED #041 paired smoke. |

## 6. Risks + Mitigations

| Risk | Mitigation |
|---|---|
| Phaser 4 `enableFilters()` API surface unstable across versions | Pin `phaser` to current exact version in `package.json`; chunk-A integration test asserts API present |
| Custom shader fails to compile on some GPUs (mobile, integrated graphics) | Stage 2 falls back to Stage 1 on compile error; tested via `WebGL_lose_context` Phaser test harness |
| Blur filter degrades pixel-art aesthetic (over-softens) | Default strength tuned low (≤0.5); toggle exposed for off |
| FPS hit at Country/Continent tiers | Chunk C measures FPS; if degradation > 10%, demote stage 2 → stage 1 default |
| Screenshot-diff flake under different OS font rendering | Snapshots compared with tolerance (e.g. 5% pixel diff threshold) |
| `view.terrain_layer` u8 sentinel (0 = void) interacts with shader sampling | Stage 2 shader treats u8=0 as "use first valid neighbor" — graceful for partial Penrose coverage future |

## 7. Ground-Truth Verification Table

Per saved memory `feedback_verify_api_against_code_before_specifying_algorithm`:

| Algorithm reference | File:line | Verified exists? |
|---|---|---|
| `TilemapGPULayer` | `frontend-game/src/game/scenes/WorldScene.ts:111` | YES |
| `TilemapLayer` (fallback) | `WorldScene.ts:125` | YES |
| `FALLBACK_TERRAIN_TILE_INDEX` | `WorldScene.ts:85` | YES |
| `enableFilters()` on GameObject | Phaser 4 types `phaser.d.ts:13770` | YES |
| `filters.external.addBlur()` | Phaser 4 types `phaser.d.ts:21002` | YES |
| `BaseFilterShader` class | Phaser 4 types (BaseFilterShader extends BaseFilter) | YES |
| `MakeSmoothPixelArt()` shader addition | Phaser 4 types `phaser.d.ts:122020` | YES |
| `viewer-store.ts` toggle pattern | existing toggles like `showZoneBoundary` | YES (verify in chunk-A) |
| `TilemapView.terrain_layer` type | `frontend-game/src/types/tilemap.ts:221` | YES |

## 8. Open Questions

None — all PO decisions locked inline (style: smooth GPU blend, effort: L 3-chunk arc, branch: fresh `mmo-rpg/terrain-blend-shader`).
