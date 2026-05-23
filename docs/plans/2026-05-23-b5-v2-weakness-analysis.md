# B5 v2 — Weakness Analysis & Tuning Roadmap

> **Status:** LOCKED 2026-05-24 (PO decisions on the 4 design forks at the end
> of this doc). Companion to
> [`2026-05-23-climate-simulation-research.md`](2026-05-23-climate-simulation-research.md)
> §10 (the v2 shipped plan). This doc covers **what was wrong with v2's
> output** after visual smoke + how each issue is to be fixed without adding
> new layers / scope.
>
> **NOT a v3 doc** — v3 (OceanCurrent), v4 (Orographic), v5 (Seasonal Köppen)
> are explicitly out of scope. This is the **stop-the-line tuning pass** so v2
> produces presentable maps with defaults before any new layer ships.

---

## 1 — Context

B5 v2 (commit `02289ebe`) shipped the 5-layer hierarchical climate per
[`2026-05-23-climate-simulation-research.md`](2026-05-23-climate-simulation-research.md)
§10. Algorithm is correct (171 tests pass, hash-pinned regression lock, full
12-phase + /review-impl workflow). 9 visual smoke samples generated for self-
eval:

| Sample | Rating |
|---|---|
| `eq_seed7` (Equatorial, default) | 6/10 |
| `eq_seed13` | **3/10** — monotone sand |
| `eq_seed23` | 7/10 — best baseline |
| `eq_seed42` | **2/10** — monotone grass |
| `seed7_north` | **8/10** — best lat gradient |
| `seed7_south` | 8/10 — mirror confirmation |
| `scenario_snowball` | 5/10 |
| `scenario_hothouse` | **8/10** — most aesthetic |
| `scenario_desert` | 4/10 |

**Mean ~5.7/10.** Algorithm correct, aesthetics not production-quality with
defaults. PO directive: **stop new features; decompose every weakness; fix
each one before any v3 layer.**

---

## 2 — Methodology

Each weakness below is decomposed into:

- **Symptom** — what the visual sample shows that is wrong
- **Root cause** — the line(s) of code or default value(s) responsible
- **Solution options** — 2-4 alternatives with tradeoffs
- **Pick** — the chosen approach
- **Complexity** — XS (<30 LOC, 1h) · S (<150 LOC, 2-4h) · M (<500 LOC, 1-2 days)
- **Priority** — 1 (must fix) · 2 (high) · 3 (medium) · 4 (cosmetic)

Some "natural numbers" (e.g. `t_pole` default value) are NOT chosen by
prediction — they are chosen by **empirical calibration sweep** (§6).

---

## 3 — The 14 weaknesses

### P1 — Critical (defaults are unusable)

#### W1 — Seed monotony

**Symptom**: 2 of 4 baseline seeds (`eq_seed13`, `eq_seed42`) produce
monocolor worlds. `eq_seed13` is uniformly HotDesert sand; `eq_seed42` is
uniformly TempGrassland. Climate variety lost.

**Root cause**:
[`flatworld::generate`](../../crates/world-gen/src/flatworld.rs)
`place_centers` constrains `min_sep × pitch` (inter-plate distance) but **does
not constrain the lat distribution of plate centers**. With `plate_count = 7`
on a 640-tall map, plates cluster naturally — random samples often have all
plates within a 200-px y range → same insolation + circulation values
everywhere → monoculture.

**Solution options**:
- **A** (XS): bump `plate_count` default 7 → N (TBD via §6.2 sweep).
  Brute-force; each plate gets smaller → may exacerbate W4 (beach dominance).
- **B** (S, **PICK**): **stratified y-placement**. Divide map into 4 horizontal
  strips by lat; require ≥1 plate per strip via rejection sampling during
  center placement. Deterministic; doesn't break existing tests.
- **C** (M): climate-diversity-aware seed rejection (generate map → compute
  biome entropy → reject if low → retry). Breaks determinism guarantee if
  threshold changes. **Reject.**

**Pick**: B + small bump in `plate_count` default (number from §6.2 sweep).

**Complexity**: S. **Priority**: 1.

---

#### W3 — Polar Ice over-fire

**Symptom**: With defaults, 3-4 polar plates per world are uniformly Ice
(white). `eq_seed7` and `seed7_north` both show this. Real Earth has polar
TUNDRA majority with Ice only on actual ice caps / glaciers.

**Root cause**: `t_pole = -25` + zone-level lapse (`zone_lapse = 50 ×
(zone_elev - sea_level)`) on tectonically-uplifted polar plates → zone
`temp_mean` falls well below `ice_temp = -10`. Any pixel with `delta ≥
peak_lapse_min_delta (0.05)` then triggers the lapse override → Ice. Polar
mountain class zones have most pixels above the gate → uniform Ice.

The `peak_lapse_min_delta` gate (introduced during /review-impl) prevents the
flat polar plain case but doesn't prevent the polar-mountain case.

**Solution options**:
- **A** (XS): raise `t_pole` default (from -25 to TBD via §6.1 sweep). Less
  realistic for "Earth-like" worlds but reduces wasteland coverage.
- **B** (XS): lower `ice_temp` from -10 to -20. Polar zones at -25 still
  classify Tundra (since -25 > -20 fails the ice threshold) until lapse
  kicks in. Pure threshold shift.
- **C** (S, **PICK** with A): **precip-gated Ice**. Real ice caps form from
  snow *accumulation*. Add: `Ice` only if `temp < ice_temp` AND
  (`precip > ICE_PRECIP_MIN` OR `delta > peak_gate × ICE_PEAK_MULT`).
  Polar dry plain (cold + low precip + flat) → Tundra. Polar wet mountain
  → Ice cap. Polar dry mountain → Tundra unless the peak is truly tall.
- **D** (S): strict tier hierarchy — pixel-lapse can only push down ONE tier
  (e.g. zone Tundra → pixel Tundra; pixel-lapse cannot reach Ice from a
  Tundra zone). Cleaner semantic but loses snow caps on cold mountains.
  **Reject.**

**Pick**: A (default tuning via §6.1) + C (precip-gated Ice). The
combination addresses both "polar default too cold" and "ice cap requires
moisture" — independently useful, both ~XS each.

**Complexity**: S total. **Priority**: 1.

---

#### W14 — Continentality reach scales by map, not plate

**Symptom**: `continentality_reach = 200 px` is calibrated for `1024×640` with
7 plates (~250 px wide). If W1's fix bumps `plate_count` to 12+, plates
shrink (~150 px wide); reach saturates near plate center → entire interior
gets full attenuation → uniform dry interior. The fix for W1 will reveal
this issue.

**Root cause**:
[`WorldClimateParams::scaled_for`](../../crates/world-gen/src/flat_climate.rs)
uses `short_side / 640`. Correct when `short_side` changes but `plate_count`
constant; incorrect when `plate_count` changes.

**Solution options**:
- **A** (S, **PICK**): scale `reach` by **mean plate radius**, not map
  dimension. Compute at climate-init: `mean_radius = sqrt(map_area / plate_count) × 0.5`.
  Set `reach = mean_radius × CONTINENTALITY_REACH_FRAC` (default 0.4 →
  reach saturates ~40% of plate radius from coast, leaving inland 60% as
  fully-continental). Single new constant `CONTINENTALITY_REACH_FRAC`
  replaces the absolute `reach` default.
- **B** (M): per-plate reach (each plate computes its own from its actual
  radius). More accurate for irregular plate sizes; over-engineered.
- **C** (XS): keep current default + force user to set reach via CLI when
  changing plate count. Pushes responsibility to author. **Reject** — bad UX.

**Pick**: A.

**Complexity**: S. **Priority**: 1 (compounds with W1).

---

### P2 — High (chronic artifacts)

#### W2 — Continentality ring artifact

**Symptom**: Every large plate shows concentric rings: wet rim →
intermediate band → dry interior. The pattern is overly geometric, not
Earth-like (real coast-to-interior gradients are anisotropic, shaped by
wind).

**Root cause**: `cont = coast_dist / reach` uses **isotropic Euclidean
distance** via `edge_dist_from_sea` BFS. On a convex plate shape, the BFS
distance field has concentric contour lines → precip lerps linearly along
those contours → biome boundaries follow the contour.

**Solution options**:
- **A** (XS, **PICK for v2.1**): **noise overlay**. `cont = base_cont + AMP ×
  perlin(sx × FREQ, sy × FREQ)`. AMP ~0.15, FREQ ~0.005. Breaks the perfect
  rings without changing the underlying model. Doesn't fix the root cause
  but immediately improves perceived quality.
- **B** (M): **anisotropic wind-aware march** (full simplified orographic).
  Replace isotropic `coast_dist` with `coast_dist along upwind direction`.
  Windward interior stays wet (moisture from the prevailing wind); leeward
  interior dries out (rain shadow). This IS the v4 OrographicLayer in
  embryonic form.
- **C** (M): plate-half decomposition (windward vs leeward halves).
- **D** (S): hemispheric trade-wind direction param.

**PO decision (2026-05-24)**: do **NOT** pull v4 forward. **Pick A** (noise
overlay) for v2.1. Full anisotropic wind-march waits for v4. Rationale:
keeps v2.1 batches small + saves the principled fix for when it can be done
properly (with orographic upwind sampling, not a half-measure).

**Complexity**: XS. **Priority**: 2.

---

#### W4 — Beach band overwrites biome on small plates

**Symptom**: Small plates (~120 px wide) have a 22-px beach band on each
side → 40-50% of the plate is sand-colored regardless of climate. Biome
signal erased.

**Root cause**:
[`colorize_biome`](../../crates/world-gen/src/zonegen.rs) at the colour pass:
when `is_beach[i]`, paints `beach_color(beach_t[i])` (sand) **instead of**
the biome color. Beach **replaces** biome.

**Solution options**:
- **A** (XS): reduce beach band on small plates: `band = min(BEACH_FRAC × short_side, plate_radius × 0.2)`.
  Plate-aware width. Partial fix.
- **B** (S, **PICK**): **tint, don't replace**. Blend beach color INTO biome
  color by `beach_t`: `final = lerp(beach_sand, biome_color, smoothstep(beach_t))`.
  At shore (`t=0`) full sand; at inland edge (`t=1`) full biome. Climate
  signal preserved everywhere. Architecturally correct — beach is a TERRAIN
  feature overlaid on biome, not a replacement.
- **C** (S): class-aware beach color (warm sand for tropical, rocky grey for
  boreal, ice-white for polar). Bonus polish on top of B.

**Pick**: B + C combined.

**Complexity**: S. **Priority**: 2.

---

### P3 — Medium (visual richness)

#### W6 — Sharp zone-to-zone seams

**Symptom**: Biome flips abruptly at zone boundary (1-px transition). No
blending. World looks "Tetris-like" with sharp polygon edges.

**Root cause**: `colorize_biome` looks up biome via `subattr_idx_at[i]` —
the **nearest** subzone only. B3 introduced a smooth-Voronoi 2-nearest blend
for HEIGHT but biome rendering ignores it.

**Solution options**:
- **A** (S, **PICK**): **port B3's blend to biome colors**.
  `blended_height_with_owner` already computes `i1`; extend it to
  `(height, i1, i2, blend_t)`. Cache `subattr_idx_2_at` + `blend_t_at` in
  `RenderState`. In `colorize_biome`: blend `biome_color(i1)` with
  `biome_color(i2)` by `blend_t` within the seam band.
- **B** (M): classification-blend (average temp + precip across both zones
  then reclassify). Semantic blend rather than color blend. Different
  result; usually equivalent visual quality at higher cost.

**Pick**: A. Reuses B3 infrastructure perfectly. Hash-pin will need rebaseline.

**Complexity**: S. **Priority**: 3.

---

#### W5 — Whittaker 8 biomes too sparse

**Symptom**: World only shows 4-5 distinct colors despite 8 biome classes.
"Tetris" feel.

**Root cause**: Whittaker 8 = step function on the (temp, precip) plane.
Each pixel takes EXACTLY ONE of 8 classes. Missing biomes: DeciduousForest
(needs seasonality), Mediterranean (precip seasonality), SubtropicalForest,
Wetland, ConiferousMontane.

**Solution options**:
- **A** (M): **add 4-5 biomes** → 12-13 total. Requires seasonality data
  (cold-month temp, precip_seasonality). **Defer to v5**.
- **B** (S, **PICK**): **classifier-level hue interpolation**. When
  `(temp, precip)` lies near a threshold (e.g. `precip ≈ 250` or `≈ 600`),
  blend the 2 closest biome colors in proportion to distance-to-threshold.
  Doubles effective palette without adding biome classes. Doesn't violate
  the "8 biomes" scope.
- **C** (S): per-zone perlin hue noise. Violates PO directive "keep zones
  flat". **Reject.**

**Pick**: B. Defer A to v5.

**Complexity**: S. **Priority**: 3.

---

#### W9 — No mountain detail in biome render

**Symptom**: Hypso render shows ridges, valleys, foothills as gradient
shading. Biome render flattens all of it to ONE color per zone (the biome
color). Geographic depth lost.

**Root cause**: Biome render uses `elev` only for the lapse override in
`pixel_biome`, not for any visual shading.

**Solution options**:
- **A** (XS, **PICK for v2.1**): **modulate biome lightness by normalized
  elevation within the zone**. `final = biome_color × (0.85 + 0.30 × elev_norm)`.
  Brighter highland (sun-exposed), darker lowland (shadowed). Cheap,
  immediate visual win.
- **B** (M): proper hillshade overlay (slope-aware lambertian, atlas
  standard). Defer.
- **C** (S): two-pass composite (biome + hypso luminance blend). Reduces
  biome saturation.

**Pick**: A for v2.1. B for v3+.

**Complexity**: XS. **Priority**: 3.

---

#### W13 — Continentality sampled at single zone-site point

**Symptom**: Elongated zones (a zone with one coastal end + one inland end)
get a single `coast_dist` value (the site's). Continentality may
misrepresent the zone's "average" position relative to coast.

**Root cause**: `compute_zone_climate` samples `edge_dist` at one point
(the zone site `(sx, sy)`).

**Solution options**:
- **A** (S, **PICK**): sample `edge_dist` at N=8 points around the zone site
  (radius = mean sub-zone spacing) + average. Per-zone average
  continentality.
- **B** (M): pixel-level continentality (sample at each pixel). Kills the
  zone-flat decision. **Reject.**

**Pick**: A.

**Complexity**: S. **Priority**: 3.

---

### P4 — Cosmetic polish

#### W7 — HotDesert ≈ WET_SAND beach (hue ambiguity)

**Symptom**: HotDesert `#D8B070` and WET_SAND `#C4B284` are visually
adjacent → biome boundary at coast hard to read.

**Pick**: Tune HotDesert → `#D89060` (reddish, Sahara-style). Tune
WET_SAND → `#B4A89A` (cooler, more grey). Visual separation +
realism.

**Complexity**: XS. **Priority**: 4.

---

#### W10 — River blue ignores climate (frozen-but-blue)

**Symptom**: Rivers in Tundra/Ice zones paint normal blue. Should be
frozen (light blue-grey).

**Root cause**: `apply_river_overlay` paints `STREAM_COLOR`/`RIVER_COLOR`
unconditionally — no climate awareness.

**Pick**: Sample biome (via `subattr_idx_at`) at each river cell. If Ice or
Tundra → paint `#C8D5E0` (frozen). Else current colors.

**Complexity**: XS. **Priority**: 4.

---

#### W8 — Snow caps over-fire (folded into W3)

Already addressed by W3's precip-gated Ice fix. No separate work.

---

## 4 — Locked decisions

PO decisions on the 4 open forks (2026-05-24):

| Fork | Decision | Rationale |
|---|---|---|
| **W2 — pull v4 orographic forward?** | **NO** — use bridge solution (perlin noise overlay) for v2.1. Defer principled anisotropic wind-march to v4. | Keeps v2.1 batches small; preserves v4 as the "do it right" milestone with full upwind sampling. |
| **W3 — `t_pole` default value?** | **Empirical sweep** (§6.1) — generate samples at t_pole ∈ {-25, -20, -15, -10, -5}; pick by visual judgment. Not a guess. | Defaults need to be calibrated against rendered output, not predicted. |
| **W1 — `plate_count` default value?** | **Empirical sweep** (§6.2) — generate samples at plate_count ∈ {7, 10, 12, 15, 20}; pick by variety vs readability tradeoff. | Same reasoning as W3. |
| **Document this analysis?** | **YES** — this file. | Decisions captured before implementation so the batches don't drift. |

---

## 5 — Batched roadmap

4 cycles, each a full 12-phase workflow. Dependencies: B → C requires A
done; B+C blend nicely; D independent of A-C.

### Batch B5-v2.1a — "Defaults rescue" (P1 cluster)

Fixes that change DEFAULTS + small algorithm tweaks. Goal: out-of-box
"đẹp" with no CLI tuning.

- W1 — stratified y-placement (`flatworld::place_centers`)
- W3 — precip-gated Ice (`pixel_biome`)
- W14 — reach scaled by mean plate radius (`scaled_for` redesign)
- W3+W1 — default values from §6 sweeps (`t_pole`, `plate_count`)
- W7 — biome + beach hue tuning
- W10 — frozen river color

Hash-pin rebaseline (biome + hypso both change for sure — defaults +
flatworld stratified placement affects every render). Re-render the 9-sample
grid + compare ratings.

**Goal**: mean rating 5.7 → 7.0+.
**Complexity**: ~S total (all individual fixes XS-S). Estimate: 1 cycle.

### Batch B5-v2.1b — "Beach + seams + shading" (P2-P3 visual)

Visual richness pass. Doesn't change defaults; changes how pixels are
painted.

- W4 — beach tint + class-aware sand color
- W6 — port B3 blend to biome colors (RenderState extension)
- W9 — elev-modulated biome lightness

Hash-pin rebaseline (biome render changes; hypso unchanged so its pin stays).

**Goal**: visual depth, mountain detail, soft transitions.
**Complexity**: S. Estimate: 1 cycle.

### Batch B5-v2.1c — "Continentality polish" (P2-P3 algorithm)

Anti-ring + zone-average. NOT pulling v4 forward — bridge solution only.

- W2 — noise overlay on continentality (perlin-based, AMP ~0.15)
- W13 — N=8 sample per zone for `coast_dist`

Hash-pin rebaseline.

**Goal**: kill the ring artifact, more natural-looking gradients.
**Complexity**: S. Estimate: 1 cycle.

### Batch B5-v2.1d — "Whittaker hue richness" (P3)

- W5 — classifier-level hue interpolation near thresholds

Hash-pin rebaseline.

**Goal**: less "Tetris" feel without adding biome classes (defer that to v5).
**Complexity**: S. Estimate: 1 cycle.

### Cross-batch invariants

- Hypso hash-pin from `eroded_hypso_render_pins_a_content_hash` (commit
  `02289ebe`) MUST stay locked UNLESS a batch deliberately changes the
  rasterize-erode-coast pipeline. Batches a/b/c/d touch only colour-pass +
  flatworld placement → hypso may shift for W1 (placement) only; rebaseline
  with explicit note.
- All existing biome render correctness tests (`pixel_biome_*`, classifier
  tests) MUST keep passing. New defaults may change which biomes the test
  worlds produce → expect to update biome render assertion fixtures.
- 12-phase workflow + /review-impl on each batch. Lessons go to ContextHub.

---

## 6 — Calibration experiments

Two empirical sweeps to lock the two "guess vs measure" defaults.

### 6.1 — `t_pole` sweep

**Goal**: pick the `t_pole` default that gives "polar Tundra majority with
Ice on real ice caps only" on the baseline 7-plate seeds.

**Procedure**:
- Fix `plate_count = 7`, seed ∈ {7, 23, 42}, hemisphere = NorthOnly (clearest
  lat bands).
- Sweep `t_pole` ∈ {-25, -20, -15, -10, -5}.
- Render `--biome-out` for each (3 seeds × 5 t_pole values = 15 PNGs).
- Tabulate per render: (Ice pixel %, Tundra pixel %, "polar plate uniformity"
  — fraction of polar half of map that's a single color).
- **Selection criterion**: pick lowest `t_pole` such that mean Ice % across
  the 3 seeds is ≤ 15% AND polar plates show MIX (Ice + Tundra +
  BorealForest), not uniformity.

**Output**: a table + recommended `t_pole` default. Captured in a new
section §10.12 of the climate research doc (or this doc's §6.1 results
section).

### 6.2 — `plate_count` sweep

**Goal**: pick the `plate_count` default that maximizes biome diversity
across seeds while keeping each plate large enough to show internal
continentality variation.

**Procedure**:
- Fix `t_pole` = §6.1 result, hemisphere = Equatorial (typical default).
- Sweep `plate_count` ∈ {7, 10, 12, 15, 20}.
- For each value: render seeds {7, 13, 23, 42, 99} (5 seeds).
- Tabulate per (plate_count, seed): biome distinct color count, beach
  pixel %.
- **Selection criterion**:
  - Median biome-color-count across 5 seeds ≥ 5 (out of 8 max).
  - Mean beach pixel % ≤ 25% (to leave biome readable).
  - Worst-seed biome count ≥ 3 (no all-monoculture worlds).

**Output**: a table + recommended `plate_count` default. Same capture
location as §6.1.

### Calibration ordering

Run 6.1 BEFORE 6.2 — `plate_count` choice depends on what's already a
visually-good `t_pole`. Both sweeps run BEFORE Batch B5-v2.1a's
implementation phase (during its CLARIFY/DESIGN phases).

---

## 7 — Open questions (not blocking; tackle when reached)

- **Q1**: Should `peak_lapse_min_delta` scale with terrain class? Currently
  uniform 0.05; Hills (max +0.13 above base) hit it earlier than Mountains
  (max +0.48). Class-aware threshold might give more nuanced snow caps.
  Defer until Batch a's t_pole sweep shows whether it matters.
- **Q2**: After W2 noise overlay, does the perlin offset need to be
  determinstic-from-seed (it should — climate determinism is invariant)?
  Yes — use the same `Rng::for_stage(seed, "climate-noise")` pattern as
  zonegen.
- **Q3**: Should the hash-pin test be split into two — one per render
  (hypso vs biome)? Currently only hypso is pinned. Biome should also
  pin after Batch a's stabilization. Open.

---

## 8 — Anti-scope-creep checklist

What this 4-batch tuning pass MUST NOT include (defer to v3+):

- ❌ OceanCurrent layer (v3)
- ❌ Anisotropic wind-aware continentality (v4 orographic — covered by W2's
  bridge fix only)
- ❌ Seasonality / Köppen subtypes (v5)
- ❌ New biome classes beyond 8 (v5 — pending Whittaker expansion)
- ❌ Lakes / inland water (v3 hydrology)
- ❌ Per-pixel biome blending (violates "zone-flat" PO directive)
- ❌ Climate persistence to disk (separate concern)
- ❌ Author-knob preview / climate dashboard (workflow tooling, not algorithm)

---

## 9 — Summary

| Batch | Touches | Goal | Estimate |
|---|---|---|---|
| **B5-v2.1a** | Defaults + W1 + W3 + W14 + W7 + W10 | Out-of-box pretty | 1 cycle |
| **B5-v2.1b** | W4 + W6 + W9 | Visual richness | 1 cycle |
| **B5-v2.1c** | W2 + W13 | Continentality polish | 1 cycle |
| **B5-v2.1d** | W5 | Hue richness | 1 cycle |

Plus 2 calibration sweeps (§6.1 + §6.2) before Batch a starts.

**Total**: 4 cycles + 2 sweeps. Estimated wall time: 4-6 hours of focused
work. Each cycle delivers a comparable 9-sample grid for rating tracking.

After v2.1d: re-rate the 9-sample grid; target mean ≥ 7.5/10. Then either
ship as "B5 complete" or proceed to v3 (OceanCurrent).
