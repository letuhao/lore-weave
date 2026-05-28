# GEO — Terrain Pipeline (AS-BUILT reference)

> **Purpose:** a stage-by-stage map of the *current* Tectonic terrain
> algorithm so it can be intervened on **one part at a time**. Every stage
> lists its source location, what it does, and the knobs (with their values
> as of HEAD `8bb0884f`, branch `geo-generator-amaw`, 2026-05-22).
>
> **Status (2026-05-22):** the terrain-coherence pass is committed (flat
> plains + localized relief; smooth ocean; separated continents). PO will now
> intervene part by part. This doc is the intervention map.
>
> See also: design intent in
> [`docs/plans/2026-05-22-geo-terrain-coherence-spec.md`](../../plans/2026-05-22-geo-terrain-coherence-spec.md);
> high-level status in [`GEO_GENERATOR_PLAN.md`](GEO_GENERATOR_PLAN.md).

---

## 0 — Big picture

```
seed + CreativeSeed
   │
   ▼
mesh.rs        Fibonacci sphere → spherical Delaunay/Voronoi (cells, neighbors)
   │
   ▼
plates.rs      Voronoi plates → continental/oceanic → motion → boundary class
   │            → orogeny-uplift BFS    ⇒  base[], uplift[]
   ▼
terrain.rs     MACRO  = base + uplift            (sign splits land / ocean)
 (Tectonic)    RUGGED = f(macro altitude, fBm)   ∈ [0,1]
               LAND   = macro + ruggedness-gated relief
               OCEAN  = coast-distance depth curve + gated uplift
   │            → erosion (gated) → fixed-scale quantize to u16
   ▼
climate / hydrology / political / settlement / routes / culture / render
```

Two terrain modes (`TerrainMode`): **Tectonic** (default, this doc) and
**Profile** (legacy single-continent radial mask — uses `height_at` +
`apply_falloff`, *not* the stages below). All line refs are
[`crates/world-gen/src/terrain.rs`](../../../crates/world-gen/src/terrain.rs)
unless noted.

---

## Stage 1 — Plate macro: `base[]` + `uplift[]`

**Where:** [`plates.rs`](../../../crates/world-gen/src/plates.rs) → `plates::build()`;
consumed at `terrain.rs:158` (`macro_elev = base[i] + uplift[i]`).

**What:** the tectonic skeleton. `base` is the crust platform (signed, sea=0);
`uplift` is the distance-decayed orogeny field from a multi-source BFS over
plate boundaries. **Land/ocean is split purely by `macro_elev >= 0`**
(`terrain.rs:160`, `is_land_macro`).

**Knobs** (`plates.rs`):

| Const | Value | Effect |
|---|---|---|
| `CONT_BASE` | `0.10` | continental platform height (just above sea) |
| `OCEAN_BASE` | `-0.55` | oceanic crust floor |
| `FOLD_PEAK` | `0.85` | continent-collision range height (Himalaya/Andes) |
| `ARC_PEAK` | `0.55` | subduction continental-arc height |
| `ISLAND_ARC_PEAK` | `0.45` | oceanic island-arc height |
| `TRENCH_DEPTH` | `0.30` | subduction trench notch |
| `RIDGE_PEAK` | `0.20` | mid-ocean ridge |
| `RIFT_DEPTH` | `0.28` | continental rift trough |
| `FAULT_PEAK` | `0.05` | transform-fault relief (minor) |
| `DECAY_HOPS` | `4.0` | how far uplift bleeds inland from a boundary (BFS hops) |
| `PLATE_WARP_AMP` | `0.32` | plate-boundary domain warp (irregular coastlines) |

**Intervention notes:** continent *count / size* is set here (plate seeding +
`continental_fraction`). Mountain *strength* = the `*_PEAK` values. Lowering
`OCEAN_BASE` toward 0 raises sea floor (more shelf); raising `CONT_BASE`
floods less.

---

## Stage 2 — Ruggedness field `r ∈ [0,1]`

**Where:** `ruggedness()` (`terrain.rs:332`); called per land cell at
`terrain.rs:169`.

**What:** the control variable for Musgrave "statistics by altitude." **High
where macro elevation is high (mountains), ~0 on the coastal platform and
plains.** A low-freq fBm adds organic interior plateaus so ruggedness isn't a
pure function of altitude.

```
alt      = smoothstep(0.22, 0.62, macro_elev)         // 0 on platform, 1 on belts
fbm_r    = 0.5 + 0.5·fbm_3d(p·RUGGED_FREQ, …, 3)
interior = 0.28 · smoothstep(0.64,0.86,fbm_r) · smoothstep(0.16,0.30,macro_elev)
r        = clamp( max(alt, interior) · (0.6 + 0.4·fbm_r), 0, 1 )
```

**Knobs:** the two `alt` thresholds `0.22 / 0.62` (where relief begins / hits
full), the `interior` weight `0.28` + its thresholds, `RUGGED_FREQ = 2.2`.

**Intervention notes (this is the master dial for "how Earth-like the
hypsometry is"):** lower the `alt` lower-threshold (`0.22`) to bring back
**rolling uplands** between plains and peaks (currently hypsometry is ~98%
lowland — flatter than Earth's 62/23/6, a deliberate choice per PO's "too
bumpy" steer). Raising it makes plains even flatter. **Do NOT** reintroduce a
boundary-proximity term here — a continent/ocean coast *is* a plate boundary,
so proximity rings every coast with a thin "pen-stroke" ridge (the bug we just
removed).

---

## Stage 3 — Land relief (ruggedness-gated)

**Where:** `land_relief()` (`terrain.rs:350`); composed at `terrain.rs:182`
(`macro_elev[i] + land_relief(...)`).

**What:** the detail layer. `r≈0` → only a tiny whisper (flat plains); `r≈1`
→ full hills + ridged ranges (jagged). Domain warp amplitude is also scaled by
`r` (`warp_scaled()`), so plains stay un-warped/coherent while mountains get
turbulent ridgelines.

```
whisper = TEC_PLAIN_WEIGHT · fbm_3d(p·PLAIN_FREQ, …, 2)
if r < 1e-3: return whisper
detail  = TEC_HILL_WEIGHT·hills + TEC_MTN_WEIGHT·ridges   // ridges = ridged_fbm
return r·detail + (1-r)·whisper
```

**Knobs:**

| Const | Value | Effect |
|---|---|---|
| `TEC_PLAIN_WEIGHT` | `0.022` | plains undulation (keep small — flatness) |
| `PLAIN_FREQ` | `2.6` | plains undulation wavelength |
| `TEC_HILL_WEIGHT` | `0.22` | mid-freq hill amplitude in mountains |
| `TEC_MTN_WEIGHT` | `0.72` | ridged-range amplitude in mountains |
| `HILL_FREQ / MTN_FREQ` | `7.5 / 4.5` | hill / ridge wavelengths |
| `WARP_AMP` | `0.09` | max ridge warp (×`r`) |

**Intervention notes:** plains roughness = `TEC_PLAIN_WEIGHT`. Mountain
jaggedness = `TEC_MTN_WEIGHT` + `MTN_OCTAVES`. The plains/mountain *boundary
sharpness* is governed by Stage 2, not here.

---

## Stage 4 — Ocean depth (coast-distance curve)

**Where:** `coast_distance()` (`terrain.rs:398`, BFS) + `ocean_depth()`
(`terrain.rs:369`); composed at `terrain.rs:187`.

**What:** ocean elevation is **not** noise — it's a depth curve by BFS hops
from the coast: shallow **shelf** at the coast → ramps down to a deep,
near-flat **abyssal plain**. A faint ripple avoids dead-flat. Plate uplift
(ridges/arcs) is added on top **but gated by coast distance** so arcs surface
offshore in deep water instead of welding continents at the shelf.

```
t      = min(coast_dist / OCEAN_ABYSS_HOPS, 1)
depth  = OCEAN_SHELF + (OCEAN_ABYSS - OCEAN_SHELF)·smoothstep(0,1,t) + ripple
gate   = smoothstep(OCEAN_ARC_GATE_NEAR, OCEAN_ARC_GATE_FAR, coast_dist)   // for uplift>0
elev   = depth + (uplift>0 ? uplift·gate : uplift)
```

**Knobs:**

| Const | Value | Effect |
|---|---|---|
| `OCEAN_SHELF` | `-0.04` | coast/shelf depth (shallow) |
| `OCEAN_ABYSS` | `-0.58` | abyssal-plain depth |
| `OCEAN_ABYSS_HOPS` | `7.0` | shelf→abyss ramp width (BFS hops) |
| `OCEAN_RIPPLE_WEIGHT` | `0.02` | abyssal texture |
| `OCEAN_ARC_GATE_NEAR/FAR` | `1.0 / 4.0` | suppress arc uplift within NEAR hops; full beyond FAR |

**Intervention notes:** widen `OCEAN_ABYSS_HOPS` for broader shelves. The arc
gate (`NEAR/FAR`) is the **continent-welding guard** — if continents merge
again, raise `OCEAN_ARC_GATE_FAR`. Trenches keep their notch via negative
uplift (ungated).

---

## Stage 5 — Erosion (ruggedness-gated incision)

**Where:** [`erosion.rs`](../../../crates/world-gen/src/erosion.rs) →
`apply(elev, neighbors, land_fraction, strength, Some(&rugged))` at
`terrain.rs:195`. Incision `K` is multiplied per-cell by `rugged[c]`
(`erosion.rs:280`); **deposition is ungated** (highland sediment still fills
lowlands → reinforces flat valley floors).

**What:** two-phase stream-power — carve passes then settle passes — plus
hillslope diffusion. Mountains carve dendritic valleys; plains barely incise.

**Knobs:** `params(strength)` table (`erosion.rs:59`) — `carve_iters`,
`settle_iters`, `erodibility (K)`, `transport (Kc)`, `settle_rate`,
`diffusion`. Driven by `--erosion {none,light,moderate,heavy}` (default
moderate: 18 carve / 8 settle / K=3 / Kc=4 / settle 0.18 / diff 0.012).

**Intervention notes:** Profile mode passes `None` (ungated). To make plains
hold even flatter, lower `K`; to deepen valleys, raise `carve_iters`.

---

## Stage 6 — Quantize to `u16` (fixed scale)

**Where:** `quantize_fixed_scale()` (`terrain.rs:274`) at `terrain.rs:200`.

**What:** map signed elevation (sea=0) to `u16` with a **fixed** scale — sea
pinned at `SEA_FRAC`; land mapped by `e/LAND_FULL` into the upper band, ocean
by `|e|/OCEAN_FULL` into the lower band (both clamped). A *flat* world stays
green (no peaks to stretch into grey) — this is why we use a fixed scale, not
min-max normalize (squeezed land into top 20% — the "flattened" bug) or
percentile-stretch (inflated flat worlds into grey plateaus).

**Knobs:** `SEA_FRAC = 0.40` (waterline as a fraction of range), `LAND_FULL =
0.78` (signed elevation → white peak), `OCEAN_FULL = 0.62` (|depth| → abyss
colour).

**Intervention notes:** this is **colour mapping only** — it does not change
geometry, just how elevation bands map to the relief palette. Raise
`LAND_FULL` to push more land toward green/brown (peaks need higher elevation
to read white).

---

## What is NOT here yet (deferred)

- **Phase 3 — Köppen climate / biome colour.** The remaining all-green colour
  monotony is *climate*, not relief. Insolation + moisture + biome palette.
- **Rivers as visible features; lakes; full erosion-network realism.**
- **Mid-band rolling uplands** — a Stage-2 threshold tweak if PO wants
  Earth-like 62/23/6 hypsometry back.

---

## Verification harness (how to re-check after an edit)

```
# render + JSON at gigaplanet
cargo run --release -p world-gen -- generate --seed 7 --scale gigaplanet \
  --terrain-mode tectonic --relief-png out.png --out out.json

# metrics (ad-hoc python over out.json): hypsometric bands + mean local slope
# by elevation band (plains should be ~flat, mountains ~80-90x rougher) +
# ocean abyssal slope (smooth). See last session's /tmp/metric.py pattern.

cargo test --release -p world-gen      # 158 tests
cargo clippy --all-targets -p world-gen # clean
```

`content_hash` rebases on any geometry change (expected — determinism gate
re-baselines, not breaks).
