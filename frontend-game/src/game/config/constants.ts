// Shared constants for the game subtree.
//
// Top-down orthogonal grid per spec
// `docs/specs/2026-05-24-v1-tilemap-viewer-rescope.md` §3 — each tile is
// TILE_PX square. No iso projection; world → screen is identity scaled
// by TILE_PX (see lib/world-math.ts).

export const TILE_PX = 64;

// Camera follow lerp factor (0-1). Lower = smoother lag, higher = snappier.
export const CAMERA_LERP = 0.1;

// Default zone fetch params for the /play tilemap viewer route. Town tier
// per spec §3 + GridSize::TOWN_DEFAULT (64²) in tilemap-service.
export const DEFAULT_ZONE_WIDTH = 64;
export const DEFAULT_ZONE_HEIGHT = 64;
export const DEFAULT_TIER = 'town' as const;
export const DEFAULT_SEED = 1;

// Game container element id (matches index.html).
export const GAME_CONTAINER_ID = 'game-container';
