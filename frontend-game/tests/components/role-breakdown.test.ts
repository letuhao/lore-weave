import { describe, expect, it } from 'vitest';
import { computeRoleBreakdown } from '../../src/components/viewer/role-breakdown';
import {
  ZONE_ROLE_DEFAULTS,
  ZONE_ROLE_FALLBACK,
} from '../../src/game/render/zone-role-palette';
import type { TilemapView, ZoneRuntime } from '../../src/types/tilemap';

// TMP-Q5 chunk B — per-role aggregate row derivation for the
// MetadataPanel breakdown section.

// LOW-3 from chunk-B /review-impl — the union type accepts known
// `ZoneRole` strings + `(string & {})` keeps the IDE autocomplete
// suggesting valid values WITHOUT erroring on legitimate test cases
// that need unknown roles (e.g., the FE-only "arena" + the "totally
// unknown" defensive cases). A future test author who writes
// `'wilderness_typo'` would still compile, but the IDE highlights it
// as "not a known suggestion" — a soft signal beats the original
// silent cast.
type TestRoleInput = ZoneRuntime['zone_role'] | (string & {});

function zone(
  zone_id: string,
  zone_role: TestRoleInput,
  overrides: Partial<ZoneRuntime> = {},
): ZoneRuntime {
  return {
    zone_id,
    zone_role: zone_role as ZoneRuntime['zone_role'],
    center_position: { x: 0, y: 0 },
    terrain_type: 'grass',
    ...overrides,
  };
}

function viewWith(zones: ZoneRuntime[], registry_ref?: TilemapView['registry_ref']): TilemapView {
  return {
    channel_id: 'unit',
    tier: 'town',
    grid_size: { width: 4, height: 4 },
    template_id: 't',
    seed: 1,
    zones,
    terrain_layer: new Array(16).fill(1),
    object_placements: [],
    road_segments: [],
    river_segments: [],
    child_cell_anchors: {},
    generation_source: { kind: 'engine_generated' },
    prompt_template_version: 0,
    registry_ref,
  };
}

describe('TMP-Q5 chunk B — computeRoleBreakdown', () => {
  it('returns empty rows for a view with no zones', () => {
    expect(computeRoleBreakdown(viewWith([]))).toEqual([]);
  });

  it('counts zones per role + populates zone_ids', () => {
    const view = viewWith([
      zone('a', 'wilderness'),
      zone('b', 'wilderness'),
      zone('c', 'hub'),
    ]);
    const rows = computeRoleBreakdown(view);
    expect(rows).toHaveLength(2);
    // Sort: count DESC. Wilderness (2) before Hub (1).
    expect(rows[0]?.role).toBe('wilderness');
    expect(rows[0]?.count).toBe(2);
    expect(rows[0]?.zone_ids).toEqual(['a', 'b']);
    expect(rows[1]?.role).toBe('hub');
    expect(rows[1]?.count).toBe(1);
  });

  it('sorts ties alphabetically by role (deterministic)', () => {
    // Same count for wilderness and hub → role asc tiebreaker.
    const view = viewWith([
      zone('a', 'wilderness'),
      zone('b', 'hub'),
    ]);
    const rows = computeRoleBreakdown(view);
    expect(rows).toHaveLength(2);
    // hub < wilderness alphabetically.
    expect(rows[0]?.role).toBe('hub');
    expect(rows[1]?.role).toBe('wilderness');
  });

  it('uses ZONE_ROLE_DEFAULTS when registry omits the override', () => {
    const view = viewWith([zone('a', 'wilderness')]);
    const rows = computeRoleBreakdown(view);
    expect(rows[0]?.color).toBe(ZONE_ROLE_DEFAULTS.wilderness);
  });

  it('uses per-book override when registry declares zone_role_colors', () => {
    const view = viewWith(
      [zone('a', 'wilderness')],
      {
        id: 'xianxia',
        version: '1.0.0',
        zone_role_colors: { wilderness: 0xfacc15 },
      },
    );
    const rows = computeRoleBreakdown(view);
    expect(rows[0]?.color).toBe(0xfacc15);
  });

  it('respects sparse override (mix of override + defaults)', () => {
    const view = viewWith(
      [
        zone('a', 'wilderness'),
        zone('b', 'hub'),
      ],
      {
        id: 'xianxia',
        version: '1.0.0',
        zone_role_colors: { wilderness: 0xfacc15 }, // sparse — no hub override
      },
    );
    const rows = computeRoleBreakdown(view);
    const wildernessRow = rows.find((r) => r.role === 'wilderness');
    const hubRow = rows.find((r) => r.role === 'hub');
    expect(wildernessRow?.color).toBe(0xfacc15);
    expect(hubRow?.color).toBe(ZONE_ROLE_DEFAULTS.hub);
  });

  it('FALLBACK color for unknown roles (FE-type-wider gap)', () => {
    const view = viewWith([zone('a', 'arena')]); // arena ∈ FE type, not BE wire
    const rows = computeRoleBreakdown(view);
    expect(rows[0]?.color).toBe(ZONE_ROLE_FALLBACK);
  });

  it('zone_ids per row are sorted (deterministic)', () => {
    const view = viewWith([
      zone('zebra', 'wilderness'),
      zone('alpha', 'wilderness'),
      zone('mango', 'wilderness'),
    ]);
    const rows = computeRoleBreakdown(view);
    expect(rows[0]?.zone_ids).toEqual(['alpha', 'mango', 'zebra']);
  });

  it('LOW-4 — sum of row counts equals view.zones.length (sum invariant)', () => {
    // LOW-4 from chunk-B /review-impl — the MetadataPanel summary
    // reads "(rows.length roles · view.zones.length zones)". Today
    // the sum of per-row counts trivially equals total zone count
    // (every zone goes into exactly one row); future filtering
    // (e.g., "exclude Forbidden from breakdown") would silently
    // break the summary's math. This test pins the invariant so
    // such a filter has to either update the summary or accept the
    // test failure.
    const view = viewWith([
      zone('a', 'wilderness'),
      zone('b', 'wilderness'),
      zone('c', 'hub'),
      zone('d', 'forbidden'),
      zone('e', 'sea'),
    ]);
    const rows = computeRoleBreakdown(view);
    const totalFromRows = rows.reduce((sum, row) => sum + row.count, 0);
    expect(totalFromRows).toBe(view.zones.length);
  });
});
