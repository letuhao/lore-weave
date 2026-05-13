import type { TileMapSkeleton } from './types';

/**
 * L1 — Hand-authored kingdom skeleton (PoC default).
 *
 * 64×64 tilemap representing a fantasy continent "Nam Thiên" with:
 * - Mountain range north (rows 0-12)
 * - Foothill transition (rows 12-20)
 * - Central plain with capital (rows 20-44)
 * - Western forest belt (cols 0-16, rows 20-44)
 * - Eastern grass+sand (cols 48-64, rows 20-44)
 * - Southern lake (rows 44-56)
 * - Southern coast/beach (rows 56-64)
 *
 * Cell anchor positions chosen so Layer 2 A* road pathfinding produces interesting
 * routes (capital at center; satellites in 4 cardinal directions; 2 narrative cells
 * near capital for SPIKE_01 Yên Vũ Lâu coverage).
 *
 * V2: per-genre skeleton library (wuxia / scifi / modern). This file becomes the
 * first entry. Author-uploadable skeletons via Forge V3.
 */
export const KINGDOM_DEFAULT: TileMapSkeleton = {
  skeleton_id: 'kingdom_default',
  grid_size: { width: 64, height: 64 },
  terrain_zones: [
    {
      zone_id: 'central_plain',
      shape: { kind: 'rect', bounds: { x: 16, y: 20, w: 32, h: 24 } },
      biome_weights: { Grass: 0.7, Forest: 0.25, Sand: 0.05 },
      noise_octaves: 3,
      noise_scale: 8,
    },
    {
      zone_id: 'northern_mountain',
      shape: { kind: 'rect', bounds: { x: 0, y: 0, w: 64, h: 12 } },
      biome_weights: { Mountain: 0.6, Forest: 0.25, Snow: 0.1, Grass: 0.05 },
      noise_octaves: 4,
      noise_scale: 8,
    },
    {
      zone_id: 'mountain_foothill',
      shape: { kind: 'rect', bounds: { x: 0, y: 12, w: 64, h: 8 } },
      biome_weights: { Forest: 0.5, Mountain: 0.3, Grass: 0.2 },
      noise_octaves: 3,
      noise_scale: 6,
    },
    {
      zone_id: 'western_forest',
      shape: { kind: 'rect', bounds: { x: 0, y: 20, w: 16, h: 24 } },
      biome_weights: { Forest: 0.7, Grass: 0.2, Mountain: 0.1 },
      noise_octaves: 3,
      noise_scale: 6,
    },
    {
      zone_id: 'eastern_grass',
      shape: { kind: 'rect', bounds: { x: 48, y: 20, w: 16, h: 24 } },
      biome_weights: { Grass: 0.6, Forest: 0.2, Sand: 0.2 },
      noise_octaves: 2,
      noise_scale: 8,
    },
    {
      zone_id: 'southern_lake',
      shape: { kind: 'rect', bounds: { x: 0, y: 44, w: 64, h: 12 } },
      biome_weights: { Water: 0.55, Sand: 0.25, Grass: 0.2 },
      noise_octaves: 2,
      noise_scale: 10,
    },
    {
      zone_id: 'southern_coast',
      shape: { kind: 'rect', bounds: { x: 0, y: 56, w: 64, h: 8 } },
      biome_weights: { Sand: 0.5, Water: 0.3, Grass: 0.2 },
      noise_octaves: 2,
      noise_scale: 10,
    },
  ],
  cell_anchors: [
    {
      channel_id: 'cell:kinh_do',
      tier: 'Town',
      position: { x: 32, y: 30 },
      kind: 'capital',
      display_name: 'Kinh Đô',
    },
    {
      channel_id: 'cell:bac_son_thai',
      tier: 'Town',
      position: { x: 22, y: 8 },
      kind: 'fortress',
      display_name: 'Bắc Sơn Thái',
    },
    {
      channel_id: 'cell:tay_van_vien',
      tier: 'Town',
      position: { x: 8, y: 26 },
      kind: 'temple',
      display_name: 'Tây Vân Viện',
    },
    {
      channel_id: 'cell:dong_phuong_lau',
      tier: 'Town',
      position: { x: 54, y: 26 },
      kind: 'tavern',
      display_name: 'Đông Phương Lâu',
    },
    {
      channel_id: 'cell:nam_hai_cang',
      tier: 'Town',
      position: { x: 32, y: 54 },
      kind: 'port',
      display_name: 'Nam Hải Cảng',
    },
    {
      channel_id: 'cell:tay_thi_quan',
      tier: 'Cell',
      position: { x: 28, y: 32 },
      kind: 'cell',
      display_name: 'Tây Thị Quán',
    },
    {
      channel_id: 'cell:yen_vu_lau',
      tier: 'Cell',
      position: { x: 36, y: 32 },
      kind: 'cell',
      display_name: 'Yên Vũ Lâu',
    },
  ],
  landmark_anchors: [
    {
      object_id: 'landmark:rong_phong',
      kind: 'Landmark',
      position: { x: 12, y: 4 },
      display_name: 'Rồng Phong',
    },
    {
      object_id: 'landmark:phuong_ho',
      kind: 'Landmark',
      position: { x: 32, y: 50 },
      display_name: 'Phượng Hồ',
    },
    {
      object_id: 'landmark:co_tich',
      kind: 'Ruin',
      position: { x: 50, y: 40 },
      display_name: 'Cổ Tích Thành',
    },
    {
      object_id: 'landmark:hac_long_de',
      kind: 'MonsterLair',
      position: { x: 14, y: 14 },
      display_name: 'Hắc Long Đệ',
    },
    {
      object_id: 'landmark:tien_kim_quang',
      kind: 'Treasure',
      position: { x: 56, y: 14 },
      display_name: 'Tiên Kim Quặng',
    },
    {
      object_id: 'landmark:bach_van_tu',
      kind: 'Decoration',
      position: { x: 4, y: 52 },
      display_name: 'Bạch Vân Tự',
    },
    {
      object_id: 'landmark:huyen_thiet_khoang',
      kind: 'Mine',
      position: { x: 44, y: 6 },
      display_name: 'Huyền Thiết Khoáng',
    },
  ],
  road_connections: [
    { from: 'cell:kinh_do', to: 'cell:bac_son_thai', kind: 'Highway' },
    { from: 'cell:kinh_do', to: 'cell:tay_van_vien', kind: 'Path' },
    { from: 'cell:kinh_do', to: 'cell:dong_phuong_lau', kind: 'Highway' },
    { from: 'cell:kinh_do', to: 'cell:nam_hai_cang', kind: 'Trade' },
    { from: 'cell:tay_van_vien', to: 'cell:nam_hai_cang', kind: 'Path' },
    { from: 'cell:dong_phuong_lau', to: 'cell:bac_son_thai', kind: 'Trade' },
  ],
};
