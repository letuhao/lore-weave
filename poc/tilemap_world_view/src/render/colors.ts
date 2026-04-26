import type { TerrainKind, MapObjectKind, CellKind, RoadKind } from '../data/types';

/**
 * Terrain color palette — Kenney-pack-aligned tones (sample1.png reference).
 *
 * Updated 2026-04-27 PoC v2: brighter, more saturated, closer to HOMM-like
 * fantasy overworld feel. Old palette was muted/dark; new palette mirrors
 * Kenney Roguelike RPG Pack base terrain colors so colored-square fallback
 * blends seamlessly when sprite atlas is partially loaded.
 */
export const TERRAIN_COLOR: Record<TerrainKind, number> = {
  Grass: 0x6dac4a, // bright grass (matches Kenney sample)
  Forest: 0x3d7c2a, // darker grass for forest base (trees overlay on top)
  Mountain: 0x9c8a72, // tan/grey rock
  Water: 0x4a9bc4, // cyan-blue water (matches Kenney sample lake)
  Sand: 0xd4b97a, // warm sand
  Snow: 0xeaf0f5, // cool white
  Swamp: 0x5a7045, // muddy green
  Road: 0xa68852, // dirt path
  Rough: 0x8c7858, // rocky ground
  Subterranean: 0x3a3344, // dark cave
};

/** Slight per-tile variation to add texture without sprite art. */
export function variantColor(base: number, variant: number): number {
  // Adjust each channel by ±12 based on variant 0..1
  const r = (base >> 16) & 0xff;
  const g = (base >> 8) & 0xff;
  const b = base & 0xff;
  const adj = Math.floor((variant - 0.5) * 24);
  const clamp = (v: number): number => Math.max(0, Math.min(255, v + adj));
  return (clamp(r) << 16) | (clamp(g) << 8) | clamp(b);
}

/** Darker shoreline color — drawn at Water/Land boundary tiles. */
export const SHORELINE_COLOR = 0x355c75;

/** Mountain ridge highlight — drawn at Mountain edge tiles. */
export const MOUNTAIN_RIDGE_COLOR = 0xb8a690;

export const ROAD_COLOR: Record<RoadKind, number> = {
  Highway: 0xc4a777,
  Trade: 0xb88859,
  Path: 0x8a7050,
};

export const OBJECT_EMOJI: Record<MapObjectKind | CellKind, string> = {
  // CellKind
  capital: '🏰',
  fortress: '🛡️',
  temple: '⛩️',
  tavern: '🍵',
  port: '⚓',
  cell: '🏠',
  cave: '🕳️',
  // MapObjectKind
  Treasure: '💎',
  MonsterLair: '🐉',
  Landmark: '🗻',
  Decoration: '🌳',
  Mine: '⛏️',
  Portal: '🌀',
  Ruin: '🏛️',
};
