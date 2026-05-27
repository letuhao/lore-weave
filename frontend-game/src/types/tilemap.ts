// TS mirrors of tilemap-service wire contract. These shapes mirror
// `services/tilemap-service/src/types/{tilemap,tile,zone,primitive,registry}.rs`
// Serialize derives; keep in sync if backend bumps schema.
//
// V1.2 expanded scope: all 5 layers consumed by the viewer
// (terrain_layer + roads + rivers + object_placements + zones).
// V2 additive: TerrainCell + terrain_vocabulary + registry_ref +
// per-placement (primitive, tag, footprint, orientation, properties).

export type ZoneId = string;

/** V2 — engine-coded terrain behavior class. Mirrors backend
 *  `crate::types::primitive::TerrainPrimitive`. */
export type TerrainPrimitive =
  | 'land'
  | 'water'
  | 'wall'
  | 'path'
  | 'hazard'
  | 'void';

/** V2 — engine-coded object behavior class. Mirrors backend
 *  `crate::types::primitive::ObjectPrimitive`. */
export type ObjectPrimitive =
  | 'decoration'
  | 'pickup'
  | 'container'
  | 'habitable'
  | 'blocker'
  | 'door'
  | 'trigger'
  | 'vehicle'
  | 'spawner'
  | 'producer'
  | 'plant';

/** V2 — tile footprint dimensions. Mirrors backend
 *  `crate::types::registry::FootprintSize`. */
export interface FootprintSize {
  width: number;
  height: number;
}

/** V2 — 8-way orientation. Mirrors backend `Direction`. */
export type Direction = 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | 'nw';

/** V2 — registry pin. Mirrors backend `RegistryRef`. */
export interface RegistryRef {
  id: string;
  version: string;
}

/** V2 — per-tile terrain cell. Indexed by `terrain_layer` u8 values
 *  via `terrain_vocabulary`. Mirrors backend `TerrainCell`. */
export interface TerrainCell {
  primitive: TerrainPrimitive;
  tag: string;
}

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

/** Backend `TileMask` (services/tilemap-service/src/types/tile_mask.rs):
 *  bits packed as u64 array; bit at index `y*width + x` indicates ownership.
 *  Wire format on the JSON line ships u64 values that overflow IEEE 754
 *  mantissa (53 bits) so values > 2^53 lose precision under default
 *  `JSON.parse`. Use `parseTilemapView()` (api/tilemap-client.ts) which
 *  preprocesses the response text to convert bit values to BigInt. */
export interface TileMask {
  width: number;
  height: number;
  bits: bigint[];
}

export interface ZoneRuntime {
  zone_id: ZoneId;
  zone_role: ZoneRole;
  center_position: TileCoord;
  /** Bitset packed as u64 array per backend `TileMask`. V1.2 L5 zone-
   *  boundary outline reads this; expected to be a `TileMask` after
   *  BigInt-aware parsing. */
  assigned_tiles?: TileMask;
  /** Connected free-path skeleton bitmap (TMP_002 §5 fractalize). Not
   *  used by V1.2 viewer yet — typed as unknown to avoid promising a
   *  shape we don't consume. */
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
  // V1 fields (frozen)
  kind: TilemapObjectKind;
  anchor: TileCoord;
  canon_ref?: string;
  biome_object_type?: BiomeObjectType;
  value?: number;
  // V2 additive — populated by backend Batch 3.0c.1+. Absent on pre-V2 fixtures.
  /** Engine behavior class. */
  primitive?: ObjectPrimitive;
  /** Registry tag (e.g. `lw:treasure`, `xianxia:dao-stone`). */
  tag?: string;
  /** Tile footprint. Frontend currently uses for inspector readout only;
   *  sprite display sizing still derived from tier table (object-overlay.ts). */
  footprint?: FootprintSize;
  /** 8-way orientation. */
  orientation?: Direction;
  /** Open property bag for per-book extension (charge_count, faction, etc.). */
  properties?: Record<string, unknown> | null;
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
  /** V2 — dictionary indexed by `terrain_layer` u8 values. Index 0 = void
   *  sentinel, indexes 1..=10 carry the V1 terrain cells. Absent on
   *  pre-V2 fixtures; use `terrainKindTag(layer[i])` as fallback. */
  terrain_vocabulary?: TerrainCell[];
  /** V2 — which registry was used to render this view. */
  registry_ref?: RegistryRef;
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
