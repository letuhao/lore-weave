# Chunk A — Stage 1 Built-in Blur Filter + Toggle (TMP-Q3)

**Spec:** [`docs/specs/2026-05-30-terrain-blend-shader.md`](../specs/2026-05-30-terrain-blend-shader.md)
**Size:** M (5 files / 4 logic / 1 side effect = WorldScene render path)
**Goal:** Ship a visible polish quick-win using Phaser 4 built-in `Blur` filter applied to the foundation tilemap layer, with a viewer-store toggle for debug. No GLSL written. V0 baseline preserved via fallback chain.

## File list (5 files)

| # | File | Action | Lines | Purpose |
|---|---|---|---|---|
| 1 | `frontend-game/src/game/scenes/WorldScene.ts` | MOD | ~30 | After `buildFoundationLayer`, call `enableFilters()` + `addBlur(...)` on the foundation display. Wrap in try/catch + log + skip on failure. Guarded by viewer-store flag. |
| 2 | `frontend-game/src/store/viewer-store.ts` | MOD | ~10 | Add `blendEnabled: boolean` field (default `true`), `setBlendEnabled` action. Mirror existing toggle patterns (`showZoneBoundary`, etc.). |
| 3 | `frontend-game/src/components/viewer/ViewerControls.tsx` (or equivalent panel) | MOD | ~12 | Checkbox "Smooth blend" bound to store. Visible label + tooltip. |
| 4 | `frontend-game/tests/store/viewer-store.test.ts` | MOD | ~15 | Vitest: default `true`, toggle flips, persists across `applyView` |
| 5 | `frontend-game/tests/game/world-scene-blend.test.ts` (NEW) | NEW | ~80 | Unit test: blend filter activation path + fallback when `enableFilters` throws |

## Invariants (V0 preservation)

1. **`blendEnabled = false` ⇒ V0 baseline** — When the flag is off, `enableFilters()` is NOT called. `foundationDisplay` renders exactly as it did pre-chunk-A.
2. **`enableFilters()` throw ⇒ fallback** — If activation fails (WebGL context lost, Phaser version mismatch), the catch block logs and the foundation continues to render via plain `TilemapGPULayer`. No user-visible error.
3. **No backend touch** — backend wire shape unchanged; tilemap-service still returns the same `terrain_layer`.
4. **Existing tilemap fallback preserved** — the `TilemapLayer` fallback (when `TilemapGPULayer` itself fails) still works; blend filter is additive on top.

## Blur tuning (default values)

```ts
this.foundationDisplay.filters.external.addBlur(
  /* quality */ 1,      // low quality — fewer texture samples
  /* x */ 0.5,          // tiny horizontal blur
  /* y */ 0.5,          // tiny vertical blur
  /* strength */ 1,     // single-pass
  /* color */ 0xffffff, // no tint
  /* steps */ 4,        // 4 sample taps per pixel
);
```

These values are intentionally conservative. Chunk B will overlay the true cross-tile shader, so chunk A's blur exists to (a) reduce hard pixel edges, (b) demonstrate the filter activation path works.

## Test plan

| Test | File | Verifies |
|---|---|---|
| `viewer_store_default_blend_enabled_is_true` | `viewer-store.test.ts` | AC-BLEND-3 default |
| `viewer_store_set_blend_enabled_toggles` | `viewer-store.test.ts` | AC-BLEND-3 toggle |
| `viewer_store_blend_persists_across_view_apply` | `viewer-store.test.ts` | Toggle survives data refresh |
| `world_scene_blend_filter_activates_when_enabled` | `world-scene-blend.test.ts` (NEW) | AC-BLEND-2 happy path |
| `world_scene_blend_filter_skips_when_disabled` | `world-scene-blend.test.ts` (NEW) | AC-BLEND-1 V0 preservation |
| `world_scene_blend_filter_falls_back_on_enable_failure` | `world-scene-blend.test.ts` (NEW) | AC-BLEND-1 fallback |

## Non-invasive design

- **No props plumbing** — the toggle lives in the viewer store, read directly by `WorldScene` via store subscription (matches `showZoneBoundary` pattern).
- **No new exports** — `addBlur` is called inline; no new helper module.
- **No e2e impact** — chromium smoke (AC-DECO-8, AC-BIOME-8) doesn't exercise visual fidelity; chunk A is invisible to those tests.

## Out of scope (chunk B/C)

- Custom `BaseFilterShader` + GLSL → chunk B
- Cross-tile bilinear blend → chunk B
- Per-book registry blend hints → chunk C
- Visual regression screenshot diff baseline → chunk C
- FPS perf probe → chunk C

## Risk register

| Risk | Mitigation |
|---|---|
| `TilemapGPULayer.enableFilters()` not available on standard `TilemapLayer` fallback | Type-narrow check before calling; only enable filters on the GPU layer path |
| Blur over-softens visible tile centers | Default values intentionally conservative (quality=1, strength=1); chunk B replaces with proper shader anyway |
| Filter activation flicker on view-apply | Apply filter ONCE at scene boot, not on every `applyView` (existing pattern) |
| WebGL context loss mid-game | Phaser handles context restore; filter list is rebuilt on context restore (Phaser 4 default behavior) |
