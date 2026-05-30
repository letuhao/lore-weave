import { describe, expect, it } from 'vitest';
import {
  tileMaskGet,
  zoneIndexOfPlacement,
} from '../../src/components/viewer/zone-attribution';
import type { ZoneRuntime } from '../../src/types/tilemap';

// TMP-Q5 chunk B pure helpers — both `overlay-rt.ts` and
// `role-breakdown.ts` consume these, so a regression here breaks
// BOTH surfaces. Tests pin the bitmap + Voronoi attribution logic
// so a future refactor (e.g., merging with PR #14 chunk-C's
// `zone-breakdown.ts` at rebase) doesn't silently drift.

// Helper: a 4x4 mask covering rows 0..1 (bits 0..7).
const TOP_HALF_BITS = 0xffn;
// 4x4 mask covering rows 2..3 (bits 8..15).
const BOTTOM_HALF_BITS = 0xff00n;

describe('TMP-Q5 chunk B — tileMaskGet', () => {
  it('reads bits correctly for an 8-tile word', () => {
    const mask = { width: 4, height: 4, bits: [TOP_HALF_BITS] };
    expect(tileMaskGet(mask, 0, 0)).toBe(true);
    expect(tileMaskGet(mask, 3, 1)).toBe(true);
    expect(tileMaskGet(mask, 0, 2)).toBe(false);
    expect(tileMaskGet(mask, 3, 3)).toBe(false);
  });

  it('returns false for out-of-bounds (defensive)', () => {
    const mask = { width: 4, height: 4, bits: [TOP_HALF_BITS] };
    expect(tileMaskGet(mask, -1, 0)).toBe(false);
    expect(tileMaskGet(mask, 4, 0)).toBe(false);
    expect(tileMaskGet(mask, 0, -1)).toBe(false);
    expect(tileMaskGet(mask, 0, 4)).toBe(false);
  });

  it('returns false when the bit word is missing (sparse mask)', () => {
    // A 64x64 mask declares only word 0; the bit at (0, 1) lives in
    // word 1 (flat index 64). Missing word → false (no crash).
    const mask = { width: 64, height: 64, bits: [0n] };
    expect(tileMaskGet(mask, 0, 1)).toBe(false);
  });
});

describe('TMP-Q5 chunk B — zoneIndexOfPlacement', () => {
  function baseZones(): ZoneRuntime[] {
    return [
      {
        zone_id: 'top',
        zone_role: 'wilderness',
        center_position: { x: 1, y: 0 },
        terrain_type: 'grass',
        assigned_tiles: { width: 4, height: 4, bits: [TOP_HALF_BITS] },
      },
      {
        zone_id: 'bottom',
        zone_role: 'hub',
        center_position: { x: 1, y: 3 },
        terrain_type: 'grass',
        assigned_tiles: { width: 4, height: 4, bits: [BOTTOM_HALF_BITS] },
      },
    ];
  }

  it('uses assigned_tiles bitmap when available (authoritative)', () => {
    const zones = baseZones();
    expect(zoneIndexOfPlacement({ x: 0, y: 0 }, zones)).toBe(0); // top
    expect(zoneIndexOfPlacement({ x: 0, y: 3 }, zones)).toBe(1); // bottom
  });

  it('falls back to Voronoi nearest-zone when no bitmap claims the tile', () => {
    const sparseZones: ZoneRuntime[] = [
      {
        zone_id: 'near',
        zone_role: 'wilderness',
        center_position: { x: 1, y: 1 },
        terrain_type: 'grass',
        assigned_tiles: { width: 4, height: 4, bits: [0n] }, // empty mask
      },
      {
        zone_id: 'far',
        zone_role: 'hub',
        center_position: { x: 10, y: 10 },
        terrain_type: 'grass',
        assigned_tiles: { width: 4, height: 4, bits: [0n] },
      },
    ];
    // (2, 2) is closer to near (dist² = 2) than far (dist² = 128).
    expect(zoneIndexOfPlacement({ x: 2, y: 2 }, sparseZones)).toBe(0);
  });

  it('falls back to Voronoi when no zone has assigned_tiles (pre-V1.2 fixture)', () => {
    const noBitsZones: ZoneRuntime[] = [
      {
        zone_id: 'a',
        zone_role: 'wilderness',
        center_position: { x: 0, y: 0 },
        terrain_type: 'grass',
      },
      {
        zone_id: 'b',
        zone_role: 'hub',
        center_position: { x: 10, y: 10 },
        terrain_type: 'grass',
      },
    ];
    expect(zoneIndexOfPlacement({ x: 1, y: 1 }, noBitsZones)).toBe(0);
    expect(zoneIndexOfPlacement({ x: 9, y: 9 }, noBitsZones)).toBe(1);
  });

  it('returns -1 for empty zones', () => {
    expect(zoneIndexOfPlacement({ x: 0, y: 0 }, [])).toBe(-1);
  });
});
