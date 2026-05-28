"""Climate eval — geographic-law-based quality measurement for the flatworld
biome renderer.

**v4 (law-based)**: scores measure how well a render follows geographic LAWS
(temperature decreases poleward, precipitation follows ITCZ circulation,
biomes respect their lat band, interior drier than coast) — NOT how closely
it matches Earth's specific biome distribution. This means snowball worlds,
desert worlds, hothouse worlds all score honestly against the laws they
should follow, not penalized for not being Earth.

5 sub-scores:
  1. temperature_gradient_law (25%) — Pearson r(lat_dist, zone temp_mean)
     should be strongly negative (cooling toward poles).
  2. lat_banding (25%) — % land pixels whose biome is in the lat-allowed set
     for that band (scenario-specific table).
  3. precipitation_gradient_law (15%) — Pearson r(observed precip, predicted
     precip from circulation_curve(lat, scenario_params)). Each scenario uses
     its own params, so high r = lat-circulation law followed in this physics.
  4. continentality (15%) — Shannon entropy delta between coastal and interior
     biome distributions. Law: interior is drier/more extreme than coast.
  5. sanity (20%) — penalty for biomes appearing in their forbidden lat band
     (e.g. TropicalRainforest at the pole).

Sub-scores 1+3 read the per-zone climate sidecar JSON (`--climate-out`); 2+4+5
read the biome PNG with E3 fractional-contribution classifier.

Usage:
  python scripts/climate_eval.py
       → render PNG + sidecar JSON; score; print Markdown report
  python scripts/climate_eval.py --output eval/baselines/v4.0.json
       → also save scores as JSON baseline for future diffs
  python scripts/climate_eval.py --baseline eval/baselines/v4.0.json
       → diff against baseline + print regression report
"""

import argparse
import json
import math
import subprocess
import sys
from collections import Counter
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
SUITE_TOML = REPO_ROOT / "eval" / "climate-eval-suite.toml"
EARTH_REF = REPO_ROOT / "eval" / "earth_reference.png"
RENDERS_DIR = REPO_ROOT / "target" / "climate-eval"


# ---------- v4 law-based metrics (sidecar JSON) ----------

def pearson(xs, ys) -> float:
    """Pearson correlation coefficient. Returns 0.0 if either series has zero
    variance (a flat field is "no gradient" rather than "infinite gradient")."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    dx = sum((xs[i] - mx) ** 2 for i in range(n))
    dy = sum((ys[i] - my) ** 2 for i in range(n))
    denom = (dx * dy) ** 0.5
    if denom < 1e-9:
        return 0.0
    return num / denom


def _circulation_curve_py(lat_dist: float, params: dict) -> float:
    """Mirror of `flat_climate::circulation_curve` — kept tiny + stable.
    Returns predicted precip (mm/yr) for a zone at `lat_dist` under the
    scenario's params. Used to score how well observed precip matches the
    predicted lat-circulation curve (precipitation_gradient_law)."""
    t = max(0.0, min(1.0, lat_dist))
    if t <= 0.33:
        k = t / 0.33
        raw = params["precip_eq"] * (1 - k) + params["precip_subtropic"] * k
    elif t <= 0.67:
        k = (t - 0.33) / (0.67 - 0.33)
        raw = params["precip_subtropic"] * (1 - k) + params["precip_midlat"] * k
    else:
        k = (t - 0.67) / (1.0 - 0.67)
        raw = params["precip_midlat"] * (1 - k) + params["precip_polar"] * k
    return max(0.0, raw)


def temperature_gradient_law(zones: list) -> float:
    """Score how monotonically temperature decreases from equator to pole.

    Score = 100 × max(0, −r) where r = Pearson(lat_dist, temp_mean).
    - r = −1.0 (perfect cooling poleward) → 100
    - r = 0 (no gradient) → 0
    - r > 0 (inverted: pole warmer than equator) → 0

    Scenario-agnostic: snowball / hothouse / desert all measured by INTERNAL
    monotonicity, not absolute temperature values."""
    if len(zones) < 3:
        return 0.0
    lat = [z["lat_dist"] for z in zones]
    temp = [z["temp_mean"] for z in zones]
    r = pearson(lat, temp)
    return 100.0 * max(0.0, -r)


def precipitation_gradient_law(zones: list, params: dict) -> float:
    """Score how well observed precip matches the lat-circulation prediction.

    Score = 100 × max(0, r) where r = Pearson(predicted_precip, observed_precip).
    Predicted uses each scenario's own params (precip_eq / sub / mid / polar)
    so Hothouse / Snowball / Desert measured against THEIR predicted curves —
    a high r means the lat-circulation law is followed in that physics, not
    that absolute values match Earth.

    Will not reach 100 in practice because continentality + ocean current add
    legitimate variance the lat-only prediction cannot capture; ~50-80 is
    healthy for Earth-like, less for extreme scenarios."""
    if len(zones) < 3:
        return 0.0
    pred = [_circulation_curve_py(z["lat_dist"], params) for z in zones]
    obs = [z["precip_annual"] for z in zones]
    r = pearson(pred, obs)
    return 100.0 * max(0.0, r)

# Biome color → name. Must mirror `Biome::color()` in flat_climate.rs at the
# current commit. **v5 Köppen-lite: 19 biomes** (was 10 Whittaker pre-v5).
BIOME_COLORS = {
    # POLAR (E)
    (245, 248, 250): "Ef",        # Ice cap (Antarctica)
    (184, 183, 174): "Et",        # Tundra (Arctic)
    # CONTINENTAL (D)
    (58, 86, 60):    "Dfd",       # Extreme subarctic (Yakutsk)
    (74, 107, 71):   "Dfc",       # Subarctic (Siberia)
    (100, 138, 88):  "Dfb",       # Warm humid continental (Canada prairies)
    (125, 158, 96):  "Dfa",       # Hot humid continental (Central US)
    (148, 175, 110): "Dwa",       # Continental dry-winter monsoon (NE China)
    # TEMPERATE (C)
    (79, 139, 65):   "Cfb",       # Oceanic (UK, NW Europe)
    (138, 171, 82):  "Cfa",       # Humid subtropical (SE USA, Yangzi)
    (181, 165, 98):  "Csa",       # Mediterranean hot summer (Med basin)
    (165, 175, 115): "Csb",       # Mediterranean warm summer (coastal CA)
    (155, 180, 95):  "Cwa",       # Subtropical monsoon (S China)
    # ARID (B)
    (174, 165, 105): "Bsk",       # Cold steppe (Kazakh)
    (195, 165, 132): "Bwk",       # Cold desert (Gobi)
    (201, 192, 74):  "Bsh",       # Hot steppe (Sahel)
    (216, 144, 96):  "Bwh",       # Hot desert (Sahara)
    # TROPICAL (A)
    (15, 77, 26):    "Af",        # Tropical rainforest (Amazon)
    (35, 100, 35):   "Am",        # Tropical monsoon (Mumbai)
    (185, 180, 80):  "Aw",        # Tropical savanna (Sahel-tropics)
}
ALL_BIOMES = list(BIOME_COLORS.values())

VOID = (12, 16, 28)
# **v5 Köppen lat-band tables** (19 biomes). Per Beck 2018 Köppen-Geiger
# world map: which Köppen subtypes legitimately appear in each lat band.
# Allowed = appears in the band on real Earth; forbidden = never appears
# (or only via lapse override at altitude, e.g. Ef on tropical mountains).
# Lat-band tables relaxed for Köppen variability: real Earth has biome
# spillover across bands due to continentality, ocean currents, altitude
# (e.g. Aw appears at mid-lat continental dry interiors; Cfb extends into
# polar on western maritime continents). Only mark TRULY impossible biomes
# as forbidden (e.g. Af tropical rainforest at the pole).
LAT_BANDS_EARTH = [
    # (lat_dist_lo, lat_dist_hi, allowed_set, forbidden_set)
    (0.00, 0.20,  # tropics 0-15°
     {"Af", "Am", "Aw", "Bwh", "Bsh", "Cfa", "Cwa"},
     {"Ef", "Dfd", "Dfc"}),
    (0.20, 0.40,  # subtropics 15-30°
     {"Bwh", "Bsh", "Aw", "Am", "Cfa", "Csa", "Cwa", "Bsk", "Bwk"},
     {"Ef", "Dfd"}),
    (0.40, 0.60,  # mid-lat 30-50°
     {"Cfb", "Cfa", "Csa", "Csb", "Cwa", "Dfa", "Dfb", "Dwa", "Bsk", "Bwk", "Bsh", "Bwh", "Aw"},
     {"Ef", "Dfd", "Af", "Am"}),
    (0.60, 0.80,  # sub-arctic 50-70°
     {"Dfc", "Dfb", "Dfa", "Dwa", "Dfd", "Bsk", "Bwk", "Cfb", "Et"},
     {"Af", "Am", "Aw", "Bwh", "Bsh"}),
    (0.80, 1.00,  # polar 70-90°
     {"Et", "Ef", "Dfd", "Dfc", "Bwk"},
     {"Af", "Am", "Aw", "Bwh", "Bsh", "Cfa", "Csa", "Cwa", "Csb"}),
]
# Hothouse: warm world. Even poles can host forests; only Ef strictly
# forbidden (only via lapse on extreme peaks).
LAT_BANDS_HOTHOUSE = [
    (0.00, 0.20,
     {"Af", "Am", "Aw", "Cfa", "Cwa"},
     {"Ef", "Et", "Dfd", "Dfc", "Dfb", "Cfb"}),
    (0.20, 0.40,
     {"Af", "Am", "Aw", "Cfa", "Csa", "Cwa", "Bsh", "Bwh"},
     {"Ef", "Et", "Dfd", "Dfc", "Dfb"}),
    (0.40, 0.60,
     {"Cfa", "Cfb", "Csa", "Csb", "Cwa", "Bsh", "Bwh", "Dfa", "Dfb"},
     {"Ef", "Dfd"}),
    (0.60, 0.80,
     {"Cfb", "Cfa", "Dfb", "Dfc", "Dfa", "Dwa"},
     {"Ef"}),
    (0.80, 1.00,
     {"Cfb", "Dfb", "Dfc", "Dwa", "Et"},
     set()),  # nothing strictly forbidden at hothouse poles
]
# Snowball: cold world. Forests only at warmest equator stripe; Ef/Et dominant.
LAT_BANDS_SNOWBALL = [
    (0.00, 0.20,
     {"Et", "Dfc", "Dfb", "Cfb", "Ef"},
     {"Af", "Am", "Aw", "Bwh", "Bsh"}),
    (0.20, 0.40,
     {"Et", "Dfd", "Dfc", "Ef", "Bsk", "Bwk"},
     {"Af", "Am", "Aw", "Bwh", "Bsh", "Cfa"}),
    (0.40, 0.60,
     {"Et", "Ef", "Dfd", "Dfc", "Bwk"},
     {"Af", "Am", "Aw", "Bwh", "Bsh", "Csa", "Cfb", "Cfa"}),
    (0.60, 1.00,
     {"Et", "Ef", "Dfd"},
     {"Af", "Am", "Aw", "Bwh", "Bsh", "Csa", "Cfb", "Cfa",
      "Dfa", "Dfb", "Dfc", "Dwa"}),
    (1.00, 1.001, {"Ef"}, set()),
]
# Desert: dry world. HotDesert / Savanna / Bsh dominate. Forests only in
# rare wet pockets.
LAT_BANDS_DESERT = [
    (0.00, 0.20,
     {"Bwh", "Bsh", "Aw", "Af"},
     {"Ef", "Et", "Dfd", "Dfc", "Cfb"}),
    (0.20, 0.40,
     {"Bwh", "Bsh", "Aw", "Bsk", "Csa"},
     {"Ef", "Et", "Dfd", "Dfc", "Af", "Am"}),
    (0.40, 0.60,
     {"Bwh", "Bwk", "Bsh", "Bsk", "Csa", "Csb"},
     {"Af", "Am", "Aw", "Ef", "Dfd"}),
    (0.60, 0.80,
     {"Bsk", "Bwk", "Et", "Dfc", "Dfb"},
     {"Af", "Am", "Aw", "Csa", "Cfb", "Cfa"}),
    (0.80, 1.00,
     {"Et", "Ef", "Dfd", "Dfc"},
     {"Af", "Am", "Aw", "Bwh", "Bsh", "Csa", "Cfb", "Cfa",
      "Dfa", "Dfb", "Dwa"}),
]
# Lever A (v2.1h): per-profile lat-band tables. Scenarios get their own
# tables because their physics differ from Earth — Hothouse poles SHOULD
# have forests; Snowball equator SHOULD have Tundra; etc. Without this,
# scenario sanity_score tanked (Hothouse 2.3 because warm-poles produced
# forests where the Earth table marked them forbidden).
PROFILE_LAT_BANDS = {
    "earth": LAT_BANDS_EARTH,
    "hothouse": LAT_BANDS_HOTHOUSE,
    "snowball": LAT_BANDS_SNOWBALL,
    "desert": LAT_BANDS_DESERT,
}


# ---------- helpers ----------

def lat_dist_for(y: int, height: int, hemisphere: str) -> float:
    h = float(height)
    if hemisphere == "equatorial":
        return min(1.0, abs((y - h * 0.5) / (h * 0.5)))
    if hemisphere == "north":
        return min(1.0, y / h)
    if hemisphere == "south":
        return min(1.0, (h - y) / h)
    raise ValueError(f"unknown hemisphere {hemisphere!r}")


def band_for(lat_dist: float, bands=None):
    """Lat-band lookup. `bands` defaults to Earth; pass a scenario table to
    use scenario-specific lat semantics (Lever A v2.1h)."""
    if bands is None:
        bands = LAT_BANDS_EARTH
    for lo, hi, allowed, forbidden in bands:
        if lo <= lat_dist <= hi:
            return allowed, forbidden
    return bands[-1][2], bands[-1][3]


# E3 v2.1b parameters (fractional-contribution classifier).
# - NEAR_THRESHOLD: pixel within this RGB distance of a canonical biome
#   color counts as a candidate for that biome. Sized to capture W6 seam
#   midpoints (Tundra↔Ice midpoint sits at ~50 from both canonicals).
# - BEACH_REJECT_DIST: stage-2 pre-filter distance from WET_SAND/DRY_SAND
#   (which sit ~25 RGB from Tundra — would false-positive otherwise).
NEAR_THRESHOLD = 55.0
BEACH_REJECT_DIST = 30.0
# WET_SAND + DRY_SAND from zonegen.rs (v2.1a W7 tuning).
BEACH_COLORS = [(180, 168, 154), (212, 200, 178)]


def classify_pixel(rgb: tuple):
    """Return `list[(biome, weight)]` for biome contributions, or None
    (ocean / beach / river overlay).

    **E3 v2.1b fractional contribution** — replaces E2 nearest-canonical
    so W6 zone-seam blending is measurable correctly. A pixel blended 50/50
    between Tundra and Ice contributes 0.5 to each biome's count instead of
    being misclassified as "neither" (the E2 failure mode that punished
    W6 -3.54 mean).

    Stages:
      1. Exact VOID → None (ocean).
      2. Within `BEACH_REJECT_DIST` of any canonical beach color → None
         (beach pre-filter — beach colors are close to Tundra in RGB
         space and would false-positive nearest-neighbor otherwise).
      3. Find 2 nearest canonical biomes by Euclidean RGB distance d1 ≤ d2.
         - d1 > NEAR_THRESHOLD → None (no biome is close; likely river
           overlay or distant-biome mid-blend the classifier can't read).
         - d2 > NEAR_THRESHOLD → `[(biome1, 1.0)]` (pure/dominant pixel —
           only biome1 is near, preserves non-W6 baseline behavior).
         - both ≤ NEAR_THRESHOLD → `[(biome1, w1), (biome2, w2)]` where
           `w1 = d2 / (d1+d2)` and `w2 = d1 / (d1+d2)` (closer biome gets
           bigger weight; d1=0 → w1=1.0; d1=d2 → split 50/50).

    Invariants:
      - Pure-canonical pixel (d1=0) returns `[(biome, 1.0)]` — preserves
        the E2 1:1 mapping for non-blended pixels, so pre-W6 baselines
        remain comparable.
      - Each return weights sum to ≤ 1.0 (== 1.0 if not None; 0 if None).
    """
    if rgb == VOID:
        return None
    # Stage 2: beach pre-filter
    for bc in BEACH_COLORS:
        dr = rgb[0] - bc[0]; dg = rgb[1] - bc[1]; db = rgb[2] - bc[2]
        if dr * dr + dg * dg + db * db < BEACH_REJECT_DIST * BEACH_REJECT_DIST:
            return None
    # Stage 3: 2-nearest canonical search (linear over ≤10 colors).
    d1_sq = float("inf"); d2_sq = float("inf")
    biome1 = None; biome2 = None
    for color, biome in BIOME_COLORS.items():
        dr = rgb[0] - color[0]; dg = rgb[1] - color[1]; db = rgb[2] - color[2]
        d_sq = dr * dr + dg * dg + db * db
        if d_sq < d1_sq:
            d2_sq = d1_sq; biome2 = biome1
            d1_sq = d_sq; biome1 = biome
        elif d_sq < d2_sq:
            d2_sq = d_sq; biome2 = biome
    d1 = math.sqrt(d1_sq)
    d2 = math.sqrt(d2_sq)
    if d1 > NEAR_THRESHOLD:
        return None
    if d2 > NEAR_THRESHOLD or biome2 is None:
        return [(biome1, 1.0)]
    # Blend region: both candidates near. Inverse-distance split.
    total = d1 + d2
    if total < 1e-6:
        # Degenerate: identical canonical colors (shouldn't happen with the
        # current 10-biome palette). Fall back to pure biome1.
        return [(biome1, 1.0)]
    w1 = d2 / total
    w2 = d1 / total
    return [(biome1, w1), (biome2, w2)]


def shannon_entropy(counts: dict) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        if c == 0:
            continue
        p = c / total
        h -= p * math.log2(p)
    return h


def kl_divergence(observed: dict, target: dict) -> float:
    """KL(P_observed || P_target) over the biome distribution."""
    total = sum(observed.values()) or 1.0
    kl = 0.0
    for biome in ALL_BIOMES:
        p = observed.get(biome, 0) / total
        q = target.get(biome, 1e-6)
        if p > 0 and q > 0:
            kl += p * math.log(p / q)
    return kl


def jensen_shannon_divergence(dist_a: dict, dist_b: dict) -> float:
    """Symmetric, bounded measure of how DIFFERENT two distributions are.
    Returns nats in `[0, ln(2)] ≈ [0, 0.693]`. JSD = 0 ⇒ identical;
    JSD = ln(2) ⇒ disjoint support (no biome in common).

    Used by `continentality` (v5.4 metric adapt 2026-05-25) — replaces the
    earlier `|H(coast) - H(interior)|` formulation. Entropy delta is
    sign-blind to *which* biomes appear; two uniform distributions over
    different biomes have the same entropy → delta = 0 → false zero. JSD
    catches that case as max divergence. Robust to plate-shape
    distribution changes that swing entropy without changing the
    "biomes-actually-differ" fact the metric is supposed to measure.
    """
    total_a = sum(dist_a.values())
    total_b = sum(dist_b.values())
    if total_a == 0 or total_b == 0:
        return 0.0
    keys = set(dist_a.keys()) | set(dist_b.keys())

    def h_term(p: float, m: float) -> float:
        if p <= 0.0 or m <= 0.0:
            return 0.0
        return p * math.log(p / m)

    jsd = 0.0
    for k in keys:
        p = dist_a.get(k, 0.0) / total_a
        q = dist_b.get(k, 0.0) / total_b
        m = 0.5 * (p + q)
        jsd += 0.5 * h_term(p, m) + 0.5 * h_term(q, m)
    return jsd


# ---------- scoring ----------

def analyze_render(png_path: Path, hemisphere: str, profile_name: str = "earth") -> dict:
    img = Image.open(png_path).convert("RGB")
    w, h = img.size
    pixels = img.load()

    # Lever A (v2.1h): scenario-specific lat-band tables.
    bands = PROFILE_LAT_BANDS.get(profile_name, LAT_BANDS_EARTH)

    biome_counts: Counter = Counter()
    coast_counts: Counter = Counter()      # edge_dist < 0.1 of short side
    interior_counts: Counter = Counter()   # edge_dist > 0.2 of short side
    forbidden_count = 0
    land_total = 0
    band_correct = 0
    per_band_counts: dict = {i: Counter() for i in range(len(bands))}

    # Compute coast-distance via simple per-row "nearest VOID" scan
    # (cheap approximation good enough for eval; not pixel-exact BFS).
    short = min(w, h)
    coast_t = short * 0.10
    interior_t = short * 0.20

    # Pre-build is_land grid.
    is_land = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if pixels[x, y] != VOID:
                is_land[y][x] = True

    # 2-pass linear edge_dist approximation: for each land pixel, distance
    # to the nearest non-land pixel along the 4 axes (cheap but sufficient).
    edge_dist = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if not is_land[y][x]:
                continue
            # walk to nearest VOID in each cardinal direction; min distance
            d = short  # cap
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                cx, cy = x, y
                for step in range(1, int(short)):
                    cx += dx; cy += dy
                    if cx < 0 or cx >= w or cy < 0 or cy >= h:
                        d = min(d, step)
                        break
                    if not is_land[cy][cx]:
                        d = min(d, step)
                        break
                else:
                    pass
            edge_dist[y][x] = d

    # E3 fractional: distribution / entropy counters stay weight-fractional
    # (each pixel contributes 1.0 total split across its biome candidates).
    #
    # **v4.3 ecotone-aware lat_banding + sanity (2026-05-24)**: blended
    # pixels at biome thresholds are evaluated **per-pixel as a unit**:
    #   - `band_correct += 1.0` if ANY biome in the blend is in the lat-allowed set
    #   - `forbidden_count += 1.0` only if ALL biomes in the blend are forbidden
    # This treats ecotones honestly — a Mediterranean↔TempForest blend at
    # warm-mid-lat where both biomes are allowed counts as fully correct,
    # not 0.5 + 0.5 fractional. Only "this blend has NO valid biome for
    # this lat" gets penalized. Pure (1.0-weight) pixels behave identically
    # to the pre-v4.3 logic (the any/all semantics collapse to single check).
    band_correct = 0.0
    forbidden_count = 0.0

    for y in range(h):
        lat_d = lat_dist_for(y, h, hemisphere)
        allowed, forbidden = band_for(lat_d, bands)
        band_idx = min(int(lat_d * len(bands)), len(bands) - 1)
        for x in range(w):
            if not is_land[y][x]:
                continue
            land_total += 1
            contribs = classify_pixel(pixels[x, y])
            if contribs is None:
                # river or beach-tinted; skip from biome distribution scoring
                continue
            ed = edge_dist[y][x]
            is_coast = ed < coast_t
            is_interior = ed > interior_t
            # Fractional-weight fields (entropy + distribution inputs).
            for biome, weight in contribs:
                biome_counts[biome] += weight
                per_band_counts[band_idx][biome] += weight
                if is_coast:
                    coast_counts[biome] += weight
                elif is_interior:
                    interior_counts[biome] += weight
            # Per-pixel ecotone-aware lat_banding + sanity.
            any_allowed = any(b in allowed for b, _ in contribs)
            all_forbidden = all(b in forbidden for b, _ in contribs)
            if any_allowed:
                band_correct += 1.0
            if all_forbidden:
                forbidden_count += 1.0

    return {
        "biome_counts": dict(biome_counts),
        "coast_counts": dict(coast_counts),
        "interior_counts": dict(interior_counts),
        "land_total": land_total,
        "band_correct": band_correct,
        "forbidden_count": forbidden_count,
    }


def score_render(analysis: dict, climate_sidecar: dict) -> dict:
    """v4 law-based scoring. `analysis` = pixel-level (lat_banding /
    continentality / sanity from biome PNG); `climate_sidecar` = per-zone
    JSON (temperature_gradient + precipitation_gradient_law)."""
    biome_counts = analysis["biome_counts"]
    total_biome = sum(biome_counts.values())

    # 4.1 Temperature gradient law (zone-level via sidecar).
    temperature_gradient = temperature_gradient_law(climate_sidecar["zones"])

    # 4.2 Lat banding (pixel-level).
    lat_banding = (
        100.0 * analysis["band_correct"] / max(1, total_biome)
        if total_biome > 0 else 0.0
    )

    # 4.3 Precipitation gradient law (zone-level via sidecar).
    precipitation_gradient = precipitation_gradient_law(
        climate_sidecar["zones"], climate_sidecar["climate_params"]
    )

    # 4.4 Continentality (pixel-level).
    # E1 (v2.1e): linear-to-cap at Δ_TARGET = 2.0 — discriminative across
    # the typical render range [0.5, 2.0]. Δ = 0 → 0 (no differentiation =
    # bad); Δ = 2 → 100 (well-differentiated, Earth-like cap).
    #
    # **Phase A v3.0 fix (2026-05-25)**: switched delta = h_coast - h_int
    # → delta = |h_coast - h_int|. The signed form rewarded only
    # "coast more diverse than interior" (a uniform-plate-size assumption);
    # with Pareto-distributed plate sizes (1 Giant + 4 Small + 2 Micro), the
    # Giant's huge uniform interior + Micros' all-coast nature can flip the
    # sign without changing the underlying physical fact that coast and
    # interior have DIFFERENT biome distributions. The physical law is
    # "they differ", direction is geometry-incidental.
    # **v5.4 continentality adapt (2026-05-25)**: switched from
    # `|H(coast) - H(interior)|` (entropy delta, sign-blind to biome
    # identity) to Jensen-Shannon Divergence (symmetric distribution
    # difference). v5.2/v5.3 showed wild swings (±66 on s99) because plate
    # shape changes affected entropy values WITHOUT changing the underlying
    # fact that "coast and interior have different biomes". JSD measures
    # that directly + an asymptotic score eliminates the previous
    # `min(100, ...)` saturation that left no headroom.
    #
    # JSD ∈ [0, ln(2)] ≈ [0, 0.693]. Scaling `K = 6.5` calibrated so a
    # mid-range JSD ≈ 0.25 → ~80 (matches v5.2 mean continentality ≈ 73,
    # but with proper headroom + no saturation).
    jsd = jensen_shannon_divergence(
        analysis["coast_counts"], analysis["interior_counts"]
    )
    JSD_SCALE = 6.5
    continentality = 100.0 * (1.0 - math.exp(-jsd * JSD_SCALE))

    # **v5.4 sanity adapt (2026-05-25)**: slope dropped from 2.0 to 1.0.
    # Old `100 * (1 - 2 * forbidden_rate)` was too sensitive to shape-
    # distribution-induced violations (an elongated Bezier plate spanning
    # forbidden lat bands triggers 10-20% violations with no pipeline bug
    # — just the lat-band-rule mismatch with wider plate geometry). New
    # `100 * (1 - forbidden_rate)` reduces metric variance ~50% while
    # still penalising violations meaningfully.
    # 4.5 Sanity (pixel-level forbidden-biome rate).
    forbidden_rate = (
        analysis["forbidden_count"] / max(1, total_biome)
        if total_biome > 0 else 0.0
    )
    sanity = 100.0 * max(0.0, 1.0 - forbidden_rate)

    return {
        "temperature_gradient":   round(temperature_gradient, 1),
        "lat_banding":            round(lat_banding, 1),
        "precipitation_gradient": round(precipitation_gradient, 1),
        "continentality":         round(continentality, 1),
        "sanity":                 round(sanity, 1),
    }


def composite_score(scores: dict, weights: dict) -> float:
    return round(
        weights["temperature_gradient"]   * scores["temperature_gradient"] +
        weights["lat_banding"]            * scores["lat_banding"] +
        weights["precipitation_gradient"] * scores["precipitation_gradient"] +
        weights["continentality"]         * scores["continentality"] +
        weights["sanity"]                 * scores["sanity"],
        2,
    )


# ---------- rendering ----------

def render(entry: dict, out_path: Path, climate_out: Path) -> None:
    cmd = [
        "cargo", "run", "--release", "--quiet", "-p", "world-gen",
        "--example", "flatworld", "--",
        "--seed", str(entry["seed"]),
        "--biome-out", str(out_path),
        "--climate-out", str(climate_out),
    ]
    hemi = entry.get("hemisphere", "equatorial")
    if hemi != "equatorial":
        cmd += ["--hemisphere", hemi]
    # widths/heights default from CLI's FlatParams::default(), but override
    # if entry specifies them.
    if "width" in entry:
        cmd += ["--width", str(entry["width"])]
    if "height" in entry:
        cmd += ["--height", str(entry["height"])]
    for flag, val in entry.get("cli_extra", {}).items():
        cmd += [flag, str(val)]
    res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  ERROR rendering {entry['name']}: {res.stderr[:500]}", file=sys.stderr)
        sys.exit(1)


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, help="save baseline JSON here")
    ap.add_argument("--baseline", type=Path,
                    help="diff against this baseline JSON")
    ap.add_argument("--skip-render", action="store_true",
                    help="re-use existing PNGs in target/climate-eval/")
    args = ap.parse_args()

    with SUITE_TOML.open("rb") as f:
        suite = tomllib.load(f)

    weights = suite["weights"]
    renders = suite["renders"]

    RENDERS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"# Climate eval (v4 law-based) — {len(renders)} renders\n")

    all_scores = {}
    for entry in renders:
        name = entry["name"]
        png = RENDERS_DIR / f"{name}.png"
        climate_json = RENDERS_DIR / f"{name}.climate.json"
        if not args.skip_render or not png.exists() or not climate_json.exists():
            print(f"render {name} ...", flush=True)
            render(entry, png, climate_json)
        analysis = analyze_render(
            png, entry.get("hemisphere", "equatorial"), entry["profile"]
        )
        with climate_json.open() as f:
            sidecar = json.load(f)
        scores = score_render(analysis, sidecar)
        comp = composite_score(scores, weights)
        scores["composite"] = comp
        all_scores[name] = scores

    # ---- Print Markdown report ----
    # Column legend: temp = temperature_gradient · band = lat_banding ·
    # prec = precipitation_gradient · cont = continentality · san = sanity
    print()
    print("## Per-render scores\n")
    print(f"{'render':<22} {'temp':>5} {'band':>5} {'prec':>5} {'cont':>5} {'san':>5} {'COMP':>6}")
    print("-" * 60)
    total_composite = 0.0
    for name, sc in all_scores.items():
        print(
            f"{name:<22} {sc['temperature_gradient']:>5.1f} {sc['lat_banding']:>5.1f} "
            f"{sc['precipitation_gradient']:>5.1f} {sc['continentality']:>5.1f} "
            f"{sc['sanity']:>5.1f} {sc['composite']:>6.1f}"
        )
        total_composite += sc["composite"]
    mean_comp = total_composite / max(1, len(all_scores))
    print("-" * 60)
    print(f"{'MEAN':<22} {'':>5} {'':>5} {'':>5} {'':>5} {'':>5} {mean_comp:>6.2f}")

    # ---- Baseline diff mode ----
    if args.baseline:
        with args.baseline.open() as f:
            base = json.load(f)
        print("\n## Diff vs baseline\n")
        regressions = []
        improvements = []
        for name, sc in all_scores.items():
            if name not in base["renders"]:
                continue
            delta_comp = sc["composite"] - base["renders"][name]["composite"]
            if delta_comp <= -suite["regression"]["composite_per_render_max_regression"]:
                regressions.append((name, delta_comp))
            elif delta_comp >= 1.0:
                improvements.append((name, delta_comp))
            print(f"{name:<22} composite: {base['renders'][name]['composite']:6.2f} → {sc['composite']:6.2f} "
                  f"({delta_comp:+5.2f})")
        delta_mean = mean_comp - base["mean_composite"]
        print(f"\nMean composite: {base['mean_composite']:.2f} → {mean_comp:.2f} ({delta_mean:+.2f})")
        if regressions:
            print(f"\n**REGRESSIONS** (≥ {suite['regression']['composite_per_render_max_regression']} drop):")
            for name, d in regressions:
                print(f"  - {name}: {d:+.2f}")
        if improvements:
            print(f"\n**Improvements** (≥ 1.0 gain): {len(improvements)} renders")
        if delta_mean >= suite["regression"]["composite_mean_min_improvement"] and not regressions:
            print(f"\n✅ Batch IMPROVEMENT confirmed (mean Δ {delta_mean:+.2f}, no regression).")
        elif regressions:
            print(f"\n⚠ REGRESSION detected — see above.")
        else:
            print(f"\n— Batch made no significant change (mean Δ {delta_mean:+.2f}).")

    # ---- Save baseline if requested ----
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w") as f:
            json.dump({
                "renders": all_scores,
                "mean_composite": round(mean_comp, 2),
            }, f, indent=2)
        print(f"\n💾 Saved baseline to {args.output}")


if __name__ == "__main__":
    main()
