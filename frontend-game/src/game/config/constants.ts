// Shared constants for the game subtree.
//
// Iso 2:1 dimetric per spec §1 #10: each tile is 128 px wide, 64 px tall.
// World grid is conceptually square; iso projection produces the diamond
// look in screen coords (see lib/iso-math.ts).

export const TILE_WIDTH = 128;
export const TILE_HEIGHT = 64;
export const TILE_HALF_WIDTH = TILE_WIDTH / 2;
export const TILE_HALF_HEIGHT = TILE_HEIGHT / 2;

// Camera follow lerp factor (0-1). Lower = smoother lag, higher = snappier.
export const CAMERA_LERP = 0.1;

// V0 demo zone size — Town tier per spec §11 (small enough for quick load).
export const DEFAULT_ZONE_WIDTH = 32;
export const DEFAULT_ZONE_HEIGHT = 32;

// Game container element id (matches index.html).
export const GAME_CONTAINER_ID = 'game-container';
