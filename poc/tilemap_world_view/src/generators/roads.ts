import type { TileMapSkeleton, RoadSegment, TileCoord } from '../data/types';
import { indexToTerrain, terrainToIndex } from '../data/types';

/**
 * L2 — Road placement via A* pathfinding.
 *
 * Connects cell anchors per skeleton.road_connections using terrain-aware costs.
 * Mountain/Water are expensive (avoided); existing Road tiles are nearly free
 * (encourages road network reuse — like Roman highway grid).
 *
 * Side effect: terrain tiles along path are converted to Road kind (except Water,
 * which becomes "bridge" — kept Water for visual; V2 dedicated Bridge kind).
 *
 * Returns updated terrain array + structured RoadSegment list.
 */
export function placeRoads(
  skeleton: TileMapSkeleton,
  terrain: number[],
): { roads: RoadSegment[]; updatedTerrain: number[] } {
  const updated = [...terrain];
  const roads: RoadSegment[] = [];
  const { width, height } = skeleton.grid_size;
  const ROAD_IDX = terrainToIndex('Road');

  for (const conn of skeleton.road_connections) {
    const from = skeleton.cell_anchors.find((c) => c.channel_id === conn.from);
    const to = skeleton.cell_anchors.find((c) => c.channel_id === conn.to);
    if (!from || !to) continue;

    const path = aStar(from.position, to.position, width, height, updated);
    if (!path) continue;

    for (const p of path) {
      const idx = p.y * width + p.x;
      // Don't overwrite Water (would visually erase rivers/lakes); skip those tiles
      // — V2 adds dedicated Bridge tile kind. Cell anchor positions also kept (cell
      // marker overrides road visual).
      const isCellAnchor =
        (p.x === from.position.x && p.y === from.position.y) ||
        (p.x === to.position.x && p.y === to.position.y);
      if (indexToTerrain(updated[idx]) !== 'Water' && !isCellAnchor) {
        updated[idx] = ROAD_IDX;
      }
    }

    roads.push({
      from_channel_id: from.channel_id,
      to_channel_id: to.channel_id,
      waypoints: path,
      road_kind: conn.kind,
    });
  }

  return { roads, updatedTerrain: updated };
}

// ─── A* implementation ──────────────────────────────────────────────────────

function aStar(
  start: TileCoord,
  goal: TileCoord,
  w: number,
  h: number,
  terrain: number[],
): TileCoord[] | null {
  const key = (p: TileCoord): string => `${p.x},${p.y}`;
  const open = new Map<string, { p: TileCoord; g: number; f: number }>();
  const cameFrom = new Map<string, TileCoord>();
  const gScore = new Map<string, number>();
  const closed = new Set<string>();

  const startKey = key(start);
  open.set(startKey, { p: start, g: 0, f: heuristic(start, goal) });
  gScore.set(startKey, 0);

  let iterations = 0;
  const maxIterations = w * h * 4; // safety cap

  while (open.size > 0 && iterations++ < maxIterations) {
    // Pick lowest f-score (linear scan; fine for 64×64 grid; replace with heap V2)
    let currentKey = '';
    let currentEntry: { p: TileCoord; g: number; f: number } | null = null;
    for (const [k, v] of open) {
      if (!currentEntry || v.f < currentEntry.f) {
        currentEntry = v;
        currentKey = k;
      }
    }
    if (!currentEntry) break;

    if (currentEntry.p.x === goal.x && currentEntry.p.y === goal.y) {
      return reconstructPath(cameFrom, currentEntry.p, key);
    }

    open.delete(currentKey);
    closed.add(currentKey);

    for (const [dx, dy] of [
      [1, 0],
      [-1, 0],
      [0, 1],
      [0, -1],
    ]) {
      const nx = currentEntry.p.x + dx;
      const ny = currentEntry.p.y + dy;
      if (nx < 0 || nx >= w || ny < 0 || ny >= h) continue;
      const nKey = `${nx},${ny}`;
      if (closed.has(nKey)) continue;

      const cost = terrainCost(indexToTerrain(terrain[ny * w + nx]));
      const tentativeG = currentEntry.g + cost;
      const existingG = gScore.get(nKey) ?? Infinity;

      if (tentativeG < existingG) {
        cameFrom.set(nKey, currentEntry.p);
        gScore.set(nKey, tentativeG);
        open.set(nKey, {
          p: { x: nx, y: ny },
          g: tentativeG,
          f: tentativeG + heuristic({ x: nx, y: ny }, goal),
        });
      }
    }
  }

  return null;
}

function heuristic(a: TileCoord, b: TileCoord): number {
  // Manhattan distance — admissible for 4-connected grid
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
}

function terrainCost(t: string): number {
  switch (t) {
    case 'Mountain':
      return 8;
    case 'Forest':
      return 3;
    case 'Water':
      return 12;
    case 'Swamp':
      return 5;
    case 'Sand':
      return 2;
    case 'Snow':
      return 4;
    case 'Rough':
      return 4;
    case 'Road':
      return 0.4; // strongly favor existing roads
    case 'Subterranean':
      return 6;
    default: // Grass + fallback
      return 1;
  }
}

function reconstructPath(
  cameFrom: Map<string, TileCoord>,
  current: TileCoord,
  key: (p: TileCoord) => string,
): TileCoord[] {
  const path: TileCoord[] = [current];
  let k = key(current);
  while (cameFrom.has(k)) {
    current = cameFrom.get(k)!;
    path.unshift(current);
    k = key(current);
  }
  return path;
}
