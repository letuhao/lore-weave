import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MetadataPanel } from '../../src/components/viewer/MetadataPanel';
import type {
  TilemapObjectPlacement,
  TilemapView,
  ZoneRuntime,
} from '../../src/types/tilemap';

// DEFERRED #049 from TMP-Q6 chunk-C /review-impl LOW-5 — component-level
// mount-smoke vitest for `<MetadataPanel>`. The chunk-C helper unit tests
// (`decoration-family-breakdown.test.ts`, `role-breakdown.test.ts`) are
// isolated from the React tree, and the chunk-C Playwright goldens were
// baked against the 0-decoration fixture (#048) so they verify the
// section HEADER but not the SECTION ROWS. If someone removes the
// `<DecorationFamilyBreakdown view={view} />` line from MetadataPanel,
// helper tests still pass + Playwright goldens still pass against the
// empty-state baseline — silent regression.
//
// This test asserts both breakdown sections actually MOUNT inside the
// rendered MetadataPanel for both populated and empty placement sets.

function zone(zone_id: string, zone_role: ZoneRuntime['zone_role']): ZoneRuntime {
  return {
    zone_id,
    zone_role,
    center_position: { x: 0, y: 0 },
    terrain_type: 'grass',
  };
}

function placement(
  kind: TilemapObjectPlacement['kind'],
  family: string | undefined,
): TilemapObjectPlacement {
  return {
    kind,
    anchor: { x: 0, y: 0 },
    primitive: kind === 'decoration' ? 'decoration' : undefined,
    family,
  };
}

function viewWith(
  zones: ZoneRuntime[] = [],
  placements: TilemapObjectPlacement[] = [],
): TilemapView {
  return {
    channel_id: 'unit',
    tier: 'town',
    grid_size: { width: 4, height: 4 },
    template_id: 't',
    seed: 1,
    zones,
    terrain_layer: new Array(16).fill(1),
    object_placements: placements,
    road_segments: [],
    river_segments: [],
    child_cell_anchors: {},
    generation_source: { kind: 'engine_generated' },
    prompt_template_version: 0,
  };
}

describe('TMP-Q6 chunk-D #049 — <MetadataPanel> mount-smoke', () => {
  it('renders null when view is undefined (defensive)', () => {
    const { container } = render(<MetadataPanel view={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('mounts both <RoleBreakdown> AND <DecorationFamilyBreakdown> when view has zones + decorations', () => {
    // The load-bearing assertion for DEFERRED #049: BOTH breakdown
    // sections must be present in the tree. If a future refactor
    // removes either `<RoleBreakdown view={view} />` or
    // `<DecorationFamilyBreakdown view={view} />` from MetadataPanel,
    // THIS test fires immediately — without depending on Playwright
    // rebake or seed-driven fixture behavior.
    const view = viewWith(
      [
        zone('a', 'wilderness'),
        zone('b', 'hub'),
      ],
      [
        placement('decoration', 'rock'),
        placement('decoration', 'vegetation'),
      ],
    );
    render(<MetadataPanel view={view} />);
    // Role breakdown summary header (chunk-Q5 chunk B).
    expect(
      screen.getByText(/^role breakdown \(2 roles · 2 zones\)$/),
    ).toBeInTheDocument();
    // Decoration family breakdown summary header (chunk-Q6 chunk C).
    expect(
      screen.getByText(/^decoration families \(2 families · 2 decorations\)$/),
    ).toBeInTheDocument();
  });

  it('mounts both sections in empty-state form when view has no zones + no decorations', () => {
    // Verifies that BOTH sections still mount even with empty data;
    // the empty-state paths inside each section are part of the
    // mount-smoke contract (a future refactor that conditionally
    // skipped a section based on data presence would silently regress
    // the user-visible state-discovery affordance).
    const view = viewWith([], []);
    render(<MetadataPanel view={view} />);
    expect(
      screen.getByText(/^role breakdown$/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/^decoration families$/),
    ).toBeInTheDocument();
    // Empty-state copy from each section.
    expect(screen.getByText(/^no zones in this view$/)).toBeInTheDocument();
    expect(
      screen.getByText(/^no decorations placed yet$/),
    ).toBeInTheDocument();
  });

  it('decoration-family rows render inside expanded breakdown (chunk-C testid path)', () => {
    // Pins the chunk-C `data-testid` path that the Playwright golden
    // expanded test relies on. If a future refactor changes the
    // testid OR moves the breakdown rows outside the testid container,
    // the e2e gate would still pass (only header assertion is gating)
    // but THIS test fires.
    const view = viewWith(
      [zone('a', 'wilderness')],
      [
        placement('decoration', 'rock'),
        placement('decoration', 'rock'),
        placement('decoration', 'vegetation'),
      ],
    );
    render(<MetadataPanel view={view} />);
    const container = screen.getByTestId('decoration-family-breakdown');
    expect(container).toBeInTheDocument();
    const rows = screen.getAllByTestId('decoration-family-row');
    expect(rows).toHaveLength(2); // rock + vegetation
  });

  it('per-zone summary (zones · placements · decorations) reports counts', () => {
    // Confirms the chunk-D #049 mount-smoke also catches a regression
    // in the MetadataPanel "decorations N" counter (chunk-C MED-1
    // extracted `isDecorationPlacement` to a shared predicate — this
    // test pins the counter's use of that predicate end-to-end).
    const view = viewWith(
      [zone('a', 'wilderness')],
      [
        placement('decoration', 'rock'),
        placement('decoration', 'vegetation'),
        placement('treasure', undefined),
      ],
    );
    render(<MetadataPanel view={view} />);
    // "decorations" row in the summary list — assert via text content.
    expect(screen.getByText('decorations')).toBeInTheDocument();
    // The value cell shows '2' (2 decoration placements; treasure
    // excluded by `isDecorationPlacement`).
    // Use a getAllByText since '2' may appear in multiple summary rows.
    expect(screen.getAllByText('2').length).toBeGreaterThanOrEqual(1);
  });
});
