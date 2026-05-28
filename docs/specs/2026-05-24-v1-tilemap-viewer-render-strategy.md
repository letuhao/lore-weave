# V1 tilemap viewer — render strategy

> **Branch:** `mmo-rpg/zone-map-amaw`
> **Builds on:** [`2026-05-24-v1-tilemap-viewer-scope-expansion.md`](./2026-05-24-v1-tilemap-viewer-scope-expansion.md)
> **Status:** PROPOSED 2026-05-24 (awaiting PO sign-off)
> **Why this exists:** PO flagged that current implementation
> (individual `add.image` per tile) won't scale beyond Town tier
> (64²). Web game = **lightness is mandatory**. This spec pins the
> render architecture before any V2-render code lands.

## 1. Render goals

- **Render any tier** without frame drop: Town 64² · District 128² ·
  Country 192² · Continent 256² (max 65,536 tiles)
- **Web bundle ≤ 5 MB** total asset weight; JS bundle gzip stays
  within V0 budget (700 KB)
- **First paint < 1 s** after `TilemapView` settles
- **60 FPS pan + zoom** at all tiers
- **Tile-precision input** (click-to-walk + tile-inspector) preserved
- **Re-render on seed change < 300 ms** (excluding backend time)

## 2. Three-strategy stack

PO directive: use **all three** strategies. Each layer of `TilemapView`
gets the strategy that fits its data shape.

### Strategy A — `TilemapGPULayer` (Phaser 4 native, single-quad GPU shader)

Used for: **foundation layer** (`terrain_layer`).

**Why:** Phaser 4 ships `TilemapGPULayer extends TilemapLayerBase`
which renders the entire tilemap as a single GL quad. Tile data is
encoded in a `WebGLTexture` (`layerDataTexture`) where each texel
stores the tile index in a 32-bit value (28-bit index + 3 flag
bits). The shader samples the tileset texture per pixel. Result:
**O(1) draw calls regardless of tile count.**

This is the orthographic-only path that DEFERRED #031 noted —
explicitly applicable to us since the camera pivoted to top-down.

**Setup:**
```ts
// 1. Build a tileset: stitch 10 algorithm-foundation tiles into one
//    256-px-tall × 2560-px-wide PNG strip (or atlas).
const map = scene.make.tilemap({
  tileWidth: 64,        // TILE_PX
  tileHeight: 64,
  width: gridW,         // from TilemapView.grid_size
  height: gridH,
});
const tileset = map.addTilesetImage('terrain-tileset', null, 64, 64);
const layer = new Phaser.Tilemaps.TilemapGPULayer(scene, map, 0, tileset);

// 2. Fill from TilemapView.terrain_layer (flat u8 array)
for (let y = 0; y < gridH; y++) {
  for (let x = 0; x < gridW; x++) {
    map.putTileAt(view.terrain_layer[y*gridW + x] - 1, x, y);  // u8 1-10 → tile index 0-9
  }
}
layer.generateLayerDataTexture();  // re-bake GPU texture
scene.add.existing(layer);
```

**Win:** Continent 65,536 tiles → 1 draw call → ~constant render time.

### Strategy B — viewport culling via `Container`

Used for: **L4 object sprites** (props with high count: 88 town → ~5,500
continent).

**Why:** Each `object_placements[]` entry is a single-instance sprite
(not repeated). At Continent scale, 5,500 individual sprites would
hit Phaser's draw-call ceiling. Solution: group sprites into chunks,
toggle chunk visibility based on camera viewport intersection.

**Setup:**
```ts
const CHUNK_TILES = 16;  // each chunk = 16×16 tiles
const chunks = new Map<string, Phaser.GameObjects.Container>();

for (const placement of view.object_placements) {
  const cx = Math.floor(placement.anchor.x / CHUNK_TILES);
  const cy = Math.floor(placement.anchor.y / CHUNK_TILES);
  const key = `${cx},${cy}`;
  let c = chunks.get(key);
  if (!c) { c = scene.add.container(); chunks.set(key, c); }
  c.add(buildSpriteFor(placement));
}

// Per-frame (or on camera move): toggle .visible per chunk
scene.events.on(Phaser.Scenes.Events.UPDATE, () => {
  const cam = scene.cameras.main;
  const view = cam.worldView;  // rect in world coords
  for (const [key, c] of chunks) {
    const [cx, cy] = key.split(',').map(Number);
    const chunkX = cx * CHUNK_TILES * TILE_PX;
    const chunkY = cy * CHUNK_TILES * TILE_PX;
    const chunkSize = CHUNK_TILES * TILE_PX;
    c.visible = view.intersects({
      x: chunkX, y: chunkY,
      width: chunkSize, height: chunkSize,
    });
  }
});
```

**Win:** At any zoom, only ~4-9 chunks visible → ~50-500 sprites max
rendered (down from 5,500 at Continent).

### Strategy C — `RenderTexture` pre-bake (single-quad blit)

Used for: **L1 roads · L2 rivers · L5 zone boundaries**.

**Why:** Polylines drawn via `Graphics.lineStyle + lineTo` are
ONE draw call per stroke. With 4 roads + 4 rivers + 93 crossings +
5+ zone outlines, that's ~100 draw calls per frame. Bake them all
into a single `RenderTexture` once per tilemap fetch, then blit the
texture as a single quad each frame.

**Setup:**
```ts
const rt = scene.add.renderTexture(0, 0, gridW * TILE_PX, gridH * TILE_PX);

// Draw roads
const g = scene.add.graphics();
g.lineStyle(6, 0x8a6e4b, 0.85);
for (const seg of view.road_segments) {
  g.beginPath();
  for (const wp of seg.waypoints) {
    const sx = wp.x * TILE_PX + TILE_PX/2;
    const sy = wp.y * TILE_PX + TILE_PX/2;
    g.lineTo(sx, sy);
  }
  g.strokePath();
}
rt.draw(g);
g.destroy();

// Draw rivers + crossings similarly, then zone outlines.
// One RenderTexture, drawn once, blitted every frame.
```

**Win:** ~100 draw calls per frame → 1 quad. Re-bake only when
`useZoneTilemap` settles new data.

### Strategy D (4th, additive) — Level Of Detail (LOD) by zoom

Used for: **all sprite layers** + visibility scaling.

**Why:** Even with chunked culling, rendering Tier-S/XS sprites at
fit-zoom (whole Continent on screen) is wasteful — they'd be 2-3 px
visual size, indistinguishable. Skip them at low zoom.

| Zoom range | Foundation | Roads/rivers | Tier-XL/L | Tier-M | Tier-S | Tier-XS | Markers | Player |
|---|---|---|---|---|---|---|---|---|
| ≥ 1.0 (detail) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0.5–1.0 (mid) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 0.25–0.5 (zoomed-out) | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ |
| 0.1–0.25 (overview) | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ |
| < 0.1 (continent) | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |

Implementation: subscribe to camera zoom change, set
`chunks.get(...).visible = false` per-tier at threshold. Player
always visible (single sprite, cheap).

## 3. Per-layer render plan (combined strategies)

| Layer | Strategy | Re-bake trigger | Per-frame cost |
|---|---|---|---|
| L0 Foundation `terrain_layer` | **A — TilemapGPULayer** | New `TilemapView` | 1 draw call |
| L1 Roads `road_segments` | **C — RenderTexture (shared)** | New `TilemapView` | 1 draw call (shared with L2/L5) |
| L2 Rivers `river_segments.tiles` | **C — RenderTexture (shared)** | New `TilemapView` | (shared above) |
| L2.5 River crossings (`bridge` / `ford`) | C — sprite drawn into RT | New `TilemapView` | (shared above) |
| L4 Object placements | **B — Container chunking + D LOD** | New `TilemapView` | ~50-500 draw calls (visible chunks only) |
| L5 Zone boundaries (debug toggle) | **C — RenderTexture (shared)** | New `TilemapView` | (shared above) |
| L6 Zone center markers (debug toggle) | Simple sprites + D LOD | New `TilemapView` | 5-256 sprites toggleable |
| L7 Player | Single sprite | Never | 1 draw call |

**Total worst-case (Continent + all toggles on):**
- L0: 1 draw call (GPU shader)
- L1+L2+L2.5+L5: 1 draw call (shared RT blit)
- L4: ~500 draw calls (chunked, LOD'd)
- L6: 0-256 sprites (toggle off by default; on = mostly culled)
- L7: 1 draw call

→ **~500 GL draw calls Continent worst case**, down from **~70,000**
naïve (65k tiles + 5,500 props + polylines per-frame). Well within
WebGL2 budget (typically 1,000-3,000 draw calls/frame).

## 4. Asset optimization (web game = lightness)

### 4.1 WebP encoding (lossy, q=85)

All non-foundation prop PNGs encoded as WebP @ quality 85:
- Browser support: Chrome 32+, Firefox 65+, Safari 14+, Edge 18+
- Phaser 4 `load.image('key', 'path.webp')` works identically to PNG
- Size reduction: ~50-70% vs PNG

**Bundle estimate with WebP:**

| Tier | Count | Per-WebP | Subtotal |
|---|---|---|---|
| Tier-XL | 4 | ~150 KB | 600 KB |
| Tier-L | 4 | ~65 KB | 260 KB |
| Tier-M | 3 | ~35 KB | 105 KB |
| Tier-S | 4 | ~25 KB | 100 KB |
| Tier-XS | 2 | ~15 KB | 30 KB |
| Tier-Marker | 6 | ~5 KB (programmatic, PNG) | 30 KB |
| Player | 1 | ~30 KB | 30 KB |
| Foundation tileset (10 tiles → 1 strip) | 1 | ~250 KB | 250 KB |

**Total ≈ 1.4 MB asset bundle** (was 2.7 MB at PNG). Together with
JS bundle ~485 KB gzip = **< 2 MB total first-load**.

### 4.2 Lazy loading

Only load what's used. First-paint stage:
1. **Critical** (preload before scene boot): foundation tileset +
   player + Tier-Marker (~350 KB)
2. **On-demand** (after first `TilemapView` settles, look at
   placements + lazy-load needed tiers): Tier-XL/L/M/S/XS PNGs as
   needed

Phaser 4 supports runtime image loading via `scene.load.image()` +
`scene.load.start()` + completion callback. The scene can render
without a tier's sprites first (using a placeholder coloured rect),
then swap to real sprite when loaded.

### 4.3 Texture atlas (foundation only)

Foundation 10 tiles → 1 PNG strip (10 × 256 = 2560 px wide × 256 px
tall). Phaser uses one tileset texture for all 10 — no extra
overhead. Atlas is generated by `gen-foundation-tiles.py` (modify to
output strip instead of 10 separate files).

For props: each prop is a unique image; atlas per-tier OPTIONAL —
small wins; defer to V2 if needed.

## 5. Performance targets

Verified at each batch checkpoint.

| Metric | Target | How to verify |
|---|---|---|
| First paint after `TilemapView` settles | ≤ 1 s | Chrome DevTools Performance tab; measure `tilemap-updated` → first frame |
| FPS at Town (64²) | 60 | Phaser FPS counter; pan camera 5 s, no drop |
| FPS at Continent (256²) | ≥ 30 sustained | Same; pan + zoom 10 s |
| Re-render on seed change | ≤ 300 ms (excl. backend) | Measure `tilemap-updated` → second-frame |
| Asset bundle weight | ≤ 1.5 MB | `du -sh frontend-game/public/assets/` |
| JS bundle gzip | ≤ 700 KB | `check:bundle-size` script |
| Memory at Continent + all toggles | ≤ 200 MB | Chrome Task Manager |

## 6. Implementation batches (replaces prior Step A–L plan)

### Batch 2.0 — Foundation refactor (~2 h)

Migrate foundation L0 from per-tile sprites → `TilemapGPULayer`.
Prerequisite for everything else.

| Step | Action |
|---|---|
| 1 | Modify `gen-foundation-tiles.py` → output 1 stitched `terrain-tileset.png` (2560×256 strip) in addition to (or replacing) 10 individual files |
| 2 | Update `PreloaderScene.ts` to load `terrain-tileset.png` instead of 10 individual `terrain-*.png` |
| 3 | Update `WorldScene.renderTilemap()` → build `Tilemap` + `TilemapGPULayer`, fill via `putTileAt` + `generateLayerDataTexture` |
| 4 | Verify: town 64² render identical; FPS at Town stays 60 |
| 5 | Verify: Continent 256² renders without frame drop (FPS ≥ 30) |
| 6 | Tests: replace existing L0 tile-render tests (if any) with TilemapGPULayer-based asserts |

### Batch 2.1 — Sprite bundle + L4 chunked rendering (~3 h)

Add L4 object_placements with Strategy B + D.

| Step | Action |
|---|---|
| 1 | Write `frontend-game/scripts/gen-prop-bundle.py` — copy + downsample 16 HoMM3 sources per tier table; draw 5 programmatic markers; encode all as WebP q=85 |
| 2 | Generate `frontend-game/public/assets/sprites/{xl,l,m,s,xs,marker,player}/*.webp` |
| 3 | Update `PreloaderScene` to lazy-load tiers (critical on boot + on-demand for tiers needed by first render) |
| 4 | New `frontend-game/src/game/render/object-overlay.ts` — `Container` per chunk, `(kind, biome_object_type) → texture key + tier` mapping |
| 5 | LOD: subscribe to camera zoom, toggle chunk-tier visibility |
| 6 | Update `WorldScene` render order to call object-overlay after foundation |
| 7 | Tests: `object-overlay.test.ts` — kind/subtype → tier mapping + chunk membership |

### Batch 2.2 — Polyline + crossings + zone overlays (~2 h)

Add L1, L2, L2.5, L5, L6 via Strategy C.

| Step | Action |
|---|---|
| 1 | New `frontend-game/src/game/render/overlay-rt.ts` — single `RenderTexture` baker, called on `tilemap-updated`. Draws roads, rivers, crossings, zone boundaries into the RT |
| 2 | Crossing icons: programmatic bridge (golden plank) + ford (light blue stones), drawn at `crossings[].at` |
| 3 | Zone boundary: 8-neighbour boundary detection on `zones[].assigned_tiles` bitmap → polyline outline draws |
| 4 | Zone center marker (L6): simple `Text` + `×` sprite at `zone.center_position` (toggled by viewer-store) |
| 5 | Tests: `overlay-rt.test.ts` — given fixture TilemapView, assert RT contains expected non-transparent pixels at road/river tile centres |

### Batch 2.3 — UX panels + LOD UI + verify (~2.5 h)

Add LayerToggles, TileInspector, MetadataPanel + viewer-store + final verify.

| Step | Action |
|---|---|
| 1 | `src/store/viewer-store.ts` — Zustand: `{ visibleLayers, selectedTile, inspectorOpen, lodZoom }` |
| 2 | `src/components/viewer/LayerToggles.tsx` — 7 checkboxes (L0–L6); changes update `viewer-store` |
| 3 | `src/components/viewer/TileInspector.tsx` — pointerdown intercept (modifier key or "inspector mode" toggle), side panel with tile metadata |
| 4 | `src/components/viewer/MetadataPanel.tsx` — `template_id`, `seed`, `tier`, `grid_size`, `generation_source`, per-zone summary |
| 5 | LOD threshold tuning — test pan + zoom at all 4 tiers (Town / District / Country / Continent) |
| 6 | Performance verify against §5 targets — Chrome DevTools Performance + FPS counter |
| 7 | Browser smoke screenshots: Town render, Continent render, layer toggles, inspector open |

**Total: ~9.5 h.** Split into 4 sessions OR 1-2 long sessions.

## 7. Open decisions for PO

1. **TilemapGPULayer vs standard TilemapLayer** — GPU variant is faster but newer (Phaser 4 only, may have bugs). Standard fallback if issues. **Recommend GPU; fallback ready.**
2. **WebP encoding quality** — q=85 is safe; q=80 saves another 10-15% with mild artifacts. **Recommend q=85.**
3. **Lazy-load granularity** — per-tier (5-6 batches) or per-sprite (21 individual). Per-tier simpler. **Recommend per-tier.**
4. **LOD thresholds** — table in §2 D is opinionated. Tunable after first smoke. **Defer tuning to verify step.**
5. **Texture atlas for props** — V1 skip (lazy-loaded per-tier is enough); V2 if memory budget tight.

## 8. DEFERRED follow-ups

- **#039 (NEW)** — V2 prop pipeline replaces HoMM3 Flux1d placeholders
  with license-clean per-book gen (already covered by #037, this is
  refined scope: applies specifically to the tier table sources)
- **#040 (NEW)** — TilemapGPULayer ortho-only confirmed (was
  #031 LOW DEFERRED V0). Reframe: GPU layer IS the V1 default for
  top-down (since this branch pivoted). #031 can be cleared as "no
  longer relevant; ortho-only is exactly what we ship now".
- Drag-to-pan camera — small follow-up
- Mouse-pinch zoom for touch — V2 polish
