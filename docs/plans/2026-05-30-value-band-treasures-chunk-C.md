# Chunk C — Zone-tier overlay + MetadataPanel breakdown + visual goldens (TMP-Q4)

**Spec:** [`docs/specs/2026-05-30-value-band-treasures.md`](../specs/2026-05-30-value-band-treasures.md)
**Chunk A:** `33df910d` (wire shape)
**Chunk B:** `93043b68` (per-pile badges + Inspector treasure section)
**Branch:** stacks on `mmo-rpg/terrain-blend-shader`
**Size:** L (8 files / 5 logic / 0 side effects — FE-only)
**Goal:** Close the arc with the design-review aids the spec promised: toggleable zone-tier overlay that tints each zone by its max-tier color, MetadataPanel "Zones" breakdown table (id · role · pile count · total value), and Playwright visual regression goldens using a fresh treasure-bearing template fixture so the badges + overlay rendering is locked.

## Architecture

### Zone-tier overlay

**Wire-up:**
- `viewer-store.showTreasureBands: boolean` (default `false`) + `setShowTreasureBands` action.
- `LayerToggles.tsx` adds a "Treasure bands" checkbox in the Polish subsection (below "Smooth blend").
- WorldScene subscribes to `showTreasureBands` and forwards it to a new handle exposed by `overlay-rt.ts`.

**Rendering:**
- Lives inside `overlay-rt.ts` alongside `drawZoneCenters` so the existing OverlayRtHandle pattern carries it. New helper `drawTreasureBandsOverlay(scene, view, parent)` that:
  1. For each zone, compute the dominant band: highest `value` among `view.object_placements.filter(p => p.tier_index === 0 && p.value != null && nearestZoneOf(p.anchor) === zone.zone_id)`. Fall back to "no band" (skip rendering) when zone has no treasures.
  2. Paint each set tile of `zone.assigned_tiles` as a translucent rectangle into a RenderTexture (one shared RT per scene). `fillRect(x * TILE_PX, y * TILE_PX, TILE_PX, TILE_PX, bandColor, alpha = 0.18)`.
  3. RT depth = 55 (above foundation 0, above paths RT 50, below props 100, below zone-center markers 200).
  4. Handle return: `setTreasureBandsVisible(v: boolean)`. When `false`, the RT's `.visible = false` (NOT destroyed — same fallback chain pattern as TMP-Q3 chunk B).
  5. Computed once at tilemap load, not per frame.

**Nearest-zone-of-anchor algorithm:** `placement.anchor` is a tile coordinate. Per-tile nearest-zone is the Voronoi of `zones[].center_position`. For each placement, find the closest `center_position` (Euclidean). O(zones × placements) = ~5 × 100 typical → trivial.

**Backward-compat:** when `view.zones[i].assigned_tiles` is `undefined` (pre-V1.2 fixture or a parse failure), skip that zone's fill. The overlay renders zero-or-more tinted regions; no crash.

### MetadataPanel zone breakdown

**New pure helper:**
```ts
// frontend-game/src/components/viewer/zone-breakdown.ts
export interface ZoneBreakdownRow {
  zone_id: string;
  zone_role: string;
  pile_count: number;
  total_value: number;
  band: number; // 0..4 via pickValueBand on max-tier-0 value
}

export function computeZoneBreakdown(view: TilemapView): ZoneBreakdownRow[];
```

- Walks `view.zones` and `view.object_placements` once.
- Filters placements to `kind === 'treasure'` (chunk B `shouldStampBadge` semantic).
- Buckets by nearest-zone Voronoi (same algorithm the overlay uses; extract to shared helper `nearestZoneOf(anchor, zones)`).
- Per-zone: pile_count = #treasure piles assigned; total_value = sum of values; band = `pickValueBand(maxValueOfTier0Piles, view.registry_ref?.value_band_thresholds ?? null)`.
- Returns rows sorted by `total_value` desc (zones with most loot float to top); tiebreaker on `zone_id` asc for determinism.

**Panel integration:**
- New collapsible `<details>` block in `MetadataPanel.tsx` between the existing "zones" details and the close — labeled "Treasure breakdown".
- Renders rows: `[id] [role] [piles] [Σ value] [band-swatch]`.
- Empty state: "no treasure placed" when `rows.length === 0`.

### Visual regression goldens

**New fixture: `frontend-game/public/templates/treasure-demo.json`**
- 5 zones similar to `minimal.json` BUT with `treasure_tiers` populated:
  - `capital` (Hub): tier `[5000, 9000, density 6]` (gilt + high band)
  - `frontier` (Wilderness): tier `[2000, 5000, density 8]` (mid + high)
  - `borderlands` (Wilderness): tier `[300, 1500, density 10]` (low + low-mid)
  - `inland_sea` (Sea): empty (no treasure in sea zones)
  - `rival` (Forbidden): empty (Forbidden zones skip TreasurePlacer per chunk A)
- Plus a `decoration_density` block matching minimal.json (so the existing AC-DECO-8 surface still works against this fixture if needed).

**New e2e spec: `frontend-game/e2e/treasure-bands-visual-regression.spec.ts`**
- 2 goldens:
  1. `treasure-bands-on.png` — page loads `/play?template=treasure-demo`, badges visible, Treasure bands overlay ON
  2. `treasure-badges-only.png` — same template, overlay OFF (badges still visible)
- Pattern mirrors `e2e/blend-visual-regression.spec.ts`:
  - `test.beforeEach` probes `/livez`; skips if backend down
  - `bootScene` navigates + waits for HUD + canvas + waitTimeout(1500) for Stage-2 blend stability
  - `maxDiffPixelRatio: 0.02` + `timeout: 30_000` + `animations: 'disabled'`
- Toggle "Treasure bands" via UI label click (same pattern as chunk B "Smooth blend" toggle).

**Cross-platform note:** Playwright stores per-platform goldens; CI on Linux + dev on Windows produce different PNGs. Same regeneration discipline as chunk-C blend goldens (LOW-4 from TMP-Q3 chunk-C review): commit all platform PNGs.

## File list (8 files projected)

| # | File | Action | Lines (est) | Purpose |
|---|---|---|---|---|
| 1 | `frontend-game/src/store/viewer-store.ts` | MOD | ~10 | `showTreasureBands: boolean` + `setShowTreasureBands` |
| 2 | `frontend-game/src/components/viewer/LayerToggles.tsx` | MOD | ~15 | "Treasure bands" checkbox in Polish subsection |
| 3 | `frontend-game/src/components/viewer/zone-breakdown.ts` | NEW | ~80 | `computeZoneBreakdown(view)` pure helper + `nearestZoneOf` helper |
| 4 | `frontend-game/src/components/viewer/MetadataPanel.tsx` | MOD | ~40 | Treasure breakdown collapsible section |
| 5 | `frontend-game/src/game/render/overlay-rt.ts` | MOD | ~70 | `drawTreasureBandsOverlay` + `setTreasureBandsVisible` handle |
| 6 | `frontend-game/src/game/scenes/WorldScene.ts` | MOD | ~10 | Subscribe to `showTreasureBands`, call handle |
| 7 | `frontend-game/public/templates/treasure-demo.json` | NEW | ~50 | Treasure-bearing 5-zone fixture |
| 8 | `frontend-game/tests/components/zone-breakdown.test.ts` | NEW | ~100 | Pure helper tests (no React) |
| 9 | `frontend-game/tests/store/viewer-store.test.ts` | MOD | ~25 | Toggle tests + default-false check |
| 10 | `frontend-game/e2e/treasure-bands-visual-regression.spec.ts` | NEW | ~80 | 2 Playwright goldens + bootScene helper |

That's 10 files counted — bumped from initial 8 due to test files. Still L-tier (6+ files).

## Invariants

1. **Default OFF for the overlay** — author opts in. `blendEnabled` defaulted TRUE in chunk-B blend, but the band overlay is an at-a-glance design review aid, not a "polish" feature, so default OFF avoids visual noise on first load.
2. **V0 fallback chain pattern** — `setTreasureBandsVisible(false)` hides the RT; doesn't destroy. Re-toggling ON is instant.
3. **Pure helper for breakdown** — `computeZoneBreakdown` takes a TilemapView and returns rows. No React, no store, no side effects. Testable via vitest.
4. **assigned_tiles is the authoritative zone-of-placement (MED-1 fix from self-review)** — both the overlay paint AND the breakdown derivation lookup which zone owns a placement by reading `zones[i].assigned_tiles.bit(p.anchor.x, p.anchor.y)`. When a zone's `assigned_tiles` is undefined (pre-V1.2 fixture or parse failure), fall back to `nearestZoneOf(anchor, zones)` Voronoi for that placement. Sharing the assignment function between overlay + breakdown is the same MED-1 pattern as chunk-B's `shouldStampBadge`.
5. **Visual goldens cover both UI states** — overlay ON + overlay OFF. Without the OFF golden, a regression that made the overlay always-on would slip past.
6. **Treasure-demo fixture doesn't break existing tests** — minimal.json stays as it is. AC-DECO-8 / AC-BIOME-8 / smoke / blend regression all keep loading minimal.json.
7. **Bandcolor consistency (chunk-B MED-1 extended)** — the overlay color, the badge color, and the breakdown swatch ALL pull from `bandColor(pickValueBand(value, registry_ref?.value_band_thresholds))`. A 1-test assertion in zone-breakdown.test.ts pins this.
8. **Empty zones omitted from breakdown (LOW-1 fix)** — a zone with `pile_count === 0` is dropped from the breakdown table to keep the panel readable. The full zone list still shows in the existing "zones" details.

## Design review findings (self-review pass — pre-BUILD)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| **MED-1** | MED | Voronoi vs `assigned_tiles` inconsistency: overlay paints by `assigned_tiles` bitmap; breakdown buckets by Voronoi `nearestZoneOf`. A boundary placement is counted under Voronoi-zone A but visually painted in `assigned_tiles`-zone B — silent attribution mismatch | Both surfaces route through shared `zoneOfPlacement(anchor, zones)` that prefers `assigned_tiles.bit(...)` and falls back to Voronoi only when bitmap is unavailable. Same single-source-of-truth pattern as chunk-B's `shouldStampBadge` |
| **LOW-1** | LOW | Empty zones (no treasure) clutter the breakdown | Filter `pile_count === 0` rows out of the table |
| **LOW-2** | LOW | Continent-tier 65k tile fills at build time could spike to ~100ms | Document; accept; build-time only; future canvas-ImageData optimization out of scope |
| **LOW-3** | LOW | Tests should verify `showTreasureBands` × layer toggle independence (chunk-A LOW-4 pattern) | Add `viewer_store_layer_and_band_toggles_independent` test |
| **COSMETIC-1** | COSMETIC | "Treasure breakdown" placement in MetadataPanel could confuse vs existing "zones" details | Add a "treasure breakdown" summary label distinct from the bare "zones" — explicit subsection naming |

## Test plan

| Test | File | Verifies |
|---|---|---|
| `zone_breakdown_empty_view_yields_no_rows` | zone-breakdown.test.ts | Boundary |
| `zone_breakdown_view_with_no_treasures_yields_empty` | same | Filter on `kind === 'treasure'` works |
| `zone_breakdown_buckets_piles_by_nearest_zone` | same | Voronoi assignment |
| `zone_breakdown_sums_per_zone_value` | same | Aggregation |
| `zone_breakdown_sorts_desc_by_total_value` | same | Spotlight zones float to top |
| `zone_breakdown_ties_break_by_zone_id` | same | Determinism |
| `zone_breakdown_band_per_zone_uses_tier_0_max_value` | same | Band derivation matches chunk-B badge color rule |
| `zone_breakdown_respects_per_book_thresholds` | same | xianxia override applied via view.registry_ref |
| `viewer_store_show_treasure_bands_default_false` | viewer-store.test.ts | AC-VBT-5 default |
| `viewer_store_set_show_treasure_bands_flips_flag` | same | Action wires |
| `viewer_store_layer_and_band_toggles_independent` | same | No cross-coupling |
| `treasure-bands-visual-regression chromium — overlay ON` | e2e | Playwright golden |
| `treasure-bands-visual-regression chromium — overlay OFF (badges only)` | e2e | Playwright golden |

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| `assigned_tiles` parse failure (e.g., grid_size mismatch) | Skip that zone's overlay; render others. No crash |
| 65k fillRects at Continent tier slow down initial render | Build-time only (not per-frame); benchmark in VERIFY |
| Voronoi nearest-zone differs slightly from backend's `assigned_tiles` truth | Acceptable for visualization; document; breakdown uses Voronoi consistently |
| New `treasure-demo.json` template doesn't compile (wrong wire shape) | Use minimal.json's shape as template; tilemap-service rejects malformed JSON at parse so a syntax error fails the e2e visibly |
| Goldens flaky across platforms | Same per-platform pin + 2% tolerance + 30s timeout as chunk-C blend goldens |
| Per-book threshold changes mid-test | One-shot computation; not a real concern for V1 |
| Visual overlay competes with biome painting | alpha=0.18 reads as tint, not paint; default OFF |

## Ground-truth verification table

| Reference | File:line | Verified |
|---|---|---|
| `viewer-store.blendEnabled` toggle pattern | `frontend-game/src/store/viewer-store.ts:55-56` | YES |
| `LayerToggles` Polish subsection | `frontend-game/src/components/viewer/LayerToggles.tsx:56-71` | YES |
| `MetadataPanel` collapsible `<details>` pattern | `frontend-game/src/components/viewer/MetadataPanel.tsx:75-87` | YES (existing zones details) |
| `overlay-rt.ts` `OverlayRtHandle.setZoneCentersVisible` | `frontend-game/src/game/render/overlay-rt.ts:177-179` | YES |
| `parseTilemapView` produces `assigned_tiles: TileMask{bits:bigint[]}` | `frontend-game/src/api/tilemap-client.ts:36-61` | YES |
| `ZoneRuntime.assigned_tiles?: TileMask` | `frontend-game/src/types/tilemap.ts:143-150` | YES |
| `bandColor`/`pickValueBand`/`shouldStampBadge` | `frontend-game/src/game/render/treasure-badge.ts` | YES (chunk B) |
| `blend-visual-regression.spec.ts` golden harness | `frontend-game/e2e/blend-visual-regression.spec.ts` | YES (TMP-Q3 chunk C) |

## Out of scope

- Per-zone breakdown drill-down (clickable row → highlight zone)
- Animated overlay transitions (instant ON/OFF only)
- Multi-tier color mixing per zone (single max-tier color)
- Backend-side aggregation (everything derived on FE)
- L4 narration of zone breakdown (TMP_008 V2)
- 3D / cinematic zone overlay (V3)

## Known limitations

- **Single max-tier color per zone** — a zone with 3 tiers shows the highest band only. The badge layer + the inspector cover per-pile detail. Spec-level decision documented in `2026-05-30-value-band-treasures.md` §10.
- **Nearest-zone Voronoi mismatch** — `nearestZoneOf(p.anchor, zones)` may classify a placement differently from the backend's authoritative `assigned_tiles`-based zone assignment for tiles near a zone boundary. For chunk C this is OK: the visualization is approximate by design. If we ever need exact attribution, the backend would need to send `placement.zone_id` on the wire (deferred).
- **u8 saturation at tier 256+** — inherited from chunk A; same break-on-overflow behavior.
- **Goldens cross-platform** — Windows-x86_64 only on first commit; Linux CI rebaselines on first run.
