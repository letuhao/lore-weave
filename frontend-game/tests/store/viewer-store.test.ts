import { describe, expect, it, beforeEach } from 'vitest';
import { lookupAt, useViewerStore } from '@/store/viewer-store';
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

describe('viewer-store lookupAt — TMP-Q4 chunk B valueBandThresholds', () => {
  it('flows the per-book thresholds from registry_ref into inspector', () => {
    const view = baseView({
      registry_ref: {
        id: 'xianxia',
        version: '1.0.0',
        value_band_thresholds: [1000, 5000, 15000, 50000],
      },
    });
    const at = lookupAt({ x: 0, y: 0 }, view);
    expect(at.valueBandThresholds).toEqual([1000, 5000, 15000, 50000]);
  });

  it('returns null when registry_ref omits value_band_thresholds', () => {
    const view = baseView({
      registry_ref: { id: 'lw', version: '1.0.0' },
    });
    const at = lookupAt({ x: 0, y: 0 }, view);
    expect(at.valueBandThresholds).toBeNull();
  });

  it('returns null when registry_ref is absent (pre-V2 view)', () => {
    const view = baseView();
    const at = lookupAt({ x: 0, y: 0 }, view);
    expect(at.valueBandThresholds).toBeNull();
  });
});

describe('viewer-store blendEnabled toggle (TMP-Q3 chunk A)', () => {
  beforeEach(() => {
    // Reset to default between tests so the previous test's toggle
    // doesn't leak. setBlendEnabled is the canonical reset path.
    // LOW-5 fix: moving the "defaults to true" test into this block
    // so the reset cycle covers it explicitly, eliminating the
    // ordering risk in the lookupAt block (no beforeEach there).
    useViewerStore.getState().setBlendEnabled(true);
    useViewerStore.getState().resetLayers();
  });

  it('blendEnabled defaults to true (Stage-1 polish ON by default)', () => {
    // AC-BLEND-2 default. Asserted after the beforeEach reset so the
    // assertion holds regardless of test ordering.
    expect(useViewerStore.getState().blendEnabled).toBe(true);
  });

  it('setBlendEnabled(false) flips the flag', () => {
    useViewerStore.getState().setBlendEnabled(false);
    expect(useViewerStore.getState().blendEnabled).toBe(false);
  });

  it('setBlendEnabled(true) re-enables after flip', () => {
    useViewerStore.getState().setBlendEnabled(false);
    useViewerStore.getState().setBlendEnabled(true);
    expect(useViewerStore.getState().blendEnabled).toBe(true);
  });

  it('blend toggle does not touch layer visibility (forward direction)', () => {
    // AC-BLEND-3 — blend lives orthogonal to L0..L7 layer toggles.
    // Forward: set blend then layer, verify each stayed put.
    useViewerStore.getState().setBlendEnabled(false);
    useViewerStore.getState().setLayer('foundation', false);
    const s = useViewerStore.getState();
    expect(s.blendEnabled).toBe(false);
    expect(s.visibleLayers.foundation).toBe(false);
    s.setLayer('foundation', true);
    expect(useViewerStore.getState().blendEnabled).toBe(false);
    expect(useViewerStore.getState().visibleLayers.foundation).toBe(true);
  });

  it('layer toggle does not touch blendEnabled (reverse direction)', () => {
    // LOW-4 fix from chunk-A /review-impl: cover the REVERSE direction
    // of the independence invariant. A regression that wired setLayer
    // to mutate blendEnabled (or vice versa via a future shared
    // setter) would slip past the forward-only test above.
    useViewerStore.getState().setLayer('paths', false);
    useViewerStore.getState().setBlendEnabled(false);
    const a = useViewerStore.getState();
    expect(a.visibleLayers.paths).toBe(false);
    expect(a.blendEnabled).toBe(false);
    // Flip blend again — layer must still be false.
    a.setBlendEnabled(true);
    const b = useViewerStore.getState();
    expect(b.visibleLayers.paths).toBe(false);
    expect(b.blendEnabled).toBe(true);
  });
});

describe('viewer-store showTreasureBands toggle (TMP-Q4 chunk C)', () => {
  beforeEach(() => {
    // Re-establish defaults between tests so flag-flip ordering doesn't
    // cross-contaminate. Same discipline as the chunk-A block.
    useViewerStore.getState().setShowTreasureBands(false);
    useViewerStore.getState().setBlendEnabled(true);
    useViewerStore.getState().resetLayers();
  });

  it('showTreasureBands defaults to false (AC-VBT-5)', () => {
    // Default OFF: the overlay is an at-a-glance design review aid,
    // not a default-visible polish. The author opts in.
    expect(useViewerStore.getState().showTreasureBands).toBe(false);
  });

  it('setShowTreasureBands flips the flag (forward + reverse)', () => {
    useViewerStore.getState().setShowTreasureBands(true);
    expect(useViewerStore.getState().showTreasureBands).toBe(true);
    useViewerStore.getState().setShowTreasureBands(false);
    expect(useViewerStore.getState().showTreasureBands).toBe(false);
  });

  it('LOW-3 — showTreasureBands and blendEnabled toggle independently', () => {
    // Forward: flip bands ON, then flip blend OFF. Both flags must
    // hold their independent state.
    useViewerStore.getState().setShowTreasureBands(true);
    useViewerStore.getState().setBlendEnabled(false);
    const a = useViewerStore.getState();
    expect(a.showTreasureBands).toBe(true);
    expect(a.blendEnabled).toBe(false);
    // Reverse: flip blend back, bands must still hold.
    a.setBlendEnabled(true);
    expect(useViewerStore.getState().showTreasureBands).toBe(true);
    expect(useViewerStore.getState().blendEnabled).toBe(true);
  });

  it('LOW-3 — showTreasureBands and L0..L7 layer toggles independent', () => {
    // A layer toggle must not perturb showTreasureBands. Same
    // independence-invariant pattern as the blend x layer test above.
    useViewerStore.getState().setShowTreasureBands(true);
    useViewerStore.getState().setLayer('foundation', false);
    const a = useViewerStore.getState();
    expect(a.showTreasureBands).toBe(true);
    expect(a.visibleLayers.foundation).toBe(false);
    // Reverse direction.
    a.setLayer('foundation', true);
    a.setShowTreasureBands(false);
    const b = useViewerStore.getState();
    expect(b.showTreasureBands).toBe(false);
    expect(b.visibleLayers.foundation).toBe(true);
  });
});
