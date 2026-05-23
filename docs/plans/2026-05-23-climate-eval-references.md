# Climate Eval — Earth-Standard References & Scoring

> **Status:** LOCKED 2026-05-23. Reference document for
> [`scripts/climate_eval.py`](../../scripts/climate_eval.py) — the objective
> quality measurement framework that replaces the prior subjective rating
> system (where each B5 v2.* batch was rated 1-10 by visual judgment).
>
> Companion docs:
> - [`2026-05-23-climate-simulation-research.md`](2026-05-23-climate-simulation-research.md) — B5 v2 spec
> - [`2026-05-23-b5-v2-weakness-analysis.md`](2026-05-23-b5-v2-weakness-analysis.md) — v2.1 roadmap

---

## 1 — Why this exists

Through B5 v2 + B5 v2.1a, every quality assessment was a subjective rating
("eq_seed42 was 2/10, now 7/10"). The PO objection (2026-05-23): "**mọi
adjustment đều được đánh giá theo cảm tính nên chưa rõ chất lượng mỗi lần
adjust có cải thiện không**" — every adjustment evaluated by feeling, no way
to objectively confirm improvement.

This doc + the eval script give us:

1. **A fixed eval suite** — 11 reference renders, same set every batch.
2. **Earth-standard target profiles** — biome distribution + lat banding
   per real-world data.
3. **5 quantitative sub-scores** per render, composited into one number.
4. **Baseline JSON** — captured at the end of each batch, diffed against
   prior batch's JSON. Improvement / regression is **measurable**, not
   debated.

---

## 2 — Earth reference data

### 2.1 Sources

| Reference | Use |
|---|---|
| Olson et al. (2001), *Terrestrial Ecoregions of the World*, BioScience 51(11):933-938 | Land-cover biome %; lat distribution |
| Beck et al. (2018), *Köppen-Geiger 1-km*, Sci. Data 5:180214 | Latitudinal climate classes |
| Whittaker (1975), *Communities and Ecosystems* | Temp × precip biome ranges |
| NCEP/NCAR Reanalysis | Temperature + precipitation by lat / lon (cross-check) |

### 2.2 Earth biome distribution (target %)

**v2.1f update (2026-05-24)**: expanded from 8 to 10 biomes. Added
DeciduousForest (cool temperate, eastern N America / Europe / E Asia) and
Mediterranean (warm temperate dry-summer, CA / Med basin / Cape SA / SW Aus /
central Chile). Previous TemperateForest catchall (13%) now splits into 3
distinct types matching Earth's actual distribution.

| Our Biome | Earth % | Notes |
|---|---:|---|
| **Ice** | 10.0 | Antarctica (~9%) + Greenland (~1%) |
| **Tundra** | 7.0 | Arctic + sub-Antarctic + alpine tundra |
| **BorealForest** | 16.5 | Taiga (Russia + Canada + Scandinavia) |
| **DeciduousForest** ⭐NEW | 7.0 | Eastern N America, Europe, E Asia mixed forest |
| **TemperateForest** | 5.0 | Warm humid subtropical only (SE US, Yangzi) |
| **Mediterranean** ⭐NEW | 4.0 | Dry-summer warm temperate (5 distinct regions) |
| **TemperateGrassland** | 7.5 | Prairie + steppe + pampas |
| **HotDesert** | 18.0 | Hot + cold desert |
| **Savanna** | 13.0 | Tropical grassland + xeric shrubland |
| **TropicalRainforest** | 12.0 | Amazon + Congo + SE Asia + New Guinea |
| **(total)** | 100.0 | |

These targets are the `distribution_target` profile in
`eval/climate-eval-suite.toml`.

**Metric calibration shift**: 10-biome targets are more demanding than the
old 8-biome ones (3 buckets where there was 1 → tighter KL divergence
required to score well). The v2.1a baseline (74.06 mean) is NOT directly
comparable to v2.1f baseline (71.18 mean) because the metric changed
underneath; comparison going forward must use `eval/baselines/v2.1f.json`.

### 2.3 Latitudinal banding (which biomes appear at which lat)

Each lat band has an **allowed set** and a **forbidden set**. A render is
penalized for any pixel whose biome is in the forbidden set for its lat.

`lat_dist` is the normalized distance from equator to pole (0 = equator,
1 = pole), per `HemisphereLayout::lat_dist`.

| lat_dist range | Earth analogue | Allowed | Forbidden |
|---|---|---|---|
| 0.00 – 0.20 | Tropical (0-15° lat) | TropicalRainforest, Savanna, HotDesert | Ice, Tundra, BorealForest |
| 0.20 – 0.40 | Subtropical (15-30°) | HotDesert, Savanna, TemperateForest, TemperateGrassland | Ice, Tundra |
| 0.40 – 0.60 | Mid-lat (30-50°) | TemperateForest, TemperateGrassland, HotDesert, BorealForest | TropicalRainforest |
| 0.60 – 0.80 | Sub-arctic (50-70°) | BorealForest, TemperateGrassland, Tundra | TropicalRainforest, Savanna, HotDesert |
| 0.80 – 1.00 | Polar (70-90°) | Tundra, Ice, BorealForest | TropicalRainforest, Savanna, HotDesert |

The `lat_banding_score` and `sanity_score` both use this table.

### 2.4 Continentality (coast vs interior diversity)

Earth's coasts have higher biome diversity than continental interiors:
- Mediterranean / oceanic forest / mangrove / steppe-transition at coasts
- Single dominant desert / cold steppe in deep continental interiors

The reference image (`eval/earth_reference.png`) encodes this — Eurasia's
center is HotDesert (Gobi-style), its coast is TemperateForest / Savanna.

**Continentality target**: `Shannon_entropy(coast) - Shannon_entropy(interior) > 0`
A render where interior is MORE diverse than coast would score poorly.

---

## 3 — Eval suite (11 fixed renders)

### 3.1 Earth-like baselines (5 renders)

| Name | Seed | Hemisphere | Climate params | Target profile |
|---|---|---|---|---|
| `baseline_s7`  | 7  | Equatorial | defaults | earth |
| `baseline_s13` | 13 | Equatorial | defaults | earth |
| `baseline_s23` | 23 | Equatorial | defaults | earth |
| `baseline_s42` | 42 | Equatorial | defaults | earth |
| `baseline_s99` | 99 | Equatorial | defaults | earth |

### 3.2 Hemisphere variants (3 renders)

| Name | Seed | Hemisphere | Target |
|---|---|---|---|
| `hemi_eq`    | 7 | Equatorial | earth |
| `hemi_north` | 7 | NorthOnly  | earth_north (lat banding pole at y=h) |
| `hemi_south` | 7 | SouthOnly  | earth_south (lat banding pole at y=0) |

### 3.3 Extreme scenarios (3 renders) — scenario-specific targets

| Name | Params | Target profile |
|---|---|---|
| `scenario_snowball` | t_eq=8 t_pole=-45 ice_temp=-15 | snowball: ≥80% Ice+Tundra |
| `scenario_hothouse` | t_eq=40 t_pole=5 precip×1.5 | hothouse: ≤5% Ice, ≥40% any-Forest |
| `scenario_desert`   | precip÷4 | desert: ≥50% HotDesert+Savanna |

Scenario profiles override the Earth distribution; they get their own
`distribution_score` calculated against the scenario target.

---

## 4 — Scoring formulas

5 sub-scores per render, each 0-100. Composite is a weighted sum (default
weights below; tunable in suite TOML).

### 4.1 `distribution_score` (weight 0.25)

Measures how close the render's biome % distribution is to the target.

```
observed = [pct_biome_i for i in 8]
target   = profile.distribution
kl_div   = sum(observed[i] * log(observed[i] / target[i])) for non-zero pairs
score    = 100 × exp(-kl_div)
```

`exp(-kl_div)` maps `kl_div = 0` (perfect match) → score 100,
`kl_div = ln(2) ≈ 0.69` (50% target divergence) → score 50.

### 4.2 `lat_banding_score` (weight 0.25)

Fraction of biome pixels falling in their allowed lat band per §2.3 table.

```
correct = count(pixel where pixel.biome ∈ allowed(pixel.lat_dist))
total   = count(land pixels)
score   = 100 × correct / total
```

A pixel that's TropicalRainforest at lat_dist=0.05 is correct (in allowed
set). A pixel that's TropicalRainforest at lat_dist=0.85 is incorrect.

### 4.3 `continentality_score` (weight 0.15)

Δ in Shannon entropy of biome distribution between coast (edge_dist < beach_band)
and interior (edge_dist > 2 × beach_band) pixels.

```
H_coast    = shannon_entropy(biome_counts_at_coast)
H_interior = shannon_entropy(biome_counts_at_interior)
delta      = H_coast - H_interior   // positive = Earth-like
score      = clamp(50 + 50 × delta, 0, 100)
```

`delta = 0` → score 50; `delta = 1` (coast much more diverse) → 100.

### 4.4 `diversity_score` (weight 0.15)

Shannon entropy of biome distribution, normalized to Earth's reference.

```
H_observed = shannon_entropy(biome_counts)
H_earth    = ~2.7 bits (computed from the Earth reference image)
score      = 100 × min(1.0, H_observed / H_earth)
```

A monoculture world (1 biome) has H=0 → score 0.

### 4.5 `sanity_score` (weight 0.20)

Penalty for forbidden-biome-in-wrong-lat-band per §2.3 table.

```
forbidden_pixels = count(pixel where pixel.biome ∈ forbidden(pixel.lat_dist))
total_land       = count(land pixels)
score            = 100 × max(0, 1 - 2 × forbidden_pixels / total_land)
```

Penalty rate of 2.0 means 50% of forbidden pixels → score 0.

### 4.6 Composite

```
composite = 0.25 × distribution
          + 0.25 × lat_banding
          + 0.15 × continentality
          + 0.15 × diversity
          + 0.20 × sanity
```

Range 0-100. A "good" Earth-like render should score ≥ 65.

---

## 5 — Comparison workflow

```bash
# After Batch N completes, capture baseline:
python scripts/climate_eval.py --output eval/baselines/v2.1a.json

# Subsequent batch — diff vs prior:
python scripts/climate_eval.py --baseline eval/baselines/v2.1a.json

# Output: per-render score diff + composite mean diff + per-subscore mean diff
```

A batch is "improvement" iff:
- Composite mean increased by ≥ 1.0
- No render regressed by > 5.0 in composite (catches "improved A but broke B")
- No sub-score regressed by > 10.0 in mean (catches "boosted distribution but tanked lat_banding")

Regression rules can be tuned in suite TOML.

---

## 6 — Sanity self-check after build

Before trusting any score: validate that the metric agrees with prior
subjective ratings.

| Sample | v2 subjective | v2.1a subjective | Metric must show |
|---|---:|---:|---|
| eq_seed13 | 3/10 | 7/10 | v2.1a composite > v2 composite by ≥15 |
| eq_seed42 | 2/10 | 7/10 | v2.1a composite > v2 composite by ≥15 |
| seed7_north | 8/10 | 8.5/10 | v2.1a composite ≥ v2 composite (small +) |
| scenario_hothouse | 8/10 | 8.5/10 | v2.1a composite ≥ v2 composite |

If metric disagrees with subjective consensus on these load-bearing samples,
the scoring formulas (weights, thresholds) need tuning before the framework
is trusted for future batches.

---

## 7 — Open Q (deferred)

- Q1: Should `continentality_score` use **per-plate** coast distance (more
  Earth-like) instead of map-wide? Current uses map-wide; revisit if scores
  feel off.
- Q2: Should `sanity_score` give different penalty weights to different
  forbidden biomes (e.g. TropicalRainforest-at-pole is more egregious than
  Tundra-at-equator)? Currently uniform.
- Q3: The Earth reference image is hand-coded. Should it be re-derived from
  Olson WWF raster data (10 MB) for accuracy? Deferred unless scores look
  unrepresentative.
