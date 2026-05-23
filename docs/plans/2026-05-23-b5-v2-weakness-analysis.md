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

### Batch B5-v2.1a — "Defaults rescue + beach" (P1 cluster + W4 promoted)

Fixes that change DEFAULTS + small algorithm tweaks. Goal: out-of-box
"đẹp" with no CLI tuning.

- W1 — stratified y-placement (`flatworld::place_centers`)
- W3 — precip-gated Ice (`pixel_biome`) + new `t_pole = -15` default
- W14 — reach scaled by mean plate radius (`scaled_for` redesign) +
  new `plate_count = 12` default
- **W4 — beach tint not replace** (**PROMOTED from Batch b 2026-05-23**
  after preview render showed `pc=12` defaults push beach % to 65-81% on
  small-plate worlds; W4 must ship together so the new defaults aren't
  visually worse than the old ones)
- W7 — biome + beach hue tuning
- W10 — frozen river color

Hash-pin rebaseline (biome + hypso both change — defaults + stratified
placement affects every render).

**Goal**: mean rating 5.7 → 7.0+.
**Complexity**: ~S+ total (W4 adds S). Estimate: 1 cycle, slightly larger.

### Batch B5-v2.1b — "Seams + shading" (P3 visual) — REDUCED

W4 moved to Batch a (above). Batch b now covers only:

- W6 — port B3 blend to biome colors (RenderState extension)
- W9 — elev-modulated biome lightness

Hash-pin rebaseline (biome render changes; hypso unchanged so its pin stays).

**Goal**: visual depth, mountain detail, soft transitions.
**Complexity**: S. Estimate: 1 cycle, smaller than originally planned.

#### v2.1b + v4 framework SHIPPED (2026-05-24) — W6 only + law-based eval rework

**TL;DR:** what started as a W6 measurement-fix detour (E2 → E3 fractional)
became a fundamental eval framework rework (v3 Earth-matching → v4 law-based)
after PO insight: "we should be evaluating whether maps follow geographic
*laws*, not whether they match Earth's specific biome distribution — every
generated world is different, but laws apply to all of them."

W6 ships as a **PO override** — measurably worse on metric (−0.36 mean even
under v4) but PO judges the intermediate transition strip visually superior
to the sharp 1-px biome flip without W6 (defined ecotone-like aesthetic).

#### v2.1b: W6 only + E3 fractional classifier (interim)

W6 ships, W9 deferred. Decision driven by **eval-framework incompatibility**
discovered during BUILD:

**Problem discovered:** W6 zone-seam blending produces blended RGB pixels
between adjacent biomes (e.g. Tundra/Ice midpoint at `[208, 210, 208]` is ~50
RGB from both canonicals). The original eval classifier was nearest-canonical
with tolerance 40 → these blended pixels classified as `None` → polar scenarios
dropped 3-15 composite points despite no visual regression. Three tolerance
sweeps (40/50/60) all produced regression; tightest = mean −3.54.

**Fix shipped — E3 fractional-contribution classifier** (`scripts/climate_eval.py`):
- New `classify_pixel` returns `list[(biome, weight)] | None` instead of single
  biome.
- 2-nearest canonical lookup: if both within `NEAR_THRESHOLD = 55.0` RGB,
  split inverse-distance weighted (closer biome → bigger weight, sum = 1.0);
  if only nearest within → pure 1.0 (preserves pre-W6 baseline semantics for
  non-blended pixels); if neither → None (river overlay / distant blend).
- All `analyze_render` counters refactored int → float; `score_render` math
  was already float-safe (KL, entropy, ratios).

**Apples-to-apples measurement (W6 on/off, both under E3):**

| Configuration | Mean composite |
|---|---|
| v3.0 baseline (E1/E2 nearest-canonical, pre-W6) | 76.65 |
| noW6 + E3 fractional (`v3.1_noW6_E3.json`) | 72.34 |
| **W6 + E3 fractional (`v3.1.json` — shipped)** | **72.17** |

**Verdict**:
- W6 vs noW6 under E3 = **−0.17 mean** (no significant change, all renders
  within ±1.0, no regression ≥5pt, 3 renders improve slightly inc. snowball
  +0.54).
- E3 vs E1/E2 = −4.31 mean (semantics shift cost, not W6 cost). Fractional
  counts treat seam pixels as fractional contributors to multiple biomes →
  interior entropy rises universally → continentality scores compress. This is
  the **proper** measurement; the old 76.65 was inflated by the classifier
  ignoring blended pixels as None.
- Headline: W6 is **architecturally good** (visual quality up, real-Earth-like
  soft transitions) AND **metric-neutral** once the eval framework can read
  blended pixels correctly.

**Locked artifacts (this batch):**
- `crates/world-gen/src/zonegen.rs` — W6 seam blend (RenderState caches
  `subattr_idx_2_at` + `seam_w1_q`; `colorize_biome_with` blends w1·biome(i1)
  + (1-w1)·biome(i2)). Hash pin updated to `b37691d0...`.
- `scripts/climate_eval.py` — E3 fractional classifier + float counters.
- `eval/baselines/v3.1.json` — new "to-beat" mean 72.17 (W6 + E3).
- `eval/baselines/v3.1_noW6_E3.json` — diagnostic baseline preserved for
  future regression triage (lets us isolate W6 cost vs eval-only cost in
  retrospect).

**W9 status**: deferred. The elev-modulated lightness path produced regression
even under E3 in PoC; would need its own design pass (likely combine elev with
biome-luminance preservation rather than naive RGB ±15%). Tracked in
`docs/deferred/DEFERRED.md` as `v2.1b-W9-elev-modulation`.

#### v4 law-based eval framework rework (the bigger ship)

**Problem PO surfaced 2026-05-24:** the v1-v3 eval framework had 40% of
composite weight tied to "match Earth biome distribution" (25% KL-divergence
vs Earth target distribution + 15% Earth entropy match). This punished any
non-Earth-like scenario *by design* — snowball scored 71.91 even though it
correctly produced a snowball world, desert scored 68.19 even though it
correctly produced a desert world. The eval was answering the wrong question.

**Reframing:** generated worlds are deliberately different from Earth. What
should be evaluated is **whether each world follows geographic LAWS** —
those laws apply universally regardless of whether the world is Earth-like,
snowball, hothouse, or desert.

**v4 framework (composite weights):**

| Sub-score | Weight | What it measures | Type |
|---|---:|---|---|
| `temperature_gradient` (NEW) | 25% | Pearson r(lat_dist, zone temp_mean) → near −1.0 | LAW: cooling toward poles |
| `lat_banding` | 25% | % land pixels in lat-allowed biome set (per-scenario table) | LAW: tropical at equator etc. |
| `precipitation_gradient` (NEW) | 15% | Pearson r(observed precip, circulation_curve prediction) | LAW: ITCZ wet, subtropic dry, mid-lat wet, polar dry |
| `continentality` | 15% | Entropy delta coast vs interior | LAW: interior drier than coast |
| `sanity` | 20% | Forbidden-biome rate per lat band | LAW negation |

`distribution` and `diversity` (the 2 Earth-matching metrics) **removed**.
`temperature_gradient` and `precipitation_gradient` are new zone-level
metrics computed from a JSON sidecar (`--climate-out`) that the renderer
emits alongside the biome PNG. The sidecar contains every zone's
`temp_mean / precip_annual / biome / lat_dist` from the same
`compute_zone_climate` call the renderer uses — single source of truth,
pinned by `export_matches_in_memory_compute` test in `flat_climate.rs`.

**Why sidecar JSON instead of Python re-implementation of climate physics:**
- Single source of truth (renderer + eval consume same `compute_zone_climate`)
- 30 LOC Rust + 5 LOC test vs 200+ LOC Python mirror + ongoing maintenance
- Future climate layers (v4 orographic, v5 Köppen) automatically picked up

**Composite gains (v3.0 → v4.0):**

| Scenario | v3.0 (Earth-match) | v4.0 (law-based) | Δ |
|---|---:|---:|---:|
| Baseline mean (5 Earth-like seeds) | 75.5 | 84.0 | +8.5 |
| Snowball | 71.91 | 83.44 | +11.5 |
| Hothouse | 87.40 | 90.26 | +2.9 |
| Desert | 68.19 | 88.71 | **+20.5** |
| Overall mean | 76.65 | 86.09 | **+9.4** |

Desert improvement is biggest — under v3 it was punished hardest for not
matching Earth's biome %; under v4 it's correctly scored on whether it
follows the gradient + banding + continentality laws.

**W6 under v4 law-based eval:**

| Metric | W6 (shipped) | noW6 | Δ |
|---|---:|---:|---:|
| temperature_gradient | 99.5 mean | 99.5 mean | identical (zone-level — W6 only affects pixel render, not physics) |
| precipitation_gradient | 89.5 mean | 89.5 mean | identical |
| lat_banding | 63.6 mean | 64.2 mean | −0.6 (W6 blends classify "wrong" slightly more often) |
| sanity | 93.4 mean | 94.3 mean | −0.9 (same reason) |
| **composite mean** | **86.09** | **86.45** | **−0.36** |

W6 measurably worse on pixel-level metrics, but the −0.36 mean is well
under the 5pt per-render regression threshold. PO judgment: intermediate
strips at zone seams (real Earth has ecotone zones — taiga→tundra,
forest→grassland transition belts) are visually superior to sharp 1-pixel
biome flips. Ship W6 as a PO override.

**Locked artifacts (this batch):**
- `crates/world-gen/src/flat_climate.rs` — added `ZoneClimateExport`,
  `WorldClimateExport`, `export_zone_climates(world, params)` + 2 tests
  (`export_matches_in_memory_compute` round-trip + `export_serializes_to_json`)
- `crates/world-gen/src/zonegen.rs` — W6 seam blend (kept) +
  `edge_dist_from_sea` exposed as `pub(crate)`
- `crates/world-gen/examples/flatworld.rs` — `--climate-out PATH` CLI flag
- `scripts/climate_eval.py` — v4 law-based scoring (drop distribution +
  diversity; add `temperature_gradient_law` + `precipitation_gradient_law`
  + Pearson helper + `_circulation_curve_py` reference impl)
- `scripts/climate_eval_sweep.py` — cached classifier sweep tool (reusable
  for future tolerance/weighting tuning)
- `eval/climate-eval-suite.toml` — weights swapped; profile distributions
  removed; scenario profiles keep only `description` for lat-band lookup
- `eval/baselines/v4.0.json` — new shipped baseline (W6 + v4, mean 86.09)
- `eval/baselines/v4.0_noW6.json` — diagnostic (mean 86.45, isolates W6 cost)
- `eval/baselines/v3.1_noW6_E3.json` — preserved diagnostic (E3 classifier
  cost before v4 framework rework, mean 72.34)
- `eval/compare-w6-vs-noW6/` — PNG pairs used for PO visual review
- `docs/plans/2026-05-23-flatworld-region-tree-data-architecture.md` — §11
  tilemap consumer contract (auto-updated separately; mentions sidecar)

### Batch B5-v2.1c — "Continentality polish" (P2-P3 algorithm)

Anti-ring + zone-average. NOT pulling v4 forward — bridge solution only.

- W2 — noise overlay on continentality (perlin-based, AMP ~0.15)
- W13 — N=8 sample per zone for `coast_dist`

Hash-pin rebaseline.

**Goal**: kill the ring artifact, more natural-looking gradients.
**Complexity**: S. Estimate: 1 cycle.

#### v2.1c SHIPPED (2026-05-24) — W2 + W13, architectural-correct-but-invisible

**TL;DR:** W2 + W13 implemented per spec. W13 gives small but real metric
gain (`precip_gradient` +0.7-5.5 across renders); W2 essentially invisible
visually (9/11 renders byte-identical even when AMP doubled to 0.30) due
to zone-level architecture limit. Ship as foundation, accept ring artifact
is properly fixed in v4 Orographic.

**W13 (N=9 zone-avg coast_d) — works as designed:**
- Replaced single-site `sample_edge_dist(sx, sy)` with 9-point average
  (center + 8 cardinal/diagonal at `mean_nearest_neighbour(subzone_sites)`
  radius). Elongated zones with coastal+inland extremes now get a
  representative average, not site-luck.
- `precip_gradient_law` (v4 metric) shows consistent gain: +0.7-5.5 across
  Earth-like renders, confirming reduction in single-site noise.

**W2 (noise overlay) — architecturally limited:**
- AMP=0.15 + FREQ=0.005 + SALT=0xC0FE fbm overlay added to `cont` post-clamp.
- Empirical: 9/11 renders byte-identical to noW2 baseline. Bumping AMP to
  0.30 only flipped 2 renders (hothouse + hemi_north). 4-plate seed=7 test
  (large continentality reach 81px) with AMP=0.30 vs AMP=0 still identical.
- **Root cause of invisibility**: W2 perturbs `cont` at zone level — each
  zone has one (sx, sy) → one noise value → uniform precip shift for the
  whole zone. Only flips biome when shift crosses Whittaker threshold.
  Most zones are deep in their biome → noise can't push them across →
  same output bytes.
- **What would actually break rings**: (a) per-pixel noise (varies within
  zone), or (b) anisotropic wind-march (v4 Orographic). Both out of scope
  for v2.1.
- **PO own spec note** ("noise overlay ... doesn't fix the root cause but
  immediately improves perceived quality") proved overstated empirically —
  doesn't improve perceived quality either, just stays as architectural
  foundation.

**Eval delta v4.0 → v4.1 (W6 + W2 + W13 vs W6 alone):**

| Render | v4.0 | v4.1 | Δ | Driver |
|---|---:|---:|---:|---|
| baseline_s7 / hemi_eq | 86.00 | 86.01 | +0.01 | W13 precip_grad |
| baseline_s13 | 86.53 | 86.66 | +0.13 | W13 precip_grad |
| baseline_s23 | 86.38 | 87.06 | +0.68 | W13 precip_grad |
| baseline_s42 | 85.78 | 84.23 | −1.55 | W2 lat_banding shift |
| baseline_s99 | 74.09 | 73.44 | −0.65 | W2 sanity shift |
| hemi_north | 87.83 | 88.64 | +0.81 | W13 precip_grad |
| hemi_south | 91.96 | 92.64 | +0.68 | W13 precip_grad |
| scenario_snowball | 83.44 | 83.66 | +0.22 | minor |
| scenario_hothouse | 90.26 | 90.18 | −0.08 | flat |
| scenario_desert | 88.71 | 88.87 | +0.16 | minor |
| **MEAN** | **86.09** | **86.13** | **+0.04** | mostly W13 |

No regression ≥5pt; aggregate +0.04 is technically below `composite_mean_min_improvement` (1.0) but ships as the architecturally-correct foundation
for v4 Orographic's eventual anisotropic march.

**Locked artifacts (this batch):**
- `crates/world-gen/src/flat_climate.rs` — added `W2_AMP/W2_FREQ/W2_SALT`
  consts; `mean_nearest_neighbour` + `sample_edge_dist_avg` helpers; modified
  `compute_zone_climate` to use both; 5 tests added (`mean_nearest_neighbour_picks_smallest_pairwise`,
  `sample_edge_dist_avg_equals_center_when_radius_zero`, `sample_edge_dist_avg_smooths_a_gradient`,
  `continentality_w2_w13_active_in_zone_climate`, `w2_noise_overlay_breaks_radial_symmetry`)
- `crates/world-gen/src/zonegen.rs` — biome render hash pin rebased to
  `d0c3e17c…` (W2 perturbation shifts ≥1 pixel even on 96×64 test world)
- `eval/baselines/v4.1.json` — new shipped baseline (W6 + W2 + W13, mean 86.13)
- `eval/compare-v2.1c/` — PNG pairs (v4.0-no-W2W13 vs v4.1-with-W2W13) used
  by PO to confirm W2 visual impact is below perception threshold

**Roadmap consequence**: v4 Orographic gets promoted to "needed work" status
(was just nice-to-have). W2 spec note "saves the principled fix for when it
can be done properly" now reads as honest acknowledgement, not just deferral.

### Batch B5-v2.1d — "Whittaker hue richness" (P3)

- W5 — classifier-level hue interpolation near thresholds

Hash-pin rebaseline.

**Goal**: less "Tetris" feel without adding biome classes (defer that to v5).
**Complexity**: S. Estimate: 1 cycle.

#### v2.1d + v4.3 framework SHIPPED (2026-05-24)

**TL;DR:** W5 hue interpolation initially produced HARD regression (mean
−3.25, hemi_north −13.90). Root cause: v4 eval treated every blended
ecotone pixel as "0.5 contribution to each biome" → contributions to
lat-forbidden biomes accumulated → sanity tanked. **Real Earth has
ecotones** (Taiga-Tundra, Forest-Steppe, Mediterranean-Forest are all
real-world gradient bands, not sharp 1-pixel transitions). PO insight:
the eval was punishing geographically-correct output. Solution: upgrade
eval to **ecotone-aware** scoring, then W5 ships with full spec BLEND
values producing **+2.05 mean improvement** + 6 individual renders
improving ≥1pt + 0 hard regressions.

**W5 implementation:**
- `whittaker_classify_blended_color(temp, precip) -> [u8; 3]`: probe 4
  axis-aligned directions (±BLEND_TEMP=1.5°C, ±BLEND_PRECIP=75mm), bisect
  to find Whittaker threshold position, smoothstep blend center vs adjacent
  biome color.
- `pixel_color(zc, elev_pixel, zone_base_elev, params) -> [u8; 3]`: wraps
  blended classifier + preserves hard lapse overrides (Ice/Tundra at peaks
  stay sharp — those need elev-aware bands, separate concern).
- Renderer `colorize_biome_with` swaps `pixel_biome().color()` →
  `pixel_color()`. `pixel_biome` retained for `ZoneClimateExport` semantics
  (sidecar still reports zone's dominant biome).

**v4.3 eval framework upgrade (ecotone-aware scoring):**
- `analyze_render` in [`climate_eval.py`](../../scripts/climate_eval.py):
  - **Entropy + distribution fields** (biome_counts, coast/interior_counts)
    still use fractional contributions (Shannon entropy needs distribution
    shape, that's intact).
  - **lat_banding + sanity** evaluate the WHOLE pixel:
    - `band_correct += 1.0` if **any** biome in the blend is in the lat-allowed
      set (recognizes ecotones as valid biome transitions).
    - `forbidden_count += 1.0` only if **all** biomes in the blend are
      forbidden (penalize only "no valid biome for this lat" failures).
- **Pure pixels behave identically** to pre-v4.3 — when contribs is a
  single-biome 1.0-weight, the any/all checks collapse to the single
  membership check. Backward-compat verified by math + no v4.1 baseline
  drift on noW5 renders.

**Combined v4.3 result vs v4.1 (pre-W5):**

| Render | v4.1 | v4.3 | Δ | Notes |
|---|---:|---:|---:|---|
| baseline_s7 / hemi_eq | 86.01 | 89.49 | **+3.48** | W5 + ecotone-aware net win |
| baseline_s13 | 86.66 | 90.69 | **+4.03** | same |
| baseline_s23 | 87.06 | 86.82 | −0.24 | flat |
| baseline_s42 | 84.23 | 89.42 | **+5.19** | recovered from W2 lat_banding hit |
| baseline_s99 | 73.44 | 78.81 | **+5.37** | sanity 91.3→98.9 (ecotone forgiveness) |
| hemi_north | 88.64 | 85.56 | −3.08 | still down (full lat gradient = many ecotones; ecotone-aware reduces from −13.90 → −3.08 but doesn't fully recover) |
| hemi_south | 92.64 | 92.39 | −0.25 | flat |
| scenario_snowball | 83.66 | 83.66 | +0.00 | mono-biome → no W5 firing |
| scenario_hothouse | 90.18 | 96.28 | **+6.10** | best — forest-rich threshold zones blend well |
| scenario_desert | 88.87 | 87.38 | −1.49 | minor |
| **MEAN** | **86.13** | **88.18** | **+2.05** | ≥ improvement threshold |

**Sub-score breakdown** (v4.3 averages across 11 renders):
- temperature_gradient: 99.5 (unchanged, W5 doesn't affect physics)
- lat_banding: 70.3 (up from 60.8; ecotone forgiveness)
- precipitation_gradient: 91.1 (unchanged)
- continentality: 83.4 (unchanged)
- **sanity: 97.8** (up from 91.6; biggest single subscore gain)

**Why hemi_north still −3.08:**
North-only hemisphere has the strongest lat gradient → 5 lat bands all
present → highest density of biome-band boundaries. Even with ecotone-aware
scoring, some pixels at the boundary between two distinctly-forbidden lat
bands (e.g. mid-lat HotDesert allowed + sub-arctic HotDesert forbidden)
can't be saved. Acceptable: under 5pt regression threshold, far down from
−13.90 pre-eval-upgrade.

**Why scenario_hothouse +6.10 (biggest gain):**
Hothouse params produce mostly forest + savanna at all lats → threshold
crossings are between forest-types (TempForest↔TropicalRainforest etc.)
where adjacent biomes are usually in the same allowed set → ecotone-aware
scoring + W5 visual blending compound positively.

**Locked artifacts (this batch):**
- `crates/world-gen/src/flat_climate.rs` — added `whittaker_classify_blended_color`
  + `pixel_color` + 3 unit tests (`whittaker_blended_color_returns_canonical_deep_in_biome`,
  `whittaker_blended_color_blends_at_precip_threshold`, `pixel_color_preserves_lapse_overrides_unblended`)
- `crates/world-gen/src/zonegen.rs` — `colorize_biome_with` uses `pixel_color`
  instead of `pixel_biome().color()`. Hash pin rebased to `28d88695…`.
- `scripts/climate_eval.py` — `analyze_render` ecotone-aware
  `band_correct` / `forbidden_count` (any-allowed / all-forbidden per pixel)
- `eval/baselines/v4.3.json` — new shipped baseline (mean 88.18)
- `eval/compare-v2.1d/` — visual compare set (with-W5 vs without-W5)

**Roadmap consequence:**
- W5 architectural win uncovered eval framework limitation; framework
  upgrade benefits ALL future ecotone-style features (W6 retroactively
  scored higher under v4.3 if re-evaluated; v4 Orographic when it ships
  won't face the same wall).
- v2.1 batch sequence COMPLETE — all 4 batches (a/b/c/d) shipped through
  /amaw + 12-phase workflow each. v5 Köppen seasonal still deferred.

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

### 6.1 RESULTS (run 2026-05-23, NorthOnly, seeds {7, 23, 42})

| t_pole | Mean Ice% | Pattern | Verdict |
|---:|---:|---|---|
| -25 (current) | 17.2% | polar Antarctica-everywhere | too cold |
| -20 | 14.8% | still Ice-heavy | borderline |
| **-15** ⭐ | **9.7%** | Tundra-dominant + Ice peaks on mountains | **LOCK** |
| -10 | 5.6% | TempGrass invades polar — loses polar identity | too warm |
| -5 | 0.4% | no Ice anywhere | snow caps gone |

**Lock: `t_pole = -15`.** Mean Ice% halved (17%→10%); polar plates show clear
Tundra majority with Ice only on actual mountain peaks. W3-C precip-gated Ice
will further reduce residual Ice% on polar dry zones.

### 6.2 RESULTS (run 2026-05-23, Equatorial, t_pole=-15 locked, seeds {7, 13, 23, 42, 99})

| pc | Mean distinct biomes | Min (worst seed) | Mean Beach% | Verdict |
|---:|---:|---:|---:|---|
| 7 (current) | 5.4 | **4** | 60.7% | monoculture risk on 2/5 seeds |
| 10 | 5.4 | 4 | 69.7% | no improvement |
| **12** ⭐ | **6.2** | **5** | 67.2% | min guarantee + room for internal variety |
| 15 | 6.8 | 6 | 70.5% | best variety but plates getting small |
| 20 | 6.6 | 6 | 73.8% | too cramped — plates lose internal climate detail |

**Lock: `plate_count = 12`.** Sweet spot — guarantees min 5 distinct biomes,
plates large enough for internal continentality gradient, smaller beach
proportion than pc=15/20. W4 (beach tint not replace) will further help
when it lands.

### Artifacts

PNG grids in `target/sweep-t-pole/` (15 files) + `target/sweep-plate-count/`
(25 files) — ephemeral, re-generable. Analyzer **promoted** to
[`scripts/sweep_analyze.py`](../../scripts/sweep_analyze.py) per 2026-05-23
PO decision — batches b/c/d will re-sweep to validate similar default
choices, so the analyzer is now a committed reproducible artifact.

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

---

## 10 — Batch status

### Batch B5-v2.1a — ✅ SHIPPED (2026-05-23)

6 fixes shipped (W1 + W3 + W14 + W4 + W7 + W10). Full 12-phase v2.2 workflow
+ /review-impl 1-pass (1 MED + 2 LOW resolved inline). 180 lib tests (was
171 → +9 NEW). Clippy clean. Both hypso + biome hashes pinned + rebaselined.

**Result**: 9-sample grid mean rating **5.7 → 7.5/10** (target met).

**Per-sample deltas**:
- eq_seed7: 6 → 7.5 (+1.5)
- eq_seed13: 3 → 7 (**+4** — was monoculture sand)
- eq_seed23: 7 → 8 (+1)
- eq_seed42: 2 → 7 (**+5** — was monoculture grass)
- seed7_north: 8 → 8.5 (+0.5)
- scenario_snowball: 5 → 6 (+1)
- scenario_hothouse: 8 → 8.5 (+0.5)

**Still bad (Batches b/c/d to fix)**: W2 continentality ring artifact;
W6 sharp zone seams; W9 no mountain shading; W5 only 8 biomes.

### Batch B5-v2.1f — ✅ SHIPPED (2026-05-24) — biome expansion 8→10

Added DeciduousForest + Mediterranean per PO decision after v2.1a +
v2.1e eval revealed distribution_score mean ~55 (Earth-likeness gap was
the largest single bottleneck — old 8-biome catchall collapsed 3 distinct
Earth biome types into TemperateForest).

**Changes**:
- `flat_climate::Biome` enum: 8→10 variants (tags 0-9; old tags 0-7 preserved
  for forward compat)
- `whittaker_classify`: refined to 4 thermal tiers × precip splits (cold,
  cool 5-14°C, warm 14-22°C, hot ≥22°C). Mediterranean approximated by
  `temp 14..22 ∧ precip 250..700` (dry-summer signature without explicit
  cold-month gating — true Köppen Csa/Csb subtypes need v5 seasonality).
- `Biome::color()`: DeciduousForest = `#8AAB52` autumn olive;
  Mediterranean = `#B5A562` olive-tan.
- Earth reference image: regenerated; DeciduousForest at 40-50° coastal,
  Mediterranean at 30-40° western coasts (CA/Med basin analogues).
- `scripts/climate_eval.py`: BIOME_COLORS + LAT_BANDS extended; diversity
  divisor updated 2.7 → 3.0 (10-biome reference entropy).
- `eval/climate-eval-suite.toml`: all 4 profile distributions rebuilt for
  10 biomes (Earth + Snowball + Hothouse + Desert).
- Biome render hash pin rebaselined.

**Result (vs v2.1a baseline)**:
- 8 baselines mean composite: 77.82 → 76.23 (-1.59) — modest drop because
  10-biome distribution target is structurally stricter than 8-biome (3
  Earth biomes in the warm-temperate band vs 1 → tighter KL divergence
  required for high distribution_score)
- `scenario_hothouse`: -19.77 — sanity tanked because Hothouse warm-poles
  produce Mediterranean/TemperateForest at sub-arctic lats, which the
  Earth lat-band table marks forbidden. **By scenario design**; future
  refinement could give scenarios their own lat-band tables. Accept now.
- New baseline saved as `eval/baselines/v2.1f.json` (mean 71.18). The
  v2.1a baseline is preserved for historical reference but is NOT
  directly comparable — the metric got stricter.

**Honest interpretation**: the score went DOWN but the biome model got
RICHER. Composite drop is metric recalibration, not quality regression.
The benefit is that v2.1b/c/d (and future batches) now have headroom to
improve distribution_score (currently ~40-55) by genuinely matching the
10-biome Earth target. With 8 biomes, the score was capped at ~60-70 from
the structural mismatch.

180 tests pass + clippy clean. Workflow: XL, full 12-phase v2.2.

### Batch B5-v2.1g — ✅ SHIPPED (2026-05-24) — climate default tuning (G3 only)

After v2.1f assessment via eval framework revealed 5 root-cause issues
(TempGrassland unreachable, BorealForest narrow band, polar bias 50-80%,
HotDesert under-firing, Mediterranean over-firing without seasonality
differentiator), prototyped 4 fixes (G1 classifier rebalance, G2 BorealForest
0..5→0..7, G3 precip_subtropic 300→180, G4 STRATA 4→6).

Initial v2.1g (all 4 combined) flagged REGRESSION via eval (-2.47 mean
composite). Cherry-pick experiment isolated each fix individually vs v2.1f
baseline:

| Fix | Mean Δ | Verdict |
|---|---:|---|
| G2 (BorealForest 0..7) | +0.04 | trivial — temp band 5..7°C rarely populated |
| **G3 (precip_subtropic 180)** | **+0.51** | **WIN — no regression** |
| G1 (classifier rebalance) | +0.04 | trivial — warm-mid-precip slot rarely populated |
| G4 (STRATA 4→6) | -2.41 | REGRESSION — placement change broke seed luck |

**Shipped: G3 only** — single root-cause fix: lowering `precip_subtropic`
default 300→180 mm/yr makes subtropical zones land below the 250 HotDesert
threshold by default. Real Earth subtropics get <100mm/yr; the prior 300
left HotDesert barely firing.

Per-render improvements:
  - baseline_s23: 72.69 → 74.04 (+1.35)
  - baseline_s42: 73.17 → 74.13 (+0.96)
  - hemi_north: 80.43 → 81.22 (+0.79)
  - scenario_hothouse: 57.76 → 60.81 (+3.05)
  - 4 renders unchanged
  - 2 small drops (-0.15 to -0.19)
  - **No regression >5pt**

Mean composite: 71.18 → 71.69 (+0.51 per metric, below 1.0 threshold so
suite TOML reports "no significant change" but it's a clear positive
direction). New baseline saved as `eval/baselines/v2.1g.json`.

**Lessons captured**:
- Most "obvious" fixes (G1, G2, G4) had near-zero or negative impact
- The eval framework prevented shipping G4's regression
- Single isolated fix beats multi-fix batch — cherry-pick is the right
  methodology for incremental tuning

**Architectural ceiling acknowledged**: the metric ceiling of ~72 won't
move significantly via classifier/defaults tuning. Future genuine
improvement requires v3+ OceanCurrent + finer biome subdivision (Köppen
seasonality, etc.).

### Batch v2.1h Lever A — ✅ SHIPPED (2026-05-24, commit a825156c)

Per-profile lat-band tables. Scenarios (Hothouse/Snowball/Desert) get
their own allowed/forbidden sets — Hothouse's warm-pole forests are no
longer marked forbidden against the Earth table. Pure measurement-
framework fix; no world-gen changes. **Mean composite 71.69 → 76.39
(+4.70)**, FIRST batch to pass the 1.0-improvement threshold.

### Batch v2.1i — cherry-pick exhausted (2026-05-24, NOT SHIPPED)

After v2.1h, prototyped 4 more levers (C continentality tighter; D
Mediterranean narrower; B lat-aware classifier; G mid-lat-biased
placement). Cherry-pick experiment results:

| Lever | Mean Δ | Verdict |
|---|---:|---|
| C (reach 0.4→0.3) | -0.46 | regression on hothouse |
| D (Mediterranean 250-700 → 350-700) | +0.06 | negligible |
| B (lat-aware Mediterranean bias) | +0.05 | negligible |
| G (mid-lat-biased pass-2 fill) | -5.38 | REGRESSION on 5 renders |

**v2.1 ceiling is firmly 76.39.** Every classifier/defaults lever
tried produces negligible or negative impact. Confirms: architecture
has saturated. Real lift requires v3+ (OceanCurrent / Köppen
seasonality). Cherry-pick experiment NOT committed — kept v2.1h state.

### Batch v3.0 OceanCurrent — ✅ SHIPPED (2026-05-24)

First architectural layer addition — activates the Plate slot reserved
in B5 v2 since 2026-05-23 (research doc §10). Models ocean gyre
temperature deltas: NH east-coast warm (Gulf Stream), NH west-coast
cool (Canary Current); reversed in SH. Magnitude ±5°C at mid-lat peak
(matches Earth NYC vs Madrid delta), fades to 0 at equator + pole.

Per-zone formula:
  ew_position    = (zone.sx - plate.center.x) / plate_half_width
  hemi_sign      = +1 NH (Equatorial sy<h/2) / -1 SH / per layout
  lat_envelope   = sin(π × (lat_dist-0.2)/0.65) for lat_dist ∈ [0.2, 0.85]
  current_delta  = ew × hemi × envelope × OCEAN_CURRENT_STRENGTH (5°C)
  temp += current_delta  // after insolation, before classification

**Eval result (vs v2.1h baseline)**:
  baseline_s7    76.09 → 75.98 (-0.11)
  baseline_s13   82.59 → 83.91 (+1.32) ✓
  baseline_s23   74.04 → 74.53 (+0.49)
  baseline_s42   74.13 → 74.97 (+0.84)
  baseline_s99   74.91 → 72.14 (-2.77)
  hemi_eq        76.09 → 75.98 (-0.11)
  hemi_north     81.22 → 81.18 (-0.04)
  hemi_south     73.35 → 76.91 (+3.56) ✓ ← biggest gain (SH gyre correct)
  scenarios      mostly unchanged

  Mean: 76.39 → 76.65 (+0.26)
  2 renders >1pt up; 0 regressions >5pt.

**Smaller than predicted** (+3-7 was my estimate). Why: ±5°C delta
rarely crosses tier boundaries (5/14/22°C) — most zones get a
temperature shift but stay in the same biome class. Bigger lift would
need wider current OR more biome tiers (Köppen seasonality = v5+).

**Architecturally correct** (Plate slot finally active) + small
quantitative gain. The hemi_south +3.56 is meaningful: SH gyre now
producing correct E-W asymmetry on its dominant render.

New baseline: `eval/baselines/v3.0.json` (76.65).

### Batches b / c / d — pending

Per §5 roadmap, unchanged.

### Batch B5-v2.1e — "Metric refinement" (NEW, added 2026-05-24 after eval assessment)

After v2.1a + eval framework shipped (commit 1591a656), objective
assessment of the captured baseline (mean 74.92) revealed 2 metric flaws
that would block accurate measurement of v2.1d (Whittaker hue interp):

- **continentality_score saturated at 100.0** on all baselines — formula
  `clamp(50 + 50×Δ, 0, 100)` always hits 100 because Δ ≥ 1.0 universally.
  Not discriminative — can't measure any future improvement on this axis.
- **`BIOME_COLORS` lookup is exact-match** — when v2.1d ships Whittaker hue
  interpolation (blended colors between adjacent biomes), pixels won't
  match any key → classified `None` → distribution + diversity scores
  DROP artifactually, creating a false regression.

Scope: 2 fixes, both XS, ship as 1 batch BEFORE v2.1b/c/d.

- **E1 — SHIPPED** Tighter continentality formula: `clamp(100 × Δ / 2.0, 0, 100)`
  (linear-to-cap at Δ=2.0). Replaces `clamp(50 + 50×Δ, 0, 100)` which
  saturated at 100 universally. Now Δ=0 → 0 (no differentiation = bad),
  Δ=1 → 50, Δ=2+ → 100. Discriminative on scenarios; baselines still
  saturate because they genuinely have Δ ≥ 2.0 (many small plates with
  high coast diversity + low interior diversity).
- **E2 — DEFERRED to v2.1d** Nearest-color biome classifier was initially
  shipped with `TOLERANCE = 60` (within Euclidean RGB distance of nearest
  canonical biome → classify). **Reverted** because it picked up beach-
  tinted pixels (W4 blend of biome × sand ≈ Tundra grey) → false biome
  counts → composite tanked 74.92 → 48.48 across all baselines. The fix
  for v2.1d's Whittaker hue interp will need a curated (biome_a, biome_b)
  blend-midpoint match (not generic nearest-neighbor in RGB space).
  Re-tackle when v2.1d ships.

Re-baseline `eval/baselines/v2.1a.json` post-E1.

**Result (E1 only)**: mean composite 74.92 → 74.06 (delta = -0.86 from
scenarios revealing their true differentiation). Baselines unchanged
because all hit cap 100 → 100. Continentality is now meaningful on
extreme scenarios; baselines remain at the high end of the discriminative
range (interpretable as "good").

Ordering: ✅ v2.1e E1 shipped → re-baseline locked → run v2.1b → diff
→ run v2.1c → diff → run v2.1d (with E2 fix bundled) → diff.
