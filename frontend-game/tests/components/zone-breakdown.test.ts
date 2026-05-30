import { describe, expect, it } from 'vitest';
import {
  computeZoneBreakdown,
  tileMaskGet,
  zoneIndexOfPlacement,
} from '../../src/components/viewer/zone-breakdown';
import { BAND_COLORS, BAND_LABELS } from '../../src/game/render/treasure-badge';
import type { TilemapView, ZoneRuntime } from '../../src/types/tilemap';

// TMP-Q4 chunk C pure helpers — both `overlay-rt.ts` and `MetadataPanel.tsx`
// share `computeZoneBreakdown` + `zoneIndexOfPlacement` so a single test
// pins the MED-1 invariant (overlay paint + breakdown table use the same
// zone-of-placement attribution).

// 4x4 grid with two zones:
//   zone "z0" claims y < 2 (top half)
//   zone "z1" claims y >= 2 (bottom half)
// (4 tiles per row × 4 rows = 16 tiles; first 8 in z0, last 8 in z1.)
//
// bits packed: index = y*4 + x; word at index/64.
// z0 (y<2): bits 0..7 set ⇒ word 0 = 0b11111111 = 0xFF = 255n
// z1 (y>=2): bits 8..15 set ⇒ word 0 = 0xFF00 = 65280n
const Z0_BITS = 0xffn; // bits 0..7
const Z1_BITS = 0xff00n; // bits 8..15

function baseZones(): ZoneRuntime[] {
  return [
    {
      zone_id: 'z0',
      zone_role: 'wilderness',
      center_position: { x: 1, y: 0 },
      terrain_type: 'grass',
      assigned_tiles: { width: 4, height: 4, bits: [Z0_BITS] },
    },
    {
      zone_id: 'z1',
      zone_role: 'hub',
      center_position: { x: 1, y: 3 },
      terrain_type: 'grass',
      assigned_tiles: { width: 4, height: 4, bits: [Z1_BITS] },
    },
  ];
}

function baseView(overrides: Partial<TilemapView> = {}): TilemapView {
  return {
    channel_id: 'unit',
    tier: 'town',
    grid_size: { width: 4, height: 4 },
    template_id: 't',
    seed: 1,
    zones: baseZones(),
    terrain_layer: new Array(16).fill(1),
    object_placements: [],
    road_segments: [],
    river_segments: [],
    child_cell_anchors: {},
    generation_source: { kind: 'engine_generated' },
    prompt_template_version: 0,
    ...overrides,
  };
}

describe('TMP-Q4 chunk C — tileMaskGet', () => {
  it('reads bits correctly for an 8-tile word', () => {
    const mask = { width: 4, height: 4, bits: [Z0_BITS] };
    // Bits 0..7 set (y<2).
    expect(tileMaskGet(mask, 0, 0)).toBe(true);
    expect(tileMaskGet(mask, 3, 1)).toBe(true);
    // Bit 8+ unset (y>=2).
    expect(tileMaskGet(mask, 0, 2)).toBe(false);
    expect(tileMaskGet(mask, 3, 3)).toBe(false);
  });

  it('returns false for out-of-bounds coords (defensive)', () => {
    const mask = { width: 4, height: 4, bits: [Z0_BITS] };
    expect(tileMaskGet(mask, -1, 0)).toBe(false);
    expect(tileMaskGet(mask, 4, 0)).toBe(false);
    expect(tileMaskGet(mask, 0, -1)).toBe(false);
    expect(tileMaskGet(mask, 0, 4)).toBe(false);
  });

  it('returns false when the bit word is missing (sparse mask)', () => {
    const mask = { width: 64, height: 64, bits: [0n] }; // only word 0 present
    // Bit at (0, 1) is in word 1 (flat index 64). Word 1 missing → false.
    expect(tileMaskGet(mask, 0, 1)).toBe(false);
  });
});

describe('TMP-Q4 chunk C MED-1 — zoneIndexOfPlacement', () => {
  it('uses assigned_tiles bitmap when available (authoritative)', () => {
    const zones = baseZones();
    // (0, 0) is in z0's bitmap.
    expect(zoneIndexOfPlacement({ x: 0, y: 0 }, zones)).toBe(0);
    // (0, 3) is in z1's bitmap.
    expect(zoneIndexOfPlacement({ x: 0, y: 3 }, zones)).toBe(1);
  });

  it('falls back to Voronoi nearest-zone when no bitmap claims the tile', () => {
    // A tile NOT claimed by either bitmap (e.g., (3, 2) — but actually
    // (3, 2) IS in z1's bitmap. Let's use a tile NEITHER bitmap covers.)
    // bits at index 0..15 cover the 4x4 grid; (3, 2) = index 11 in z1.
    // For a tile outside the bitmap coverage, both bitmaps return false.
    // Construct a sparse fixture for this.
    const sparseZones: ZoneRuntime[] = [
      {
        zone_id: 'near',
        zone_role: 'wilderness',
        center_position: { x: 1, y: 1 },
        terrain_type: 'grass',
        assigned_tiles: { width: 4, height: 4, bits: [0n] }, // no bits set
      },
      {
        zone_id: 'far',
        zone_role: 'hub',
        center_position: { x: 10, y: 10 },
        terrain_type: 'grass',
        assigned_tiles: { width: 4, height: 4, bits: [0n] }, // no bits set
      },
    ];
    // (2, 2) — distance² to (1,1) = 2; to (10,10) = 128 → nearest = 0 (near).
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

  it('returns -1 when zones array is empty', () => {
    expect(zoneIndexOfPlacement({ x: 0, y: 0 }, [])).toBe(-1);
  });
});

describe('TMP-Q4 chunk C — computeZoneBreakdown', () => {
  it('returns empty rows for a view with no zones', () => {
    const view = baseView({ zones: [] });
    expect(computeZoneBreakdown(view)).toEqual([]);
  });

  it('returns empty rows for a view with zones but no treasure placements', () => {
    const view = baseView();
    expect(computeZoneBreakdown(view)).toEqual([]);
  });

  it('filters out non-treasure placements (uses shouldStampBadge)', () => {
    const view = baseView({
      object_placements: [
        // Obstacle in z0 — should be ignored.
        { kind: 'obstacle', anchor: { x: 0, y: 0 }, value: 1000 },
        // Lair in z1 — should be ignored even with tier_index inherited.
        {
          kind: 'monster_lair',
          anchor: { x: 0, y: 3 },
          value: 850,
          tier_index: 0,
        },
      ],
    });
    expect(computeZoneBreakdown(view)).toEqual([]);
  });

  it('buckets treasure piles by zone via assigned_tiles bitmap', () => {
    const view = baseView({
      object_placements: [
        // Two treasures in z0 (y<2)
        {
          kind: 'treasure',
          anchor: { x: 0, y: 0 },
          value: 500,
          tier_index: 0,
        },
        {
          kind: 'treasure',
          anchor: { x: 1, y: 1 },
          value: 700,
          tier_index: 0,
        },
        // One treasure in z1 (y>=2)
        {
          kind: 'treasure',
          anchor: { x: 0, y: 2 },
          value: 8000,
          tier_index: 0,
        },
      ],
    });
    const rows = computeZoneBreakdown(view);
    expect(rows).toHaveLength(2);
    // Sort: total_value DESC (z1 8000 > z0 1200) so z1 is first.
    expect(rows[0]?.zone_id).toBe('z1');
    expect(rows[0]?.pile_count).toBe(1);
    expect(rows[0]?.total_value).toBe(8000);
    expect(rows[1]?.zone_id).toBe('z0');
    expect(rows[1]?.pile_count).toBe(2);
    expect(rows[1]?.total_value).toBe(1200);
  });

  it('omits zones with no piles (LOW-1 fix)', () => {
    // Only z0 has a pile; z1 is empty. z1 must NOT appear.
    const view = baseView({
      object_placements: [
        {
          kind: 'treasure',
          anchor: { x: 0, y: 0 },
          value: 500,
          tier_index: 0,
        },
      ],
    });
    const rows = computeZoneBreakdown(view);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.zone_id).toBe('z0');
  });

  it('sorts by total_value desc with zone_id tiebreaker', () => {
    // Tied values: z0 and z1 both at total 1000.
    const view = baseView({
      object_placements: [
        {
          kind: 'treasure',
          anchor: { x: 0, y: 0 },
          value: 1000,
          tier_index: 0,
        },
        {
          kind: 'treasure',
          anchor: { x: 0, y: 2 },
          value: 1000,
          tier_index: 0,
        },
      ],
    });
    const rows = computeZoneBreakdown(view);
    expect(rows).toHaveLength(2);
    expect(rows[0]?.zone_id).toBe('z0'); // z0 < z1 alphabetically
    expect(rows[1]?.zone_id).toBe('z1');
  });

  it('uses MAX tier-0 value for band color, not total or max-of-all', () => {
    // z0: two piles, one tier_index=0 with v=600, one tier_index=1 with v=12000.
    // Max-of-all = 12000 (would land in band 4 = gilt).
    // Max tier-0 = 600 (lands in band 1 = low-mid).
    // Chunk-A semantic: tier_index=0 is the zone's HIGHEST band, so band
    // for the zone should come from THAT tier's piles — NOT from a
    // lower-tier pile that happens to be more valuable in absolute terms.
    const view = baseView({
      object_placements: [
        {
          kind: 'treasure',
          anchor: { x: 0, y: 0 },
          value: 600,
          tier_index: 0,
        },
        {
          kind: 'treasure',
          anchor: { x: 1, y: 0 },
          value: 12000,
          tier_index: 1,
        },
      ],
    });
    const rows = computeZoneBreakdown(view);
    expect(rows[0]?.zone_id).toBe('z0');
    expect(rows[0]?.spotlight_value).toBe(600);
    expect(rows[0]?.band).toBe(1);
    expect(rows[0]?.color).toBe(BAND_COLORS[1]);
    expect(rows[0]?.band_name).toBe(BAND_LABELS[1]);
  });

  it('falls back to max-of-any when no pile has tier_index=0 (pre-Q4 wire)', () => {
    // No tier_index populated at all (legacy wire). Fall back to max of any.
    const view = baseView({
      object_placements: [
        { kind: 'treasure', anchor: { x: 0, y: 0 }, value: 2500 },
        { kind: 'treasure', anchor: { x: 0, y: 1 }, value: 8000 },
      ],
    });
    const rows = computeZoneBreakdown(view);
    expect(rows[0]?.spotlight_value).toBe(8000);
    expect(rows[0]?.band).toBe(3); // high
  });

  it('respects per-book value_band_thresholds (xianxia scale)', () => {
    const view = baseView({
      registry_ref: {
        id: 'xianxia',
        version: '1.0.0',
        value_band_thresholds: [1000, 5000, 15000, 50000],
      },
      object_placements: [
        {
          kind: 'treasure',
          anchor: { x: 0, y: 0 },
          value: 10000,
          tier_index: 0,
        },
      ],
    });
    const rows = computeZoneBreakdown(view);
    // 10000 with xianxia thresholds [1000, 5000, 15000, 50000]:
    //   10000 >= 5000 but < 15000 ⇒ band 2 (mid).
    expect(rows[0]?.band).toBe(2);
    expect(rows[0]?.color).toBe(BAND_COLORS[2]);
  });
});
