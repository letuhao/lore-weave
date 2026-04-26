import type { ChannelTier, TileMapSkeleton, TileMapView } from '../data/types';
import { generateTerrain } from './terrain';
import { placeRoads } from './roads';

const PROMPT_TEMPLATE_VERSION = 1;

/**
 * L1 + L2 composition entry point.
 *
 * Given a hand-authored skeleton and deterministic seed, produces a complete
 * TileMapView aggregate matching SPIKE_03 §4 schema (modulo L3/L4 which are V2).
 *
 * Replay-determinism property (per EVT-A9):
 *   composeTileMap(skeleton, seed, _, _).terrain_layer == composeTileMap(skeleton, seed, _, _).terrain_layer
 *
 * Roads are deterministic too (A* with stable tie-breaking via Map insertion order).
 *
 * `generated_at` is excluded from determinism comparison (timestamp varies); strip
 * before equality checks in tests.
 */
export function composeTileMap(
  skeleton: TileMapSkeleton,
  seed: number,
  channelId: string,
  tier: ChannelTier,
): TileMapView {
  // L2.a — generate terrain by zone biome distribution + value-noise
  const terrainInitial = generateTerrain(skeleton, seed);

  // L2.b — overlay roads via A*; Water tiles preserved as bridges
  const { roads, updatedTerrain } = placeRoads(skeleton, terrainInitial);

  return {
    channel_id: channelId,
    tier,
    grid_size: skeleton.grid_size,
    skeleton_id: skeleton.skeleton_id,
    procedural_seed: seed,
    terrain_layer: updatedTerrain,
    roads,
    cell_placements: skeleton.cell_anchors.map((c) => ({
      channel_id: c.channel_id,
      position: c.position,
      display_name: c.display_name,
      kind: c.kind,
      tier: c.tier,
    })),
    object_placements: skeleton.landmark_anchors.map((l) => ({
      object_id: l.object_id,
      kind: l.kind,
      position: l.position,
      display_name: l.display_name,
    })),
    layer3_source: { kind: 'CanonicalDefault' },
    region_narration: null,
    generated_at: new Date().toISOString(),
    prompt_template_version: PROMPT_TEMPLATE_VERSION,
  };
}
