import { describe, expect, it } from 'vitest';
import {
  computeDecorationFamilyBreakdown,
  FAMILY_NONE,
  isDecorationPlacement,
} from '../../src/components/viewer/decoration-family-breakdown';
import type {
  TilemapObjectPlacement,
  TilemapView,
} from '../../src/types/tilemap';

// TMP-Q6 chunk C — per-family decoration breakdown helper. Pure function;
// no DOM, no async, deterministic given (view).

function placement(
  kind: TilemapObjectPlacement['kind'],
  family: string | undefined,
  overrides: Partial<TilemapObjectPlacement> = {},
): TilemapObjectPlacement {
  return {
    kind,
    anchor: { x: 0, y: 0 },
    family,
    ...overrides,
  };
}

function viewWith(placements: TilemapObjectPlacement[]): TilemapView {
  return {
    channel_id: 'unit',
    tier: 'town',
    grid_size: { width: 4, height: 4 },
    template_id: 't',
    seed: 1,
    zones: [],
    terrain_layer: new Array(16).fill(1),
    object_placements: placements,
    road_segments: [],
    river_segments: [],
    child_cell_anchors: {},
    generation_source: { kind: 'engine_generated' },
    prompt_template_version: 0,
  };
}

describe('TMP-Q6 chunk C — computeDecorationFamilyBreakdown', () => {
  it('returns empty rows for an empty view', () => {
    expect(computeDecorationFamilyBreakdown(viewWith([]))).toEqual([]);
  });

  it('returns empty rows when no decoration placements exist (filters by semantic)', () => {
    // Mix of non-decoration kinds should produce 0 rows — confirms the
    // helper filters by SEMANTIC kind, not by tag-prefix or family-presence.
    const view = viewWith([
      placement('treasure', undefined),
      placement('monster_lair', undefined),
      placement('town', undefined),
    ]);
    expect(computeDecorationFamilyBreakdown(view)).toEqual([]);
  });

  it('counts placements per family + percent rounds to 1 decimal', () => {
    const view = viewWith([
      placement('decoration', 'rock'),
      placement('decoration', 'rock'),
      placement('decoration', 'rock'),
      placement('decoration', 'vegetation'),
    ]);
    const rows = computeDecorationFamilyBreakdown(view);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toEqual({ family: 'rock', count: 3, percent: 75.0 });
    expect(rows[1]).toEqual({ family: 'vegetation', count: 1, percent: 25.0 });
  });

  it('sorts desc by count; ties broken alphabetically asc by family', () => {
    const view = viewWith([
      // 2 of vegetation + 2 of rock → tie, then 1 bone.
      placement('decoration', 'vegetation'),
      placement('decoration', 'vegetation'),
      placement('decoration', 'rock'),
      placement('decoration', 'rock'),
      placement('decoration', 'bone'),
    ]);
    const rows = computeDecorationFamilyBreakdown(view);
    // Tie: rock before vegetation alphabetically.
    expect(rows[0]?.family).toBe('rock');
    expect(rows[1]?.family).toBe('vegetation');
    expect(rows[2]?.family).toBe('bone');
  });

  it("buckets unfamilied decoration placements as 'none' (visible, not dropped)", () => {
    const view = viewWith([
      placement('decoration', 'rock'),
      placement('decoration', undefined), // legacy / TYPE-marker
      placement('decoration', undefined),
    ]);
    const rows = computeDecorationFamilyBreakdown(view);
    expect(rows).toHaveLength(2);
    // Tie at 2 each: none sorts before rock alphabetically.
    expect(rows[0]?.family).toBe(FAMILY_NONE);
    expect(rows[0]?.count).toBe(2);
    expect(rows[1]?.family).toBe('rock');
  });

  it('ignores placements of non-decoration kinds even if they carry family', () => {
    // Defensive: a non-decoration placement with a stray `family` value
    // (impossible per backend, but pinning intent) must be skipped.
    const view = viewWith([
      placement('decoration', 'rock'),
      // synthetic: treasure with a family — placer would never do this,
      // but the FE helper must not be brittle to it.
      placement('treasure', 'rock'),
    ]);
    const rows = computeDecorationFamilyBreakdown(view);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.count).toBe(1); // only the decoration counted
  });

  it('LOW-1 invariant — sum of row counts equals total decoration placements (mirrors role-breakdown)', () => {
    // Parallel to `LOW-4 — sum of row counts equals view.zones.length`
    // in role-breakdown. Pins the math invariant that the MetadataPanel
    // summary copy "(N families · M decorations)" relies on. A future
    // filter (e.g., "exclude `none` family") would silently break the
    // summary's M unless this test or the summary is updated together.
    const view = viewWith([
      placement('decoration', 'rock'),
      placement('decoration', 'rock'),
      placement('decoration', 'vegetation'),
      placement('decoration', 'bone'),
      placement('decoration', undefined),
      placement('treasure', undefined), // not counted (kind filter)
    ]);
    const rows = computeDecorationFamilyBreakdown(view);
    const sumFromRows = rows.reduce((sum, r) => sum + r.count, 0);
    const totalDecorations = view.object_placements.filter(
      (p) => p.kind === 'decoration',
    ).length;
    expect(sumFromRows).toBe(totalDecorations);
    expect(totalDecorations).toBe(5);
  });

  it('LOW-2 invariant — percent sum approximates 100% within rounding tolerance', () => {
    // Sanity: 3 buckets at 5/4/3 = 12 total → 41.7% / 33.3% / 25.0%.
    // Sum is 100.0 exact when rounding lines up; allow ±0.1 tolerance
    // for f64 imprecision.
    const view = viewWith([
      placement('decoration', 'rock'),
      placement('decoration', 'rock'),
      placement('decoration', 'rock'),
      placement('decoration', 'rock'),
      placement('decoration', 'rock'),
      placement('decoration', 'vegetation'),
      placement('decoration', 'vegetation'),
      placement('decoration', 'vegetation'),
      placement('decoration', 'vegetation'),
      placement('decoration', 'bone'),
      placement('decoration', 'bone'),
      placement('decoration', 'bone'),
    ]);
    const rows = computeDecorationFamilyBreakdown(view);
    const totalPercent = rows.reduce((sum, r) => sum + r.percent, 0);
    expect(Math.abs(totalPercent - 100.0)).toBeLessThanOrEqual(0.2);
  });

  it('MED-1 — kind=decoration counts even when primitive is undefined (pre-V2 fixtures)', () => {
    // MED-1 from chunk-C /review-impl: the shared `isDecorationPlacement`
    // predicate uses (primitive OR kind) so pre-V2 fixtures (kind set,
    // primitive undefined) still register. This test pins that legacy
    // path so a future "simplify to primitive-only" refactor would fail
    // here BEFORE silently dropping pre-V2 placements from the breakdown.
    const view = viewWith([
      // Pre-V2: kind set, no primitive.
      { kind: 'decoration', anchor: { x: 0, y: 0 }, family: 'rock' },
    ]);
    const rows = computeDecorationFamilyBreakdown(view);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.family).toBe('rock');
  });

  it('MED-1 — primitive=decoration counts even when kind diverges (V2-only future path)', () => {
    // MED-1 from chunk-C /review-impl: forward-compat for per-book
    // registries that declare new kinds with primitive: 'decoration'
    // semantics. The shared predicate accepts EITHER signal so this
    // future path is captured the moment it becomes real.
    const view = viewWith([
      {
        kind: 'landmark', // synthetic — V1 enum, not 'decoration'
        primitive: 'decoration',
        anchor: { x: 0, y: 0 },
        family: 'vegetation',
      },
    ]);
    const rows = computeDecorationFamilyBreakdown(view);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.family).toBe('vegetation');
  });

  it('MED-1 + LOW-6 — sentinel is _unfamilied (cannot collide with valid family name)', () => {
    // LOW-6 from chunk-C /review-impl: the FAMILY_NONE sentinel starts
    // with underscore so it CANNOT match the backend's
    // is_valid_family_id regex `^[a-z][a-z0-9_]*$`. If a per-book
    // registry author ever declares a family literally named 'none',
    // their placements would NOT silently bucket with truly-unfamilied
    // entries — they'd correctly appear under 'none'.
    expect(FAMILY_NONE).toBe('_unfamilied');
    expect(FAMILY_NONE[0]).toBe('_');
  });

  it('isDecorationPlacement predicate accepts both kind-only AND primitive-only forms', () => {
    // Defensive unit test for the shared predicate itself, so a future
    // change to its implementation doesn't silently drift either
    // surface.
    expect(
      isDecorationPlacement({ kind: 'decoration', anchor: { x: 0, y: 0 } }),
    ).toBe(true);
    expect(
      isDecorationPlacement({
        kind: 'landmark',
        primitive: 'decoration',
        anchor: { x: 0, y: 0 },
      }),
    ).toBe(true);
    expect(
      isDecorationPlacement({
        kind: 'treasure',
        primitive: 'pickup',
        anchor: { x: 0, y: 0 },
      }),
    ).toBe(false);
    expect(
      isDecorationPlacement({ kind: 'treasure', anchor: { x: 0, y: 0 } }),
    ).toBe(false);
  });

  it('accepts a registry argument but is currently a no-op (API parity)', () => {
    // computeDecorationFamilyBreakdown(view, registry) — the registry
    // arg is reserved for future enrichment (e.g., per-family color
    // from registry.decoration_family_density). Chunk-C v1 does not
    // consult it; this test pins the API parity so callers can pass
    // the registry now and the helper signature won't change later.
    const view = viewWith([placement('decoration', 'rock')]);
    const rows_no_registry = computeDecorationFamilyBreakdown(view);
    const rows_with_registry = computeDecorationFamilyBreakdown(view, {
      decoration_family_density: { rock: 1.8 },
    });
    expect(rows_with_registry).toEqual(rows_no_registry);
  });
});
