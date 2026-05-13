import { describe, expect, it } from 'vitest';
import { validateSkeleton } from '../src/llm/validator';
import { KINGDOM_DEFAULT } from '../src/data/skeleton';

describe('LLM skeleton validator', () => {
  it('canonical KINGDOM_DEFAULT validates clean', () => {
    const result = validateSkeleton(KINGDOM_DEFAULT);
    if (!result.valid) console.error('Errors:', result.errors);
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  it('rejects non-object input', () => {
    const result = validateSkeleton('not an object');
    expect(result.valid).toBe(false);
    expect(result.errors[0]).toContain('Top-level value');
  });

  it('rejects missing required fields', () => {
    const result = validateSkeleton({});
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it('rejects bad grid size', () => {
    const result = validateSkeleton({
      ...KINGDOM_DEFAULT,
      grid_size: { width: 32, height: 32 },
    });
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes('grid_size'))).toBe(true);
  });

  it('rejects out-of-bounds cell position', () => {
    const result = validateSkeleton({
      ...KINGDOM_DEFAULT,
      cell_anchors: [
        ...KINGDOM_DEFAULT.cell_anchors.slice(0, -1),
        {
          ...KINGDOM_DEFAULT.cell_anchors[KINGDOM_DEFAULT.cell_anchors.length - 1],
          position: { x: 100, y: 200 },
        },
      ],
    });
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes('position'))).toBe(true);
  });

  it('rejects invalid TerrainKind in biome_weights', () => {
    const result = validateSkeleton({
      ...KINGDOM_DEFAULT,
      terrain_zones: [
        {
          ...KINGDOM_DEFAULT.terrain_zones[0],
          biome_weights: { Lava: 1.0 }, // invalid kind
        },
        ...KINGDOM_DEFAULT.terrain_zones.slice(1),
      ],
    });
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes('Lava'))).toBe(true);
  });

  it('rejects biome_weights not summing to 1', () => {
    const result = validateSkeleton({
      ...KINGDOM_DEFAULT,
      terrain_zones: [
        {
          ...KINGDOM_DEFAULT.terrain_zones[0],
          biome_weights: { Grass: 0.3, Forest: 0.3 }, // sums to 0.6
        },
        ...KINGDOM_DEFAULT.terrain_zones.slice(1),
      ],
    });
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes('sum'))).toBe(true);
  });

  it('rejects road referencing nonexistent cell', () => {
    const result = validateSkeleton({
      ...KINGDOM_DEFAULT,
      road_connections: [
        ...KINGDOM_DEFAULT.road_connections,
        { from: 'cell:nonexistent', to: 'cell:kinh_do', kind: 'Path' as const },
      ],
    });
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes('nonexistent'))).toBe(true);
  });

  it('rejects disconnected cell graph', () => {
    const result = validateSkeleton({
      ...KINGDOM_DEFAULT,
      cell_anchors: [
        ...KINGDOM_DEFAULT.cell_anchors,
        {
          channel_id: 'cell:isolated',
          tier: 'Town' as const,
          position: { x: 60, y: 0 },
          kind: 'cell' as const,
          display_name: 'Isolated',
        },
      ],
      // road_connections unchanged — isolated has no road
    });
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes('Unreachable'))).toBe(true);
  });

  it('rejects missing capital', () => {
    const result = validateSkeleton({
      ...KINGDOM_DEFAULT,
      cell_anchors: KINGDOM_DEFAULT.cell_anchors.map((c) =>
        c.kind === 'capital' ? { ...c, kind: 'cell' as const } : c,
      ),
    });
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes('capital'))).toBe(true);
  });

  it('rejects duplicate channel_id', () => {
    const result = validateSkeleton({
      ...KINGDOM_DEFAULT,
      cell_anchors: [
        ...KINGDOM_DEFAULT.cell_anchors,
        { ...KINGDOM_DEFAULT.cell_anchors[0] }, // duplicate id
      ],
    });
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes('duplicated'))).toBe(true);
  });

  it('rejects channel_id without "cell:" prefix', () => {
    const result = validateSkeleton({
      ...KINGDOM_DEFAULT,
      cell_anchors: [
        {
          ...KINGDOM_DEFAULT.cell_anchors[0],
          channel_id: 'no_prefix',
        },
        ...KINGDOM_DEFAULT.cell_anchors.slice(1),
      ],
    });
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes('cell:'))).toBe(true);
  });

  it('rejects landmark with invalid kind', () => {
    const result = validateSkeleton({
      ...KINGDOM_DEFAULT,
      landmark_anchors: [
        {
          ...KINGDOM_DEFAULT.landmark_anchors[0],
          kind: 'Volcano' as never, // not in enum
        },
      ],
    });
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes('kind'))).toBe(true);
  });
});
