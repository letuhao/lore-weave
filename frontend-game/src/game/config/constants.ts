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
// per spec §3 + GridSize::ZOOM_64 (64²) in tilemap-service (renamed 2026-08-22, SPG-R13 -- the presets were a zoom ladder keyed by retired ChannelTier rungs, not a per-kind map).
export const DEFAULT_ZONE_WIDTH = 64;
export const DEFAULT_ZONE_HEIGHT = 64;
// SPG-R14, 2026-08-22: `town` became `locale` -- the tilemap-bearing kind
// (SPG-R9). The name stays DEFAULT_TIER for now because renaming it would
// touch call sites in the same pass as a wire change; the VALUE is the part
// that had to move.
export const DEFAULT_TIER = 'locale' as const;
export const DEFAULT_SEED = 1;

// Game container element id (matches index.html).
export const GAME_CONTAINER_ID = 'game-container';
