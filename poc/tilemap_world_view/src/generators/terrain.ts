import type { TileMapSkeleton, TerrainKind, ZoneSpec } from '../data/types';
import { terrainToIndex } from '../data/types';
import { valueNoise2D, fbm2D } from './noise';

/**
 * L2 — Procedural terrain generator.
 *
 * Input: L1 skeleton (zones + biome weights) + deterministic seed.
 * Output: flattened terrain grid (length = width × height; values are TerrainKind index).
 *
 * Algorithm per zone:
 *   1. Compute fBm value-noise at (x/scale, y/scale) — produces 0..1 spatial gradient
 *   2. Map noise value to TerrainKind via cumulative biome-weight distribution
 *   3. Tiles outside any zone default to Grass
 *
 * Determinism: pure function of (skeleton, seed). Same input → byte-identical output.
 * Tested in `tests/generators.test.ts`.
 */
export function generateTerrain(skeleton: TileMapSkeleton, seed: number): number[] {
  const { width, height } = skeleton.grid_size;
  const noise = valueNoise2D(seed);
  const tiles = new Array<number>(width * height);

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const zone = findZoneAt(skeleton, x, y);
      const scale = zone?.noise_scale ?? 8;
      const octaves = zone?.noise_octaves ?? 3;
      const noiseValue = fbm2D(noise, x / scale, y / scale, octaves);
      const terrain = pickTerrainFromZone(zone, noiseValue);
      tiles[y * width + x] = terrainToIndex(terrain);
    }
  }
  return tiles;
}

function findZoneAt(skeleton: TileMapSkeleton, x: number, y: number): ZoneSpec | null {
  // First-match wins. Authors writing skeletons should order zones from most-specific
  // to most-general to leverage this. V2: explicit z-order field on ZoneSpec.
  for (const zone of skeleton.terrain_zones) {
    const b = zone.shape.bounds;
    if (x >= b.x && x < b.x + b.w && y >= b.y && y < b.y + b.h) {
      return zone;
    }
  }
  return null;
}

function pickTerrainFromZone(zone: ZoneSpec | null, noiseValue: number): TerrainKind {
  if (!zone) return 'Grass';

  const entries = Object.entries(zone.biome_weights) as [TerrainKind, number][];
  if (entries.length === 0) return 'Grass';

  const total = entries.reduce((sum, [, w]) => sum + w, 0);
  if (total <= 0) return 'Grass';

  // Cumulative distribution; noise value (0..1) maps to terrain band
  const clamped = Math.max(0, Math.min(0.9999, noiseValue));
  let acc = 0;
  for (const [kind, weight] of entries) {
    acc += weight / total;
    if (clamped < acc) return kind;
  }
  return entries[entries.length - 1][0];
}
