import { describe, expect, it } from 'vitest';
import { lookupAt } from '@/store/viewer-store';
import type { TerrainCell, TilemapView } from '@/types/tilemap';

// V2 inspector lookup — `lookupAt` must resolve `terrainCell` from the
// V2 `terrain_vocabulary` field when present, and stay null when the
// view is pre-V2 (no vocabulary populated).

function baseView(overrides: Partial<TilemapView> = {}): TilemapView {
  return {
    channel_id: 'unit',
    tier: 'town',
    grid_size: { width: 4, height: 4 },
    template_id: 't',
    seed: 1,
    zones: [
      {
        zone_id: 'z0',
        zone_role: 'wilderness',
        center_position: { x: 2, y: 2 },
        terrain_type: 'grass',
      },
    ],
    // Tile (1,1) → flat 5 → kind 4 (Water); tile (0,0) → kind 1 (Grass).
    terrain_layer: [1, 0, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    object_placements: [],
    road_segments: [],
    river_segments: [],
    child_cell_anchors: {},
    generation_source: { kind: 'engine_generated' },
    prompt_template_version: 0,
    ...overrides,
  };
}

const VOCAB: TerrainCell[] = [
  { primitive: 'void', tag: 'lw:void' },
  { primitive: 'land', tag: 'lw:grass' },
  { primitive: 'land', tag: 'lw:forest' },
  { primitive: 'land', tag: 'lw:mountain' },
  { primitive: 'water', tag: 'lw:water' },
  { primitive: 'land', tag: 'lw:sand' },
  { primitive: 'land', tag: 'lw:snow' },
  { primitive: 'land', tag: 'lw:swamp' },
  { primitive: 'path', tag: 'lw:road' },
  { primitive: 'land', tag: 'lw:rough' },
  { primitive: 'land', tag: 'lw:subterranean' },
];

describe('viewer-store lookupAt — V2 terrainCell', () => {
  it('resolves terrainCell from terrain_vocabulary when present', () => {
    const view = baseView({ terrain_vocabulary: VOCAB });
    const at_water = lookupAt({ x: 1, y: 1 }, view);
    expect(at_water.terrainKind).toBe(4);
    expect(at_water.terrainCell).toEqual({ primitive: 'water', tag: 'lw:water' });

    const at_grass = lookupAt({ x: 0, y: 0 }, view);
    expect(at_grass.terrainKind).toBe(1);
    expect(at_grass.terrainCell).toEqual({ primitive: 'land', tag: 'lw:grass' });
  });

  it('returns null terrainCell when terrain_vocabulary is absent (pre-V2 view)', () => {
    const view = baseView(); // no vocabulary
    const at = lookupAt({ x: 1, y: 1 }, view);
    expect(at.terrainKind).toBe(4);
    expect(at.terrainCell).toBeNull();
  });

  it('returns null terrainCell when terrainKind is out of vocab range', () => {
    // A short vocabulary that doesn't cover all kinds — defensive guard.
    const view = baseView({ terrain_vocabulary: VOCAB.slice(0, 2) });
    const at = lookupAt({ x: 1, y: 1 }, view); // kind 4 — out of vocab range
    expect(at.terrainKind).toBe(4);
    expect(at.terrainCell).toBeNull();
  });

  it('still resolves V1 fields (zone, placements, road/river) alongside V2', () => {
    const view = baseView({
      terrain_vocabulary: VOCAB,
      object_placements: [
        {
          kind: 'treasure',
          anchor: { x: 1, y: 1 },
          tag: 'lw:treasure',
          primitive: 'pickup',
          footprint: { width: 1, height: 1 },
        },
      ],
      road_segments: [{ waypoints: [{ x: 1, y: 1 }] }],
    });
    const at = lookupAt({ x: 1, y: 1 }, view);
    expect(at.terrainCell?.tag).toBe('lw:water');
    expect(at.zone?.id).toBe('z0');
    expect(at.placementsAtTile).toHaveLength(1);
    expect(at.placementsAtTile[0]?.tag).toBe('lw:treasure');
    expect(at.placementsAtTile[0]?.primitive).toBe('pickup');
    expect(at.placementsAtTile[0]?.footprint).toEqual({ width: 1, height: 1 });
    expect(at.roadHits).toBe(1);
  });
});
