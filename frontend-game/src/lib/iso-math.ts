// Iso 2:1 dimetric coordinate conversion (spec §1 #10, tile 128×64).
//
// Two coordinate systems:
//   WORLD  — integer tile (x, y) coords, axes aligned with the iso grid
//   SCREEN — pixel coords after iso projection
//
// Projection (standard 2:1 dimetric):
//   screenX = (worldX - worldY) * TILE_HALF_WIDTH
//   screenY = (worldX + worldY) * TILE_HALF_HEIGHT
//
// Inverse (screen → world): standard 2x2 inverse of the projection matrix.

import { TILE_HALF_HEIGHT, TILE_HALF_WIDTH } from '../game/config/constants';

export interface WorldCoord {
  x: number;
  y: number;
}

export interface ScreenCoord {
  x: number;
  y: number;
}

export function worldToScreen(world: WorldCoord): ScreenCoord {
  return {
    x: (world.x - world.y) * TILE_HALF_WIDTH,
    y: (world.x + world.y) * TILE_HALF_HEIGHT,
  };
}

export function screenToWorld(screen: ScreenCoord): WorldCoord {
  const halfW = TILE_HALF_WIDTH;
  const halfH = TILE_HALF_HEIGHT;
  return {
    x: screen.x / (2 * halfW) + screen.y / (2 * halfH),
    y: screen.y / (2 * halfH) - screen.x / (2 * halfW),
  };
}

// Round to nearest integer tile — useful when picking which tile a click hit.
export function screenToTile(screen: ScreenCoord): WorldCoord {
  const w = screenToWorld(screen);
  return { x: Math.round(w.x), y: Math.round(w.y) };
}
