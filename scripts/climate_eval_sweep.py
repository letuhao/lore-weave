"""E3 classifier sweep — measure W6 vs noW6 delta across (threshold, weighting)
configurations, to refine the fractional classifier.

Renders are pre-rendered into:
  target/climate-eval-w6/   — W6 enabled (zone-seam blend)
  target/climate-eval-noW6/ — W6 disabled (w1 forced to 1.0)

Cached approach (~20× faster than naive sweep):
  1. For each PNG, compute the expensive per-pixel features (is_land, edge_dist,
     lat_dist, band_idx, raw RGB) ONCE and cache.
  2. For each (threshold, weighting) config, walk the cached pixel data and
     apply the per-config classifier — cheap arithmetic only.
  3. Score + composite per config; print (W6_mean, noW6_mean, delta) matrix.
"""

from pathlib import Path
from collections import Counter
import math
import tomllib

from PIL import Image
import climate_eval as ce

REPO_ROOT = Path(__file__).resolve().parent.parent
SUITE_TOML = REPO_ROOT / "eval" / "climate-eval-suite.toml"
W6_DIR = REPO_ROOT / "target" / "climate-eval-w6"
NOW6_DIR = REPO_ROOT / "target" / "climate-eval-noW6"


def load_pixel_features(png_path: Path, hemisphere: str):
    """One-time per-PNG feature extraction. Returns dict with:
      w, h, land_rgb (list of (rgb, lat_d, band_idx, edge_dist)).
    Only includes LAND pixels (is_land == True). Skips the per-pixel
    classification — that runs per config.
    """
    img = Image.open(png_path).convert("RGB")
    w, h = img.size
    pixels = img.load()
    short = min(w, h)
    coast_t = short * 0.10
    interior_t = short * 0.20

    is_land = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if pixels[x, y] != ce.VOID:
                is_land[y][x] = True

    # Cardinal-walk edge distance (matches climate_eval.py implementation).
    edge_dist = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if not is_land[y][x]:
                continue
            d = short
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                cx, cy = x, y
                for step in range(1, int(short)):
                    cx += dx; cy += dy
                    if cx < 0 or cx >= w or cy < 0 or cy >= h:
                        d = min(d, step); break
                    if not is_land[cy][cx]:
                        d = min(d, step); break
            edge_dist[y][x] = d

    # Pre-compute lat_dist per row + band_idx, then flatten land pixels with
    # all per-pixel features classifier-independent.
    land_pixels = []
    for y in range(h):
        lat_d = ce.lat_dist_for(y, h, hemisphere)
        for x in range(w):
            if not is_land[y][x]:
                continue
            ed = edge_dist[y][x]
            land_pixels.append((pixels[x, y], lat_d, ed, x, y))

    return {
        "w": w, "h": h,
        "land_pixels": land_pixels,
        "coast_t": coast_t,
        "interior_t": interior_t,
        "land_total": len(land_pixels),
    }


def make_classifier(near_threshold: float, weighting: str):
    biome_colors_items = list(ce.BIOME_COLORS.items())
    beach_colors = ce.BEACH_COLORS
    beach_reject_sq = ce.BEACH_REJECT_DIST * ce.BEACH_REJECT_DIST
    near_sq = near_threshold * near_threshold

    def cls(rgb):
        # Skip VOID at caller; this is land-only.
        for bc in beach_colors:
            dr = rgb[0] - bc[0]; dg = rgb[1] - bc[1]; db = rgb[2] - bc[2]
            if dr * dr + dg * dg + db * db < beach_reject_sq:
                return None
        d1_sq = float("inf"); d2_sq = float("inf")
        b1 = None; b2 = None
        for color, biome in biome_colors_items:
            dr = rgb[0] - color[0]; dg = rgb[1] - color[1]; db = rgb[2] - color[2]
            d_sq = dr * dr + dg * dg + db * db
            if d_sq < d1_sq:
                d2_sq = d1_sq; b2 = b1
                d1_sq = d_sq; b1 = biome
            elif d_sq < d2_sq:
                d2_sq = d_sq; b2 = biome
        if d1_sq > near_sq:
            return None
        if d2_sq > near_sq or b2 is None:
            return [(b1, 1.0)]
        if weighting == "linear":
            d1 = math.sqrt(d1_sq); d2 = math.sqrt(d2_sq)
            tot = d1 + d2
            if tot < 1e-6:
                return [(b1, 1.0)]
            w1 = d2 / tot
        else:  # inv_sq
            tot = d1_sq + d2_sq
            if tot < 1e-6:
                return [(b1, 1.0)]
            w1 = d2_sq / tot
        return [(b1, w1), (b2, 1.0 - w1)]
    return cls


def analyze_with_classifier(features: dict, hemisphere: str, profile_name: str,
                             classifier):
    """Replays the cached land_pixels through `classifier`. Returns the same
    shape as climate_eval.analyze_render."""
    bands = ce.PROFILE_LAT_BANDS.get(profile_name, ce.LAT_BANDS_EARTH)
    biome_counts: Counter = Counter()
    coast_counts: Counter = Counter()
    interior_counts: Counter = Counter()
    band_correct = 0.0
    forbidden_count = 0.0
    coast_t = features["coast_t"]
    interior_t = features["interior_t"]

    for rgb, lat_d, ed, _x, _y in features["land_pixels"]:
        allowed, forbidden = ce.band_for(lat_d, bands)
        contribs = classifier(rgb)
        if contribs is None:
            continue
        is_coast = ed < coast_t
        is_interior = ed > interior_t
        for biome, weight in contribs:
            biome_counts[biome] += weight
            if biome in allowed:
                band_correct += weight
            if biome in forbidden:
                forbidden_count += weight
            if is_coast:
                coast_counts[biome] += weight
            elif is_interior:
                interior_counts[biome] += weight

    return {
        "biome_counts": dict(biome_counts),
        "coast_counts": dict(coast_counts),
        "interior_counts": dict(interior_counts),
        "land_total": features["land_total"],
        "band_correct": band_correct,
        "forbidden_count": forbidden_count,
    }


def score_dir_cached(cached: dict, suite: dict, classifier) -> float:
    """Mean composite using pre-cached per-render features + given classifier."""
    weights = suite["weights"]
    profiles = suite["profiles"]
    renders = suite["renders"]
    total = 0.0; n = 0
    for entry in renders:
        feat = cached[entry["name"]]
        analysis = analyze_with_classifier(
            feat, entry.get("hemisphere", "equatorial"),
            entry["profile"], classifier
        )
        scores = ce.score_render(analysis, profiles[entry["profile"]])
        comp = ce.composite_score(scores, weights)
        total += comp; n += 1
    return total / max(1, n)


def main():
    with SUITE_TOML.open("rb") as f:
        suite = tomllib.load(f)
    renders = suite["renders"]

    print(f"caching W6 features ({len(renders)} renders)...", flush=True)
    cached_w6 = {}
    for entry in renders:
        png = W6_DIR / f"{entry['name']}.png"
        cached_w6[entry["name"]] = load_pixel_features(
            png, entry.get("hemisphere", "equatorial")
        )
    print(f"caching noW6 features ({len(renders)} renders)...", flush=True)
    cached_no = {}
    for entry in renders:
        png = NOW6_DIR / f"{entry['name']}.png"
        cached_no[entry["name"]] = load_pixel_features(
            png, entry.get("hemisphere", "equatorial")
        )

    print()
    thresholds = [40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0]
    weightings = ["linear", "inv_sq"]

    print(f"{'threshold':>10} {'weighting':>8}   {'W6_mean':>8} {'noW6_mean':>10} {'delta':>8}")
    print("-" * 60)
    rows = []
    for th in thresholds:
        for wt in weightings:
            classifier = make_classifier(th, wt)
            w6 = score_dir_cached(cached_w6, suite, classifier)
            no = score_dir_cached(cached_no, suite, classifier)
            delta = w6 - no
            print(f"{th:>10.1f} {wt:>8}   {w6:>8.2f} {no:>10.2f} {delta:>+8.3f}", flush=True)
            rows.append((th, wt, w6, no, delta))
    print("-" * 60)
    best = max(rows, key=lambda r: r[4])
    print(f"\nBEST delta:  threshold={best[0]} weighting={best[1]}  "
          f"W6={best[2]:.2f} noW6={best[3]:.2f}  Δ={best[4]:+.3f}")


if __name__ == "__main__":
    main()
