// TMP-Q5 chunk B — pure helpers for "which zone owns this tile?"
//
// Shared between `overlay-rt.ts` (canvas zone-role tint) and
// `role-breakdown.ts` (MetadataPanel role count table) so a
// boundary-tile placement isn't visually painted under zone B but
// counted under zone A in the panel. Same single-source-of-truth
// pattern as chunk-A TMP-Q4 chunk-C will land via PR #14 (under
// `zone-breakdown.ts`); at rebase, both surfaces consume from one
// merged file.

import type { TileMask, ZoneRuntime } from '@/types/tilemap';

/**
 * Defensive TileMask bit read.
 *
 * Backend `TileMask` packs bits as `bits[y * width + x / 64]` with the
 * bit at `(y * width + x) % 64`. Returns `false` for out-of-bounds
 * reads (a registry / template authoring error must NOT crash the
 * inspector).
 */
export function tileMaskGet(mask: TileMask, x: number, y: number): boolean {
  if (x < 0 || y < 0 || x >= mask.width || y >= mask.height) return false;
  const flat = y * mask.width + x;
  const wordIdx = Math.floor(flat / 64);
  const bitIdx = flat % 64;
  const word = mask.bits[wordIdx];
  if (word === undefined) return false;
  return (word & (1n << BigInt(bitIdx))) !== 0n;
}

/**
 * Authoritative "which zone owns this tile/placement?".
 *
 * Preference order:
 *   1. `assigned_tiles` bitmap lookup (backend's authoritative
 *      assignment).
 *   2. Voronoi `nearestZoneOf(center_position)` fallback when no
 *      zone's `assigned_tiles` claims the tile, OR when no zone has
 *      a bitmap at all (pre-V1.2 fixture or sparse test view).
 *
 * Returns the zone's INDEX in `zones` (not its `zone_id`) so callers
 * can index into other parallel arrays. Returns `-1` when `zones`
 * is empty.
 */
export function zoneIndexOfPlacement(
  anchor: { x: number; y: number },
  zones: ReadonlyArray<ZoneRuntime>,
): number {
  if (zones.length === 0) return -1;
  // First pass — authoritative bitmap check.
  //
  // LOW from chunk-B /review-impl — when MULTIPLE zones bitmap-claim
  // the same tile (a backend invariant violation), this loop picks
  // the FIRST claiming index silently. The backend guarantees zones
  // don't overlap; defensive logging here would be noisy in the
  // common case. Documented + accepted; if a future backend bug ever
  // ships overlapping masks, the visual symptom (first-claimer's
  // role color painted) is the diagnostic signal.
  for (let i = 0; i < zones.length; i++) {
    const at = zones[i]!.assigned_tiles;
    if (at && tileMaskGet(at, anchor.x, anchor.y)) {
      return i;
    }
  }
  // Second pass — Voronoi fallback (used when no zone's bitmap claims
  // the tile, OR when all zones lack a bitmap).
  let bestIdx = 0;
  let bestDist = Infinity;
  for (let i = 0; i < zones.length; i++) {
    const z = zones[i]!;
    const dx = z.center_position.x - anchor.x;
    const dy = z.center_position.y - anchor.y;
    const d = dx * dx + dy * dy;
    if (d < bestDist) {
      bestDist = d;
      bestIdx = i;
    }
  }
  return bestIdx;
}
