# GEO World-Tier Phase 2 — Plate-Tectonic Multi-Continent

> **Spec:** [`GEO_WORLD_TIER_REDESIGN.md`](../03_planning/LLM_MMO_RPG/GEO_WORLD_TIER_REDESIGN.md) §5.
> **Phase 1** (sphere mesh + 3D terrain + projections) is complete — commits
> `1433f045` / `0a5387b1` / `4f10b557`.
>
> **Goal:** replace the single-continent radial mask (`apply_falloff` +
> `enforce_coherence`) with a **plate-tectonic model** — an LLM/seed-chosen
> number of plates over the sphere, each oceanic or continental, with motion
> vectors whose boundaries place mountains / rifts / trenches / arcs. The
> default world becomes a genuine planet: several continents in real ocean
> basins. The legacy single-continent path stays available as `TerrainMode::Profile`.
>
> **Task size:** XL. content_hash rebases (new terrain algorithm + new hashed
> WorldMap fields). PO-approved.

---

## PO decisions (2026-05-21)

1. **`TerrainMode` enum** on `CreativeSeed` — `Tectonic` (default,
   multi-continent) vs `Profile` (legacy `CoastlineProfile`). `enforce_coherence`
   runs only in `Profile` mode.
2. **New `CreativeSeed` fields** — `plate_count: u8` (default 8, clamp 3..=24)
   + `continental_fraction: f32` (default 0.4). CLI + LLM-author settable.
3. **Expose the plate layer** in `WorldMap` — `plate_of` (per-cell) + `plates`
   (kind + motion) + `plate_boundaries` (plate pairs + boundary kind). All
   hashed.

---

## 1 — The model (`plates.rs`, NEW)

`plates::build(seed, plate_count, continental_fraction, centers, neighbors) -> Plates`
where `Plates { plate_of: Vec<u32>, plates: Vec<Plate>, boundaries: Vec<PlateBoundary>, uplift: Vec<f32> }`.

### 1a — Seed plates + assign cells
- Sample `N = plate_count` plate seed points on the sphere via the RNG
  (`Rng::for_stage(seed, b"plates")` → random unit vectors; reject-sample or
  normalize). Irregular (not Fibonacci) so plate shapes look natural.
- `plate_of[cell]` = nearest plate seed by great-circle (max dot). A spherical
  Voronoi over the seeds — the same nearest-by-dot pattern the renderer uses.

### 1b — Plate kind
- `continental = round(N * continental_fraction)` plates are `Continental`,
  the rest `Oceanic`. Pick which by ascending plate id (deterministic) after a
  seeded shuffle so it's not always plates 0..k.
- Continental plate → base elevation `CONT_BASE` (above sea); oceanic →
  `OCEAN_BASE` (below sea).

### 1c — Plate motion
- Each plate gets a random **tangent** unit motion vector: draw a random 3D
  vector, project onto the plate-seed tangent plane, normalize. Deterministic
  via the plate RNG stream.

### 1d — Boundary classification
- A cell is a **boundary cell** if any neighbour belongs to a different plate.
- For each boundary cell, find the dominant neighbouring plate; classify by the
  relative motion of the two plates resolved along the boundary normal
  (direction between the two plate seeds, or cell→neighbour):
  - **Convergent** (closing): both Continental → `FoldMountain`; one Oceanic →
    `Subduction` (trench + arc); both Oceanic → `IslandArc`.
  - **Divergent** (opening): Oceanic → `Ridge`; Continental → `Rift`.
  - **Transform** (shear): `Fault`.
- `PlateBoundary { plate_a, plate_b, kind }` collected per unordered plate pair
  (the dominant kind across that pair's shared edge, by cell count → ties to
  lower kind tag). `boundaries` is sorted by `(plate_a, plate_b)`.

### 1e — Orogeny uplift field
- Multi-source BFS from all boundary cells over the mesh graph → per-cell
  `(dist, boundary_kind)` (the nearest boundary + how far, in hops).
- `uplift[cell]` = a kind-specific signed profile that decays with `dist`:
  - `FoldMountain` → strong positive (a broad belt).
  - `Subduction` → positive arc on the continental side + a negative trench
    notch on the oceanic side (sign by the cell's own plate kind).
  - `IslandArc` → moderate positive ridge.
  - `Ridge` → mild positive (mid-ocean ridge bump, stays subsea).
  - `Rift` → negative (a valley) flanked by mild shoulders.
  - `Fault` → near-zero (slight roughening).
- The decay length scales with mesh resolution (≈ a few cells).

---

## 2 — Terrain integration (`terrain.rs`)

`terrain::build` gains a `TerrainMode` parameter and branches:

### Tectonic mode (default)
1. `plates::build(...)` → plate base + uplift.
2. Per cell: `elev = plate_base(plate kind) + uplift[cell] + texture`, where
   `texture` is the existing 3D fBm continent/ridge/hill **detail** from
   `height_at` — but with its broad continent term **dampened** (the plates now
   own the macro structure; fBm is medium/fine relief). Domain warp still
   applies for organic edges.
3. **No `apply_falloff`** (plates own land placement). **No `enforce_coherence`**
   (multi-continent is the goal).
4. Erosion (`erosion::apply`) runs as today on the combined f32 field.
5. `choose_sea_level`: pick the level that yields `continental_fraction`-ish
   land **without** the largest-component constraint (plain percentile — many
   continents are expected). Reuse `pick_sea_level`.

### Profile mode (legacy)
- Exactly today's path: `height_at` + `apply_falloff(profile)` +
  `enforce_coherence(profile)` + `choose_sea_level(profile)`. Untouched.

### Refactor note
- `height_at` splits its continent term behind a `macro_weight` so Tectonic can
  dampen it (plates provide the macro) while Profile keeps it at 1.0.

---

## 3 — `CreativeSeed` + enums (`creative_seed.rs`)

```rust
pub enum TerrainMode { Tectonic, Profile }      // #[default] = Tectonic
pub enum PlateKind  { Oceanic, Continental }    // + tag() for hashing
pub enum BoundaryKind { Interior, FoldMountain, Subduction, IslandArc, Ridge, Rift, Fault } // + tag()

pub struct CreativeSeed {
    // … existing fields …
    #[serde(default)] pub terrain_mode: TerrainMode,
    #[serde(default = "default_plate_count")]      pub plate_count: u8,        // 8
    #[serde(default = "default_continental_frac")] pub continental_fraction: f32, // 0.4
}
```
- `plate_count` clamped to `3..=24` at use. `continental_fraction` clamped to
  `0.1..=0.9`.
- A pre-Phase-2 config JSON (no `terrain_mode`) defaults to **Tectonic** — the
  world-tier default is a planet. Documented; `content_hash` shifts.

---

## 4 — `WorldMap` exposure (`world_map.rs`)

```rust
pub struct Plate { pub id: u32, pub kind: PlateKind, pub motion: [f32; 3], pub seed_cell: u32 }
pub struct PlateBoundary { pub plate_a: u32, pub plate_b: u32, pub kind: BoundaryKind }

pub struct WorldMap {
    // … existing …
    pub plate_of: Vec<u32>,          // per-cell, parallel to cells
    pub plates: Vec<Plate>,
    pub plate_boundaries: Vec<PlateBoundary>,
}
```
- Empty (`plate_of` all `u32::MAX`, `plates`/`plate_boundaries` empty) in
  `Profile` mode so the field set is uniform.
- `compute_hash` extended: `plate_of` ids; each `Plate` (id, kind tag, motion
  bits, seed_cell); each `PlateBoundary` (plate_a, plate_b, kind tag). The
  `compute_hash_covers_every_field` serde test tampers each new field.

---

## 5 — Render (`render.rs`)

NEW `plate_image` (+ CLI `--plate-png`): cells tinted by `plate_of`, with
continental plates warm and oceanic cool, boundary cells outlined by kind
colour, hillshaded by the relief field. A showcase that makes the tectonic
structure legible. Projection-aware like the others.

---

## 6 — BUILD order

| Step | Scope |
|---|---|
| **B1** | `plates.rs` — seed + Voronoi + kind + motion + boundary classify + uplift field. Unit-tested in isolation (deterministic; every cell assigned; ≥2 plates of each kind when fraction allows; boundary cells flagged). |
| **B2** | enums in `creative_seed.rs` (`TerrainMode`/`PlateKind`/`BoundaryKind` + the 2 fields + defaults). |
| **B3** | `terrain.rs` — `TerrainMode` branch; Tectonic path (plate base + uplift + dampened fBm; no falloff/coherence); Profile path unchanged. `height_at` `macro_weight`. |
| **B4** | `world_map.rs` — `Plate`/`PlateBoundary` structs + 3 fields + `compute_hash` + lib.rs wiring (thread plates through `generate`). |
| **B5** | `render.rs` `plate_image` + CLI `--terrain-mode`/`--plate-count`/`--continental-fraction`/`--plate-png` in `main.rs`; LLM author schema (`author.rs`) gains the 3 fields. |
| **B6** | tests + content_hash rebaseline + visual smoke (multi-continent globe). |

---

## 7 — VERIFY criteria

- Determinism: same seed+config → byte-identical map (lib + integration).
- `plates::build`: every cell assigned a plate; plate count == requested;
  continental count == round(N·fraction); ≥1 boundary cell on a multi-plate map.
- **Multi-continent**: a Tectonic map has **>1 land component** (the whole
  point — assert ≥2 for a representative seed/config).
- Profile mode unchanged: a `Profile` map still has exactly 1 land component
  (enforce_coherence still runs) and byte-matches… (not byte — algorithm
  refactor may shift; assert structural: 1 component).
- `compute_hash_covers_every_field` extended for the 3 new fields.
- Boundary placement sanity: cells near a `FoldMountain` boundary have higher
  mean elevation than plate interiors.
- Visual smoke: render a Tectonic globe — confirm several distinct continents
  + mountain belts along convergent boundaries.
- clippy clean.

---

## 8 — Risks

| Risk | Mitigation |
|---|---|
| Plates produce all-ocean or all-land worlds | `continental_fraction` + `choose_sea_level` percentile; test asserts both land and ocean exist. |
| Multi-continent breaks downstream (political/settlement assume connectivity) | They already handle multiple land components (`pathfind::land_components` + per-component quotas from Phase 3); verify all_layers_populated still passes. |
| content_hash rebaseline churn | Expected + documented; rebaseline after structural tests pass; visual smoke before baking. |
| Boundary classification determinism | All tie-breaks by ascending id / kind tag; BFS over sorted neighbours. |
| Orogeny tuning ugly | Visual smoke + iterate constants on a fixture seed. |

---

## 9 — Out of scope (later phases)

- Köppen climate (Phase 3) — climate still uses the Phase-1 lat model.
- Two-tier scale (Phase 5).
- Fantasy archetypes / anomaly regions (Phase 6).
- Realistic plate *evolution* over time (single static snapshot only).
- Hotspots / mantle plumes (could be a later enhancement).
