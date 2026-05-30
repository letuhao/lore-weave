#!/usr/bin/env python3
"""Biome histogram for a world-gen map.json — calibration aid (session 100, Köppen).

Usage: python scripts/biome_histogram.py <map.json>
Prints each biome's share of ALL cells and of LAND cells (excluding Ocean/Lake),
plus the headline Desert-share-of-land the Köppen calibration targets (30-40%).
"""
import json
import sys
from collections import Counter

WATER = {"Ocean", "Lake"}

def main(path: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        m = json.load(f)
    biomes = m["biome"]
    total = len(biomes)
    counts = Counter(biomes)
    land = total - sum(counts[w] for w in WATER)
    print(f"file: {path}  seed={m.get('seed')}  scale={m.get('scale')}  cells={total}  land={land}")
    print(f"{'biome':<10} {'count':>8} {'%all':>7} {'%land':>7}")
    for b, c in counts.most_common():
        pa = 100.0 * c / total if total else 0.0
        pl = 100.0 * c / land if land and b not in WATER else float("nan")
        pl_s = f"{pl:6.1f}" if pl == pl else "    --"
        print(f"{b:<10} {c:>8} {pa:6.1f} {pl_s}")
    desert = counts.get("Desert", 0)
    print(f"\nDESERT %land = {100.0*desert/land:.1f}%  (target 30-40)" if land else "no land")

if __name__ == "__main__":
    main(sys.argv[1])
