"""Quick analyzer for biome PNG sweeps.

For each PNG, classifies pixels by Biome color (matching `Biome::color()` in
flat_climate.rs), reports:
  - pixel count per biome
  - "land" total (= non-VOID pixels)
  - Ice%, Tundra%, Forest% (sum of all forest), Desert%, etc.
  - distinct biome count
  - "polar half uniformity" = max-biome-pct in the polar half of the map

Usage:
  python target/sweep_analyze.py target/sweep-t-pole/
"""

import sys
from pathlib import Path
from PIL import Image
from collections import Counter

# Mirror Biome::color() from flat_climate.rs
BIOME_COLORS = {
    (232, 238, 242): "Ice",
    (184, 183, 174): "Tundra",
    (74, 107, 71):   "BorealForest",
    (79, 139, 65):   "TempForest",
    (184, 180, 90):  "TempGrass",
    (216, 176, 112): "HotDesert",
    (201, 192, 74):  "Savanna",
    (15, 77, 26):    "TropRainforest",
}
VOID  = (12, 16, 28)
# Beach sand colors — anything along that gradient is "beach".
# Beach is wet-sand → dry-sand lerp: (196,178,132) → (230,214,165).
def is_beach(c):
    r, g, b = c
    return 195 <= r <= 232 and 175 <= g <= 215 and 130 <= b <= 167 and c not in BIOME_COLORS
# Rivers (blue tones)
def is_river(c):
    r, g, b = c
    return b > 130 and b > r + 20 and b > g + 10

def classify(c):
    if c == VOID: return "Void"
    if c in BIOME_COLORS: return BIOME_COLORS[c]
    if is_river(c): return "River"
    if is_beach(c): return "Beach"
    return "Other"

def analyze(path):
    img = Image.open(path).convert("RGB")
    W, H = img.size
    pixels = list(img.getdata())
    n = W * H

    counts = Counter(classify(p) for p in pixels)

    # Polar-half uniformity: top half (y < H/2 for NorthOnly = equator)
    # actually for NorthOnly, y=H is pole. So polar half = bottom half.
    polar_pixels = [classify(p) for j, p in enumerate(pixels) if j // W >= H // 2]
    polar_counts = Counter(polar_pixels)
    polar_land = sum(c for k, c in polar_counts.items() if k not in ("Void", "River"))
    if polar_land == 0:
        polar_unif = 0.0
        polar_dominant = "—"
    else:
        polar_dominant, dom_count = polar_counts.most_common(1)[0]
        if polar_dominant in ("Void", "River"):
            # take second
            for k, c in polar_counts.most_common(3):
                if k not in ("Void", "River"):
                    polar_dominant, dom_count = k, c
                    break
        polar_unif = dom_count / polar_land if polar_land > 0 else 0

    land = n - counts.get("Void", 0) - counts.get("River", 0)
    if land == 0: land = 1

    biome_only = {k: v for k, v in counts.items() if k in BIOME_COLORS.values()}
    distinct_biomes = len(biome_only)

    def pct(k):
        return 100.0 * counts.get(k, 0) / land

    return {
        "path": path.name,
        "ice_pct": pct("Ice"),
        "tundra_pct": pct("Tundra"),
        "boreal_pct": pct("BorealForest"),
        "tempforest_pct": pct("TempForest"),
        "tempgrass_pct": pct("TempGrass"),
        "hotdesert_pct": pct("HotDesert"),
        "savanna_pct": pct("Savanna"),
        "rainforest_pct": pct("TropRainforest"),
        "beach_pct": pct("Beach"),
        "distinct_biomes": distinct_biomes,
        "polar_dominant": polar_dominant,
        "polar_uniformity": polar_unif * 100,
    }

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    folder = Path(sys.argv[1])
    pngs = sorted(folder.glob("*.png"))
    if not pngs:
        print(f"No PNGs in {folder}")
        sys.exit(1)

    print(f"{'file':<28} {'Ice%':>5} {'Tnd%':>5} {'Bor%':>5} {'TFo%':>5} {'TGr%':>5} {'HDs%':>5} {'Sav%':>5} {'RFr%':>5} {'Bch%':>5} {'#Bm':>3} {'PolDom':>14} {'PolUnif%':>9}")
    print("-" * 130)
    for p in pngs:
        r = analyze(p)
        print(f"{r['path']:<28} {r['ice_pct']:>5.1f} {r['tundra_pct']:>5.1f} {r['boreal_pct']:>5.1f} {r['tempforest_pct']:>5.1f} {r['tempgrass_pct']:>5.1f} {r['hotdesert_pct']:>5.1f} {r['savanna_pct']:>5.1f} {r['rainforest_pct']:>5.1f} {r['beach_pct']:>5.1f} {r['distinct_biomes']:>3} {r['polar_dominant']:>14} {r['polar_uniformity']:>8.1f}")

if __name__ == "__main__":
    main()
