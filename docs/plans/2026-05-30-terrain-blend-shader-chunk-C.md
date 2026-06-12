# Chunk C — Per-Book Blend Hints + FPS Probe + Visual Regression (TMP-Q3)

**Spec:** [`docs/specs/2026-05-30-terrain-blend-shader.md`](../specs/2026-05-30-terrain-blend-shader.md)
**Chunk A:** `e4872521` (Phaser built-in Blur + toggle)
**Chunk B:** `107e55a9` (custom cross-tile shader + fallback chain)
**Size:** L (9 files / 6 logic / 1 side effect = TerrainCell wire-shape additive)
**Goal:** Close the polish arc with the three remaining items from spec §3: per-book registry blend hints, FPS perf probe, Playwright screenshot regression baseline. Also bumps `STAGE2_BLEND_DEFAULTS` based on manual visual feedback (LOW-3 from chunk-B /review-impl).

## Architecture

### Per-book blend hints

Wire-shape choice: **extend `TerrainCell`** with two optional fields
rather than introducing a new top-level field on `TilemapView`. Reasons:
- TerrainCell is already the wire mechanism for per-kind metadata
  (primitive + tag); blend hints are per-kind too.
- Adds 0 bytes to `terrain_layer` (still u8 per tile).
- Additive Option pattern — V2 byte-identical preserved when None.

```rust
// services/tilemap-service/src/types/tile.rs
pub struct TerrainCell {
    pub primitive: TerrainPrimitive,
    pub tag: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub blend_radius: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub blend_strength: Option<f32>,
}
```

Backend pipeline:
1. `TerrainKindDef` (registry-loaded) gets the same two Option<f32> fields with validation `[0.0, 1.0]` + finite.
2. `Registry::build_default_terrain_vocabulary()` reads from the loaded `TerrainKindDef` and populates `TerrainCell`. Hints flow through automatically.
3. Default registry (`registry/default.toml`) gets blend hints on **two** terrain kinds as a demo (`lw:water` → softer, `lw:mountain` → sharper). Other kinds inherit defaults.

Frontend pipeline:
1. `TerrainCell` TS type extended with optional `blend_radius?: number` + `blend_strength?: number`.
2. `applyBlendFilterV2` computes a histogram of `view.terrain_layer` to find the dominant TerrainKind (highest tile count), looks up the corresponding `vocab[kind].blend_radius/blend_strength`, falls back to `STAGE2_BLEND_DEFAULTS`.
3. The hint values flow into `newCrossTileBlendController(camera, radius, strength)` which already accepts them.

### FPS perf probe

A standalone Playwright test (`blend-fps-probe.spec.ts`):
1. Navigates to /play, waits for Phaser canvas + HUD.
2. Installs a `requestAnimationFrame` counter via `page.evaluate`.
3. Samples for 3 seconds wall-clock.
4. Computes `fps = counter / seconds`.
5. Asserts `fps >= MIN_FPS` (default 30; configurable via env).
6. Toggles blend ON / OFF, asserts FPS doesn't tank below threshold in either state.

Caveat: Playwright headless chromium may run capped (e.g., 60 FPS hard cap or vsync-driven). The probe captures relative regression detection, not absolute perf truth.

### Visual regression baseline

A Playwright test (`blend-visual-regression.spec.ts`):
1. Captures canvas screenshots in three states:
   - Blend OFF (V0 hard edges)
   - Blend ON with default hints
   - (Optional) Custom hint applied via direct registry override
2. Stores PNG goldens under `e2e/__screenshots__/`.
3. Uses Playwright's `toHaveScreenshot()` with a small tolerance (`maxDiffPixelRatio: 0.01`) — first run creates goldens; subsequent runs compare.
4. Masks: HUD area (top-left HP/MP bars) + MetadataPanel (bottom-left) so debug overlay changes don't trigger false positives.

Caveat: cross-OS golden flake. Goldens are pinned to Windows x86_64 (developer host). Linux CI may produce ~0.5% pixel diff per platform-specific WebGL driver behavior. The 1% tolerance should absorb that; if not, CI gets `update-snapshots` task.

## File list (9 files)

| # | File | Action | Lines | Purpose |
|---|---|---|---|---|
| 1 | `services/tilemap-service/src/types/registry.rs` | MOD | ~20 | `TerrainKindDef.blend_radius/blend_strength` + validation |
| 2 | `services/tilemap-service/src/types/tile.rs` | MOD | ~15 | `TerrainCell.blend_radius/blend_strength` (additive) |
| 3 | `services/tilemap-service/src/registry.rs` | MOD | ~30 | `build_default_terrain_vocabulary` reads hints from `TerrainKindDef`; validation in `from_file` |
| 4 | `services/tilemap-service/registry/default.toml` | MOD | +6 | Demo: `lw:water` blend_radius=0.95 (softer water edge), `lw:mountain` blend_radius=0.55 (sharper rocky edge) |
| 5 | `services/tilemap-service/src/types/tile.rs` (tests block) | MOD | ~30 | Round-trip + skip-serializing tests |
| 6 | `frontend-game/src/types/tilemap.ts` | MOD | ~5 | TerrainCell TS type extension |
| 7 | `frontend-game/src/game/render/foundation-blend.ts` | MOD | ~40 | Dominant-kind histogram + hint lookup + plumbing into V2 helper signature |
| 8 | `frontend-game/e2e/blend-visual-regression.spec.ts` | NEW | ~80 | Golden screenshot baseline for V0 / Stage-1 / Stage-2 |
| 9 | `frontend-game/e2e/blend-fps-probe.spec.ts` | NEW | ~60 | Frame-rate measurement under each blend state |

## Invariants

1. **V2 byte-identical preserved** — when no terrain kind has `blend_radius`/`blend_strength` set (the chunk-C default state), TerrainCell serializes without the fields (`skip_serializing_if`). Existing snapshot pins from chunk B (`85b7a177...`) continue to pass.
2. **Backend validation** — out-of-range or non-finite hint values fail registry-load with a clear error, matching the existing decoration density + biome theme validation discipline.
3. **Frontend fallback** — when vocabulary doesn't include hints (pre-Q3 backend), the dominant-kind lookup returns undefined, foundation-blend falls back to `STAGE2_BLEND_DEFAULTS`. No frontend regression.
4. **Dominant-kind correctness** — histogram excludes u8=0 (void). For ties, the lowest TerrainKind wins (deterministic).
5. **Visual regression tolerance** — goldens pass at ≤1% pixel diff. Cross-OS drift documented in DEFERRED #041 (or successor).
6. **FPS probe doesn't false-positive** — threshold is 30 fps (well below typical 60); below that means a real regression.

## Test plan

| Test | File | Verifies |
|---|---|---|
| `terrain_kind_def_deserializes_without_blend_fields` | registry.rs | Pre-Q3 TOML round-trips |
| `terrain_kind_def_round_trips_with_blend_fields` | registry.rs | Hints persist through TOML/JSON |
| `registry_rejects_blend_radius_out_of_range` | registry.rs | -0.1 / 1.1 / NaN / Inf rejected |
| `registry_rejects_blend_strength_out_of_range` | registry.rs | Same |
| `terrain_cell_deserializes_without_blend_fields` | tile.rs | Pre-Q3 wire shape |
| `terrain_cell_skip_serializing_when_blend_none` | tile.rs | V2 byte-identical |
| `terrain_cell_round_trips_with_blend_fields` | tile.rs | Hints serialize when Some |
| `default_vocabulary_carries_blend_hints_from_toml` | registry.rs | Wire-up from def → TerrainCell |
| `dominant_kind_picks_highest_count_excluding_void` | foundation-blend.test.ts | Histogram correctness + tie-breaking |
| `apply_blend_filter_v2_uses_registry_hints_when_available` | foundation-blend.test.ts | Hint flows into controller constructor |
| `apply_blend_filter_v2_falls_back_to_defaults_when_no_hints` | foundation-blend.test.ts | Backward compat |
| `blend-visual-regression chromium` | e2e | Goldens captured + compared |
| `blend-fps-probe chromium` | e2e | FPS ≥ 30 under blend ON / OFF / Stage-1 |

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Cross-OS visual golden flake | Pin to Windows x86_64; document deferral; allow `maxDiffPixelRatio: 0.01` tolerance |
| FPS probe flaky in headless chromium | Threshold set well below typical (30 vs 60); test runs after warm-up; cull noisy initial 500ms |
| Backend hint validation throws for valid 0.0 | `[0.0, 1.0]` is INCLUSIVE — 0.0 is allowed (means "no blend" via shader's `clamp(0, 0, 1) = 0`) |
| Dominant-kind histogram cost on Continent tier (65k tiles) | Single linear scan = ~1ms; runs once per blend re-application (toggle), not per frame |
| Per-kind hints might surprise users (e.g., water uses blendRadius=0.95) | Document hints in default.toml comments; chunk C ships demo values that the user can override per-book |
| `STAGE2_BLEND_DEFAULTS` bump might regress chunk-A calibration test | Re-verify e2e after defaults change; bump conservatively |

## STAGE2_BLEND_DEFAULTS calibration (LOW-3 from chunk B)

Chunk B shipped `blendRadius=0.85, blendStrength=0.65` as structural defaults. Chunk C is the right moment to bump these based on manual visual feedback. The plan: run /play with chunk-C backend (with default hints in TOML), eyeball the blend, adjust the JS-side defaults to match the most pleasant result.

Bumping the defaults is a separate concern from per-book hints — the defaults ship as the kind-agnostic floor; hints override per-kind. The chunk-B-pinned calibration test (`expect(fellBackToStage1).toBe(false)`) doesn't depend on specific values, only on Stage-2 producing observable output.

## Ground-truth verification table

| Algorithm reference | File:line | Verified exists? |
|---|---|---|
| `TerrainKindDef` struct | `services/tilemap-service/src/types/registry.rs:85` | YES |
| `TerrainCell` struct | `services/tilemap-service/src/types/tile.rs:160` | YES |
| `Registry::build_default_terrain_vocabulary` | `services/tilemap-service/src/registry.rs:441` | YES |
| `TilemapView.terrain_vocabulary` shape | `frontend-game/src/types/tilemap.ts:222` | YES |
| `STAGE2_BLEND_DEFAULTS` const | `frontend-game/src/game/render/blend-shader-source.ts:90` | YES (chunk B) |
| `newCrossTileBlendController(camera, radius, strength)` signature | `frontend-game/src/game/render/cross-tile-blend-filter.ts:185` | YES (chunk B) |
| Playwright `toHaveScreenshot` API | `@playwright/test` | YES (built-in) |
| `requestAnimationFrame` counter pattern | `page.evaluate` standard | YES |

## Out of scope

- Per-zone blend hints (`ZoneSpec.blend_radius`) — covered structurally by per-kind hints since the dominant kind correlates with the zone's theme
- Cross-OS golden image management — DEFERRED #041 successor item
- Voronoi / non-rectangular blend kernels — V3.1+
- Backend hot-reload of hints — future operator concern

## Known limitations (LOW-5 from chunk-C /review-impl)

**Single hint pair per render** — the Stage-2 shader receives ONE `(blendRadius, blendStrength)` pair for the entire canvas, applied to whatever pixels the rendered tilemap texture contains. The shader cannot sample per-pixel `TerrainKind` because it operates on the already-rendered output of the foundation tilemap layer, not on the source u8 data.

Implication: a map with both Water (soft hint) AND Mountain (sharp hint) zones gets only the DOMINANT kind's hints — the non-dominant zone uses an aesthetic that may not match its content. `pickBlendHints` with LOW-2's "prefer kind with declared hints" tie-break mitigates this when the dominant kind doesn't declare hints, but a fundamentally mixed map still gets a single compromise hint pair.

True per-tile hints would require either:
- (a) A second shader pass that reads a per-tile `TerrainKind` data texture and looks up hints per-fragment, OR
- (b) A multi-pass renderer that paints each zone with its own filter

Both are out of chunk C scope. The architectural ceiling for chunk C is "one hint pair per render". V3.1+ may revisit when per-tile blending becomes load-bearing.
