import { describe, expect, it } from 'vitest';
import { parseTilemapView } from '@/api/tilemap-client';

// V1.2 step B: assert BigInt-aware `parseTilemapView` recovers full u64
// precision from the `assigned_tiles.bits` arrays. Default `JSON.parse`
// rounds values > 2^53 to nearest IEEE 754 float, which corrupts the
// bitmap's low-order bits and produces wrong zone-boundary outlines.

const U64_OVER_53 = '18446708889337462784'; // 0xFFFFFFC0007FF800 — > 2^53
const U64_MAX = '18446744073709551615';     // 0xFFFFFFFFFFFFFFFF
const SMALL = '42';

function fixture(): string {
  return JSON.stringify({
    channel_id: 'unit',
    tier: 'town',
    grid_size: { width: 8, height: 8 },
    template_id: 'unit',
    seed: 1,
    zones: [
      {
        zone_id: 'z0',
        zone_role: 'capital',
        center_position: { x: 0, y: 0 },
        assigned_tiles: { width: 8, height: 8, bits: [99, 100] },
        terrain_type: 'grass',
      },
    ],
    terrain_layer: [],
    object_placements: [],
    road_segments: [],
    river_segments: [],
    child_cell_anchors: {},
    generation_source: { kind: 'engine_generated' },
    prompt_template_version: 0,
  }).replace(
    /"bits":\[99,100\]/,
    `"bits":[${U64_OVER_53},${U64_MAX},${SMALL}]`,
  );
}

describe('parseTilemapView (BigInt-aware)', () => {
  it('preserves u64 values > 2^53 as BigInt without precision loss', () => {
    const view = parseTilemapView(fixture());
    const at = view.zones[0]?.assigned_tiles;
    expect(at).toBeDefined();
    expect(at!.width).toBe(8);
    expect(at!.height).toBe(8);
    expect(at!.bits).toHaveLength(3);
    expect(at!.bits[0]).toBe(BigInt(U64_OVER_53));
    expect(at!.bits[1]).toBe(BigInt(U64_MAX));
    expect(at!.bits[2]).toBe(42n);
  });

  it('default JSON.parse loses precision (sanity check)', () => {
    const parsed = JSON.parse(`{"v":${U64_OVER_53}}`) as { v: number };
    // Confirms the bug being avoided: parsed as Number, can't round-trip.
    expect(parsed.v).not.toBe(BigInt(U64_OVER_53) as unknown as number);
    expect(Number.isSafeInteger(parsed.v)).toBe(false);
  });

  it('handles empty bits arrays + zones without assigned_tiles', () => {
    const view = parseTilemapView(
      JSON.stringify({
        channel_id: 'u',
        tier: 'town',
        grid_size: { width: 4, height: 4 },
        template_id: 'u',
        seed: 0,
        zones: [
          { zone_id: 'no-bits', zone_role: 'sea', center_position: { x: 0, y: 0 }, terrain_type: 'water' },
        ],
        terrain_layer: [1, 1, 1, 1, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
        object_placements: [],
        road_segments: [],
        river_segments: [],
        child_cell_anchors: {},
        generation_source: { kind: 'engine_generated' },
        prompt_template_version: 0,
      }),
    );
    expect(view.zones[0]?.assigned_tiles).toBeUndefined();
    expect(view.terrain_layer).toHaveLength(16);
  });
});
