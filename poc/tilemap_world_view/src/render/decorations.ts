import type { TileMapView } from '../data/types';
import { indexToTerrain } from '../data/types';
import { hash2D } from '../generators/prng';
import { DECORATION_RULES, type TileIndex } from './kenney_atlas';

export interface DecorationPlacement {
  x: number;
  y: number;
  sprite: TileIndex;
}

/**
 * Procedural decoration scatter — pure function of (view, seed).
 *
 * For each tile, deterministically decides:
 *   1. Should this tile have ANY decoration? (per-terrain base_chance)
 *   2. If yes, which decoration? (weighted random)
 *
 * Determinism: hash2D(x, y, seed) drives all decisions. Same input → same output.
 * Tested by replay-determinism property in tests/generators.test.ts (V2 will add explicit test).
 *
 * Skip tiles that:
 *   - Are road tiles (terrain=Road) — keep paths clean
 *   - Have an object_placement on them (cell anchor / landmark) — avoid overlap
 *   - Have a road waypoint — avoid breaking road continuity
 */
export function generateDecorations(view: TileMapView): DecorationPlacement[] {
  const seed = view.procedural_seed;
  const { width, height } = view.grid_size;

  // Build occupied-tile set so decorations don't overlap with cells/landmarks/road waypoints
  const occupied = new Set<string>();
  for (const cell of view.cell_placements) {
    occupied.add(`${cell.position.x},${cell.position.y}`);
    // Also reserve a 1-tile halo around cells for visual breathing room
    for (const dx of [-1, 0, 1]) {
      for (const dy of [-1, 0, 1]) {
        occupied.add(`${cell.position.x + dx},${cell.position.y + dy}`);
      }
    }
  }
  for (const obj of view.object_placements) {
    occupied.add(`${obj.position.x},${obj.position.y}`);
  }
  for (const road of view.roads) {
    for (const wp of road.waypoints) {
      occupied.add(`${wp.x},${wp.y}`);
    }
  }

  const placements: DecorationPlacement[] = [];

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const key = `${x},${y}`;
      if (occupied.has(key)) continue;

      const terrain = indexToTerrain(view.terrain_layer[y * width + x]);
      const rules = DECORATION_RULES[terrain];
      if (!rules || rules.length === 0) continue;

      // Decision 1: should this tile have any decoration?
      // Use distinct hash channels for spawn vs choice so they vary independently
      const spawnRoll = hash2D(x, y, seed);
      // Take the first rule's base_chance as terrain-wide; rules per terrain share chance
      const baseChance = rules[0].base_chance;
      if (spawnRoll >= baseChance) continue;

      // Decision 2: which decoration?
      const choiceRoll = hash2D(x * 7 + 1, y * 13 + 3, seed);
      const totalWeight = rules.reduce((s, r) => s + r.weight, 0);
      let acc = 0;
      let picked = rules[0].sprite;
      for (const rule of rules) {
        acc += rule.weight / totalWeight;
        if (choiceRoll < acc) {
          picked = rule.sprite;
          break;
        }
      }

      placements.push({ x, y, sprite: picked });
    }
  }

  return placements;
}
