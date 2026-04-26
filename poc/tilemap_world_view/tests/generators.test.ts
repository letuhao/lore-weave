import { describe, expect, it } from 'vitest';
import { composeTileMap } from '../src/generators/tilemap';
import { generateTerrain } from '../src/generators/terrain';
import { placeRoads } from '../src/generators/roads';
import { mulberry32, hash2D } from '../src/generators/prng';
import { valueNoise2D, fbm2D } from '../src/generators/noise';
import { KINGDOM_DEFAULT } from '../src/data/skeleton';
import { indexToTerrain, terrainToIndex } from '../src/data/types';

describe('PRNG — Mulberry32', () => {
  it('same seed → identical sequence', () => {
    const a = mulberry32(42);
    const b = mulberry32(42);
    for (let i = 0; i < 100; i++) {
      expect(a()).toBe(b());
    }
  });

  it('different seeds → different sequence', () => {
    const a = mulberry32(42);
    const b = mulberry32(43);
    let same = 0;
    for (let i = 0; i < 100; i++) {
      if (a() === b()) same++;
    }
    expect(same).toBeLessThan(2);
  });
});

describe('PRNG — hash2D', () => {
  it('pure function: same (x,y,seed) → same value', () => {
    expect(hash2D(5, 7, 42)).toBe(hash2D(5, 7, 42));
    expect(hash2D(0, 0, 42)).toBe(hash2D(0, 0, 42));
  });

  it('different (x,y) → different value (high probability)', () => {
    const a = hash2D(0, 0, 42);
    const b = hash2D(1, 0, 42);
    const c = hash2D(0, 1, 42);
    expect(a).not.toBe(b);
    expect(a).not.toBe(c);
    expect(b).not.toBe(c);
  });

  it('output range 0..1', () => {
    for (let x = 0; x < 50; x++) {
      for (let y = 0; y < 50; y++) {
        const v = hash2D(x, y, 42);
        expect(v).toBeGreaterThanOrEqual(0);
        expect(v).toBeLessThan(1);
      }
    }
  });
});

describe('Noise', () => {
  it('value noise determinism', () => {
    const n1 = valueNoise2D(42);
    const n2 = valueNoise2D(42);
    for (let i = 0; i < 20; i++) {
      const x = Math.random() * 100;
      const y = Math.random() * 100;
      expect(n1(x, y)).toBe(n2(x, y));
    }
  });

  it('fBm produces values in 0..1', () => {
    const n = valueNoise2D(42);
    for (let i = 0; i < 50; i++) {
      const v = fbm2D(n, i * 0.3, i * 0.7, 4);
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(1);
    }
  });
});

describe('Terrain enum mapping', () => {
  it('terrainToIndex round-trips via indexToTerrain', () => {
    const kinds = ['Grass', 'Forest', 'Mountain', 'Water', 'Road'] as const;
    for (const k of kinds) {
      expect(indexToTerrain(terrainToIndex(k))).toBe(k);
    }
  });
});

describe('L2 Terrain generation', () => {
  it('produces correct grid size', () => {
    const terrain = generateTerrain(KINGDOM_DEFAULT, 42);
    const expected = KINGDOM_DEFAULT.grid_size.width * KINGDOM_DEFAULT.grid_size.height;
    expect(terrain.length).toBe(expected);
  });

  it('all values are valid TerrainKind indices', () => {
    const terrain = generateTerrain(KINGDOM_DEFAULT, 42);
    for (const idx of terrain) {
      expect(idx).toBeGreaterThanOrEqual(0);
      expect(idx).toBeLessThan(10); // 10 TerrainKind variants
    }
  });

  it('determinism: same seed → identical terrain array', () => {
    const a = generateTerrain(KINGDOM_DEFAULT, 42);
    const b = generateTerrain(KINGDOM_DEFAULT, 42);
    expect(a).toEqual(b);
  });

  it('different seeds → different terrain', () => {
    const a = generateTerrain(KINGDOM_DEFAULT, 42);
    const b = generateTerrain(KINGDOM_DEFAULT, 99);
    expect(a).not.toEqual(b);
  });
});

describe('L2 Road placement', () => {
  it('produces road segments matching skeleton.road_connections count', () => {
    const terrain = generateTerrain(KINGDOM_DEFAULT, 42);
    const { roads } = placeRoads(KINGDOM_DEFAULT, terrain);
    expect(roads.length).toBe(KINGDOM_DEFAULT.road_connections.length);
  });

  it('every road segment has start = from cell position; end = to cell position', () => {
    const terrain = generateTerrain(KINGDOM_DEFAULT, 42);
    const { roads } = placeRoads(KINGDOM_DEFAULT, terrain);
    for (const road of roads) {
      const from = KINGDOM_DEFAULT.cell_anchors.find(
        (c) => c.channel_id === road.from_channel_id,
      )!;
      const to = KINGDOM_DEFAULT.cell_anchors.find((c) => c.channel_id === road.to_channel_id)!;
      expect(road.waypoints[0]).toEqual(from.position);
      expect(road.waypoints[road.waypoints.length - 1]).toEqual(to.position);
    }
  });

  it('determinism: same input terrain → identical road waypoints', () => {
    const terrain = generateTerrain(KINGDOM_DEFAULT, 42);
    const a = placeRoads(KINGDOM_DEFAULT, terrain);
    const b = placeRoads(KINGDOM_DEFAULT, terrain);
    expect(a.roads).toEqual(b.roads);
    expect(a.updatedTerrain).toEqual(b.updatedTerrain);
  });
});

describe('TileMapView composition (replay-determinism per EVT-A9)', () => {
  it('same seed → byte-identical TileMapView (modulo timestamp)', () => {
    const a = composeTileMap(KINGDOM_DEFAULT, 42, 'continent:test', 'Continent');
    const b = composeTileMap(KINGDOM_DEFAULT, 42, 'continent:test', 'Continent');
    // Strip timestamp (only field that varies between calls)
    const stripped = (v: typeof a) => ({ ...v, generated_at: '0' });
    expect(stripped(a)).toEqual(stripped(b));
  });

  it('different seeds → different terrain layer', () => {
    const a = composeTileMap(KINGDOM_DEFAULT, 42, 'continent:test', 'Continent');
    const b = composeTileMap(KINGDOM_DEFAULT, 99, 'continent:test', 'Continent');
    expect(a.terrain_layer).not.toEqual(b.terrain_layer);
  });

  it('output schema matches expected aggregate fields', () => {
    const view = composeTileMap(KINGDOM_DEFAULT, 42, 'continent:test', 'Continent');
    expect(view.channel_id).toBe('continent:test');
    expect(view.tier).toBe('Continent');
    expect(view.skeleton_id).toBe('kingdom_default');
    expect(view.procedural_seed).toBe(42);
    expect(view.grid_size).toEqual({ width: 64, height: 64 });
    expect(view.terrain_layer).toBeInstanceOf(Array);
    expect(view.roads).toBeInstanceOf(Array);
    expect(view.cell_placements.length).toBe(KINGDOM_DEFAULT.cell_anchors.length);
    expect(view.object_placements.length).toBe(KINGDOM_DEFAULT.landmark_anchors.length);
    expect(view.layer3_source.kind).toBe('CanonicalDefault');
    expect(view.region_narration).toBeNull();
    expect(view.prompt_template_version).toBe(1);
  });

  it('JSON serializable (round-trip preserves all fields)', () => {
    const a = composeTileMap(KINGDOM_DEFAULT, 42, 'continent:test', 'Continent');
    const json = JSON.stringify(a);
    const b = JSON.parse(json);
    expect(b).toEqual(a);
  });
});
