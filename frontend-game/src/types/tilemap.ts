// TS mirrors of tilemap-service contract. V0 placeholder; Session D
// mirrors the real Rust types from
// services/tilemap-service/src/world_inherit/types.rs +
// src/http/render.rs response shapes. The @loreweave/api-types package
// will eventually own these — this file is the frontend-game's local
// import alias.

export type ZoneId = string;
export type BiomeKey = string;

export interface TilemapRenderRequest {
  zoneId: ZoneId;
  width: number;
  height: number;
}

export interface TilemapRenderResponse {
  zoneId: ZoneId;
  tiles: number[][];
  biome: BiomeKey;
}
