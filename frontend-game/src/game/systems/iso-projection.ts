// Iso projection helpers — thin re-export from lib/iso-math.ts so scene
// code can import from "@game/systems/iso-projection" or any path it
// prefers. Centralized so future changes (e.g. different tile dimension)
// have one place to update.

export { worldToScreen, screenToWorld, screenToTile } from '../../lib/iso-math';
export type { WorldCoord, ScreenCoord } from '../../lib/iso-math';
