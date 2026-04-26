// Mirror SPIKE_03 §4 aggregate sketch (preliminary; not boundary-locked)
// When TMP_001 graduates, regenerate from canonical contracts/api/tilemap/

export type ChannelTier = 'Continent' | 'Country' | 'District' | 'Town' | 'Cell';

export type TerrainKind =
  | 'Grass'
  | 'Forest'
  | 'Mountain'
  | 'Water'
  | 'Sand'
  | 'Snow'
  | 'Swamp'
  | 'Road'
  | 'Rough'
  | 'Subterranean';

export type MapObjectKind =
  | 'Treasure'
  | 'MonsterLair'
  | 'Landmark'
  | 'Decoration'
  | 'Mine'
  | 'Portal'
  | 'Ruin';

export type CellKind = 'capital' | 'fortress' | 'temple' | 'tavern' | 'port' | 'cell' | 'cave';

export type RoadKind = 'Highway' | 'Path' | 'Trade';

export interface TileCoord {
  x: number;
  y: number;
}

export interface GridSize {
  width: number;
  height: number;
}

export interface ZoneSpec {
  zone_id: string;
  shape: { kind: 'rect'; bounds: { x: number; y: number; w: number; h: number } };
  biome_weights: Partial<Record<TerrainKind, number>>;
  noise_octaves: number;
  noise_scale: number;
}

export interface CellAnchor {
  channel_id: string;
  tier: ChannelTier;
  position: TileCoord;
  kind: CellKind;
  display_name: string;
}

export interface LandmarkAnchor {
  object_id: string;
  kind: MapObjectKind;
  position: TileCoord;
  display_name: string;
}

export interface RoadConnection {
  from: string;
  to: string;
  kind: RoadKind;
}

// L1 input — author-authored skeleton
export interface TileMapSkeleton {
  skeleton_id: string;
  grid_size: GridSize;
  terrain_zones: ZoneSpec[];
  cell_anchors: CellAnchor[];
  landmark_anchors: LandmarkAnchor[];
  road_connections: RoadConnection[];
}

// L2 output — road segment with computed waypoints
export interface RoadSegment {
  from_channel_id: string;
  to_channel_id: string;
  waypoints: TileCoord[];
  road_kind: RoadKind;
}

// Aggregate = L1 + L2 (+ L3/L4 V2)
export interface CellPlacement {
  channel_id: string;
  position: TileCoord;
  display_name: string;
  kind: CellKind;
  tier: ChannelTier;
}

export interface MapObjectPlacement {
  object_id: string;
  kind: MapObjectKind;
  position: TileCoord;
  display_name: string;
}

export type Layer3Source =
  | { kind: 'CanonicalDefault' }
  | { kind: 'LlmGenerated'; model: string; attempts: number; generated_at: string };

export interface TileMapView {
  channel_id: string;
  tier: ChannelTier;
  grid_size: GridSize;
  skeleton_id: string;
  procedural_seed: number;
  /** Flattened tile array; index = y * width + x; values are TerrainKind enum index */
  terrain_layer: number[];
  roads: RoadSegment[];
  cell_placements: CellPlacement[];
  object_placements: MapObjectPlacement[];
  layer3_source: Layer3Source;
  region_narration: string | null;
  /** ISO 8601 timestamp; not part of replay-determinism comparison */
  generated_at: string;
  /** Schema version for cache invalidation; mirrors CSC_001 prompt_template_version */
  prompt_template_version: number;
}

// Closed enum order — index in this array IS the storage representation
export const TERRAIN_KIND_ORDER: TerrainKind[] = [
  'Grass',
  'Forest',
  'Mountain',
  'Water',
  'Sand',
  'Snow',
  'Swamp',
  'Road',
  'Rough',
  'Subterranean',
];

export function terrainToIndex(t: TerrainKind): number {
  const i = TERRAIN_KIND_ORDER.indexOf(t);
  if (i < 0) throw new Error(`Unknown terrain: ${t}`);
  return i;
}

export function indexToTerrain(i: number): TerrainKind {
  return TERRAIN_KIND_ORDER[i] ?? 'Grass';
}
