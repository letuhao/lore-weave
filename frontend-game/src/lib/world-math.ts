// Top-down orthogonal coordinate conversion per spec
// `docs/specs/2026-05-24-v1-tilemap-viewer-rescope.md` §3.
//
// Two coordinate systems:
//   WORLD  — integer tile (x, y) coords on a square grid, origin top-left
//   SCREEN — pixel coords after identity projection scaled by TILE_PX
//
// Projection (identity, scaled):
//   screenX = worldX * TILE_PX
//   screenY = worldY * TILE_PX
//
// Inverse: screen / TILE_PX.

import { TILE_PX } from '../game/config/constants';

export interface WorldCoord {
  x: number;
  y: number;
}

export interface ScreenCoord {
  x: number;
  y: number;
}

export function tileToScreen(world: WorldCoord, tilePx: number = TILE_PX): ScreenCoord {
  return {
    x: world.x * tilePx,
    y: world.y * tilePx,
  };
}

export function screenToTile(screen: ScreenCoord, tilePx: number = TILE_PX): WorldCoord {
  return {
    x: Math.floor(screen.x / tilePx),
    y: Math.floor(screen.y / tilePx),
  };
}
