"""Climate eval — objective quality measurement for the flatworld biome
renderer.

Loads `eval/climate-eval-suite.toml`, renders each entry via
`cargo run --release -p world-gen --example flatworld`, computes 5
sub-scores per render (per `docs/plans/2026-05-23-climate-eval-references.md`)
and outputs a JSON + Markdown report.

Usage:
  python scripts/climate_eval.py
       → render + score; print Markdown report to stdout
  python scripts/climate_eval.py --output eval/baselines/v2.1a.json
       → also save scores as JSON baseline for future diffs
  python scripts/climate_eval.py --baseline eval/baselines/v2.1a.json
       → compute current scores + diff against baseline + print regression
         report (used after every batch to decide improvement / regression)

Replaces subjective rating ("eq_seed42 is 7/10") with objective composite
("eq_seed42 composite = 64.3, baseline 51.2 → +13.1, no sub-score regressed
by >5"). See doc §6 for sanity-check methodology.
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

# Biome color → name. Must mirror `Biome::color()` in flat_climate.rs at the
# current commit; W7 v2.1a colors (HotDesert reddish, WET_SAND cooler).
BIOME_COLORS = {
    (232, 238, 242): "Ice",
    (184, 183, 174): "Tundra",
    (74, 107, 71):   "BorealForest",
    (79, 139, 65):   "TemperateForest",
    (184, 180, 90):  "TempGrassland",  # alias for TemperateGrassland
    (216, 144, 96):  "HotDesert",
    (201, 192, 74):  "Savanna",
    (15, 77, 26):    "TropicalRainforest",
}
# Map our short name → profile distribution key.
BIOME_PROFILE_KEY = {
    "Ice": "Ice", "Tundra": "Tundra", "BorealForest": "BorealForest",
    "TemperateForest": "TemperateForest", "TempGrassland": "TemperateGrassland",
    "HotDesert": "HotDesert", "Savanna": "Savanna",
    "TropicalRainforest": "TropicalRainforest",
}
ALL_BIOMES = list(BIOME_PROFILE_KEY.values())

VOID = (12, 16, 28)
# Lat banding allowed/forbidden per refs doc §2.3.
LAT_BANDS = [
    # (lat_dist_lo, lat_dist_hi, allowed_set, forbidden_set)
    (0.00, 0.20,
     {"TropicalRainforest", "Savanna", "HotDesert"},
     {"Ice", "Tundra", "BorealForest"}),
    (0.20, 0.40,
     {"HotDesert", "Savanna", "TemperateForest", "TemperateGrassland"},
     {"Ice", "Tundra"}),
    (0.40, 0.60,
     {"TemperateForest", "TemperateGrassland", "HotDesert", "BorealForest"},
     {"TropicalRainforest"}),
    (0.60, 0.80,
     {"BorealForest", "TemperateGrassland", "Tundra"},
     {"TropicalRainforest", "Savanna", "HotDesert"}),
    (0.80, 1.00,
     {"Tundra", "Ice", "BorealForest"},
     {"TropicalRainforest", "Savanna", "HotDesert"}),
]


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


def band_for(lat_dist: float):
    for lo, hi, allowed, forbidden in LAT_BANDS:
        if lo <= lat_dist <= hi:
            return allowed, forbidden
    return LAT_BANDS[-1][2], LAT_BANDS[-1][3]


def classify_pixel(rgb: tuple) -> str | None:
    """Return short biome name, or None for ocean/beach-tinted/river pixels.

    Currently EXACT-MATCH only. Beach-tinted pixels (W4 blend of biome × sand
    color) are intentionally `None` — they're a coast-band feature, not a
    biome reading, and including them distorts the biome distribution.
    Rivers are also `None`.

    **W5 v2.1d caveat**: when Whittaker hue interpolation ships, pixels near
    a biome threshold will have blended colors that won't match canonically.
    THAT batch must extend this classifier with nearest-neighbor matching
    against a curated set of (biome_a, biome_b) blend midpoints (NOT just
    nearest in RGB space — beach-tints would also classify and distort).
    Tracked in doc §10 v2.1e known limit.
    """
    if rgb == VOID:
        return None
    return BIOME_COLORS.get(rgb)


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


# ---------- scoring ----------

def analyze_render(png_path: Path, hemisphere: str) -> dict:
    img = Image.open(png_path).convert("RGB")
    w, h = img.size
    pixels = img.load()

    biome_counts: Counter = Counter()
    coast_counts: Counter = Counter()      # edge_dist < 0.1 of short side
    interior_counts: Counter = Counter()   # edge_dist > 0.2 of short side
    forbidden_count = 0
    land_total = 0
    band_correct = 0
    per_band_counts: dict = {i: Counter() for i in range(len(LAT_BANDS))}

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

    for y in range(h):
        lat_d = lat_dist_for(y, h, hemisphere)
        allowed, forbidden = band_for(lat_d)
        band_idx = min(int(lat_d * len(LAT_BANDS)), len(LAT_BANDS) - 1)
        for x in range(w):
            if not is_land[y][x]:
                continue
            land_total += 1
            biome = classify_pixel(pixels[x, y])
            if biome is None:
                # river or beach-tinted; skip from biome distribution scoring
                continue
            biome_counts[biome] += 1
            per_band_counts[band_idx][biome] += 1
            if biome in allowed:
                band_correct += 1
            if biome in forbidden:
                forbidden_count += 1
            # Coast vs interior buckets.
            ed = edge_dist[y][x]
            if ed < coast_t:
                coast_counts[biome] += 1
            elif ed > interior_t:
                interior_counts[biome] += 1

    return {
        "biome_counts": dict(biome_counts),
        "coast_counts": dict(coast_counts),
        "interior_counts": dict(interior_counts),
        "land_total": land_total,
        "band_correct": band_correct,
        "forbidden_count": forbidden_count,
    }


def score_render(analysis: dict, profile: dict) -> dict:
    biome_counts = analysis["biome_counts"]
    land_total = analysis["land_total"]
    total_biome = sum(biome_counts.values())
    if total_biome == 0:
        return {
            "distribution": 0.0, "lat_banding": 0.0,
            "continentality": 0.0, "diversity": 0.0, "sanity": 0.0,
        }

    # 4.1 Distribution: 100 × exp(-KL).
    kl = kl_divergence(biome_counts, profile["distribution"])
    distribution = 100.0 * math.exp(-kl)

    # 4.2 Lat banding.
    lat_banding = 100.0 * analysis["band_correct"] / max(1, total_biome)

    # 4.3 Continentality (Δ entropy coast vs interior).
    # E1 fix (v2.1e): old formula `clamp(50 + 50×Δ, 0, 100)` saturated at 100
    # because Δ ≥ 1.0 was universal (the eval's aggregate-coast-vs-aggregate-
    # interior naturally has high Δ). New formula is linear-to-cap, peaking
    # at Δ_TARGET = 2.0 — Δ = 0 → 0 (no differentiation = bad), Δ = 1 → 50,
    # Δ = 2 → 100 (well-differentiated, Earth-like cap), Δ > 2 → still 100.
    # Now discriminative across the typical render range [0.5, 2.0].
    h_coast = shannon_entropy(analysis["coast_counts"])
    h_int   = shannon_entropy(analysis["interior_counts"])
    delta   = h_coast - h_int
    DELTA_TARGET = 2.0
    continentality = max(0.0, min(100.0, 100.0 * delta / DELTA_TARGET))

    # 4.4 Diversity vs Earth entropy (~2.7 bits with 8 biomes).
    h_obs = shannon_entropy(biome_counts)
    diversity = 100.0 * min(1.0, h_obs / 2.7)

    # 4.5 Sanity (forbidden-biome penalty).
    forbidden_rate = analysis["forbidden_count"] / max(1, total_biome)
    sanity = 100.0 * max(0.0, 1.0 - 2.0 * forbidden_rate)

    return {
        "distribution":   round(distribution, 1),
        "lat_banding":    round(lat_banding, 1),
        "continentality": round(continentality, 1),
        "diversity":      round(diversity, 1),
        "sanity":         round(sanity, 1),
    }


def composite_score(scores: dict, weights: dict) -> float:
    return round(
        weights["distribution"]   * scores["distribution"] +
        weights["lat_banding"]    * scores["lat_banding"] +
        weights["continentality"] * scores["continentality"] +
        weights["diversity"]      * scores["diversity"] +
        weights["sanity"]         * scores["sanity"],
        2,
    )


# ---------- rendering ----------

def render(entry: dict, out_path: Path) -> None:
    cmd = [
        "cargo", "run", "--release", "--quiet", "-p", "world-gen",
        "--example", "flatworld", "--",
        "--seed", str(entry["seed"]),
        "--biome-out", str(out_path),
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
    profiles = suite["profiles"]
    renders = suite["renders"]

    RENDERS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"# Climate eval — {len(renders)} renders\n")

    all_scores = {}
    for entry in renders:
        name = entry["name"]
        png = RENDERS_DIR / f"{name}.png"
        if not args.skip_render or not png.exists():
            print(f"render {name} ...", flush=True)
            render(entry, png)
        analysis = analyze_render(png, entry.get("hemisphere", "equatorial"))
        profile = profiles[entry["profile"]]
        scores = score_render(analysis, profile)
        comp = composite_score(scores, weights)
        scores["composite"] = comp
        all_scores[name] = scores

    # ---- Print Markdown report ----
    print()
    print("## Per-render scores\n")
    print(f"{'render':<22} {'dist':>5} {'band':>5} {'cont':>5} {'div':>5} {'san':>5} {'COMP':>6}")
    print("-" * 60)
    total_composite = 0.0
    for name, sc in all_scores.items():
        print(
            f"{name:<22} {sc['distribution']:>5.1f} {sc['lat_banding']:>5.1f} "
            f"{sc['continentality']:>5.1f} {sc['diversity']:>5.1f} "
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
