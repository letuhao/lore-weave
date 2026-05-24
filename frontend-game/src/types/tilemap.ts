// TS mirrors of tilemap-service wire contract. These shapes mirror
// `services/tilemap-service/src/types/{tilemap,tile,zone}.rs` Serialize
// derives; keep in sync if backend bumps schema.
//
// V1.2 expanded scope: all 5 layers consumed by the viewer
// (terrain_layer + roads + rivers + object_placements + zones).

export type ZoneId = string;

/** TerrainKind u8 index per `services/tilemap-service/src/types/tile.rs` */
export enum TerrainKind {
  Grass = 1,
  Forest = 2,
  Mountain = 3,
  Water = 4,
  Sand = 5,
  Snow = 6,
  Swamp = 7,
  Road = 8,
  Rough = 9,
  Subterranean = 10,
}

/** Stable lowercase tag — matches backend `TerrainKind::tag()`. */
export function terrainKindTag(kind: TerrainKind): string {
  switch (kind) {
    case TerrainKind.Grass: return 'grass';
    case TerrainKind.Forest: return 'forest';
    case TerrainKind.Mountain: return 'mountain';
    case TerrainKind.Water: return 'water';
    case TerrainKind.Sand: return 'sand';
    case TerrainKind.Snow: return 'snow';
    case TerrainKind.Swamp: return 'swamp';
    case TerrainKind.Road: return 'road';
    case TerrainKind.Rough: return 'rough';
    case TerrainKind.Subterranean: return 'subterranean';
  }
}

export interface TileCoord {
  x: number;
  y: number;
}

export interface GridSize {
  width: number;
  height: number;
}

export type ChannelTier = 'continent' | 'country' | 'district' | 'town';

export type ZoneRole =
  | 'capital'
  | 'hub'
  | 'wilderness'
  | 'forbidden'
  | 'sea'
  | 'arena'
  | 'mine_camp'
  | 'town';

export interface ZoneRuntime {
  zone_id: ZoneId;
  zone_role: ZoneRole;
  center_position: TileCoord;
  /** Bitset packed as u64 array per backend `TileMask`. Not used by V1 viewer. */
  assigned_tiles?: unknown;
  free_paths?: unknown;
  terrain_type: string;
}

export interface RoadSegment {
  waypoints: TileCoord[];
}

export interface RiverCrossing {
  at: TileCoord;
  kind: 'bridge' | 'ford';
}

export interface RiverSegment {
  tiles: TileCoord[];
  crossings: RiverCrossing[];
}

/** Mirrors backend `TilemapObjectKind` (9 variants). */
export type TilemapObjectKind =
  | 'treasure'
  | 'monster_lair'
  | 'town'
  | 'mine'
  | 'landmark'
  | 'monolith'
  | 'decoration'
  | 'obstacle'
  | 'ferry';

/** Mirrors backend `BiomeObjectType` (9 variants — applies to `obstacle`). */
export type BiomeObjectType =
  | 'mountain'
  | 'tree'
  | 'lake'
  | 'crater'
  | 'rock'
  | 'plant'
  | 'structure'
  | 'animal'
  | 'other';

export interface TilemapObjectPlacement {
  kind: TilemapObjectKind;
  anchor: TileCoord;
  canon_ref?: string;
  biome_object_type?: BiomeObjectType;
  value?: number;
}

export type GenerationSource =
  | { kind: 'engine_generated' }
  | { kind: 'llm_augmented'; model: string; attempts: number; generated_at_fiction_time: string };

/** Wire shape for `POST /internal/v1/tilemaps/render` request body. */
export interface RenderRequest {
  /** Full TilemapTemplate JSON. Loaded from /public/templates/*.json fixture. */
  template: unknown;
  channel_id: string;
  tier: ChannelTier;
  grid_size: GridSize;
  seed: number;
}

/** Wire shape for `POST /internal/v1/tilemaps/render` response body. */
export interface TilemapView {
  channel_id: string;
  tier: ChannelTier;
  grid_size: GridSize;
  template_id: string;
  seed: number;
  zones: ZoneRuntime[];
  /** Flat array; index = y*width + x; value = `TerrainKind` u8 index (1-10). */
  terrain_layer: number[];
  object_placements: TilemapObjectPlacement[];
  road_segments: RoadSegment[];
  river_segments: RiverSegment[];
  child_cell_anchors: Record<string, TileCoord>;
  generation_source: GenerationSource;
  regional_narration?: string;
  prompt_template_version: number;
}

/** Legacy V0 shape — kept for backward compat with `useTilemapHealth`. */
export interface TilemapRenderRequest {
  zoneId: ZoneId;
  width: number;
  height: number;
}
