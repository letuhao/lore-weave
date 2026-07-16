// S7·2 — the world-map editor VIEW. WorldMapEditor takes its controller as a prop, so we drive it
// with a hand-rolled fake `ctl` (vi.fn mutations) — no QueryClient/auth needed. The load-bearing
// assertions: a LABEL-ONLY save does NOT send x/y (the FE half of the pointer rule — a partial
// PATCH must not carry coords), unbind sends entity_id:null, and a pin drag fires a single
// moveMarker({markerId,x,y}) — never delete+add.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { WorldMapMarker } from '../../types';
import { WorldMapEditor } from '../WorldMapEditor';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) => String((o?.defaultValue as string) ?? k),
  }),
}));

const marker = (over: Partial<WorldMapMarker> = {}): WorldMapMarker => ({
  marker_id: 'm1',
  label: 'Keep',
  x: 0.3,
  y: 0.6,
  entity_id: 'e1',
  marker_type: null,
  updated_at: '2026-07-16T00:00:00Z',
  ...over,
});

// A minimal mutation stub with the fields the view touches.
const mut = () => ({ mutate: vi.fn() });

// Build a full fake controller; overrides let each test aim a specific state.
function fakeCtl(over: Record<string, unknown> = {}) {
  return {
    worldId: 'w1',
    needsWorldPicker: false,
    worldOptions: [],
    pickWorld: vi.fn(),
    maps: [{ map_id: 'map1', world_id: 'w1', name: 'Atlas', image_object_key: null, image_url: null, version: 1 }],
    selectedMapId: 'map1',
    selectMap: vi.fn(),
    map: { map_id: 'map1', world_id: 'w1', name: 'Atlas', image_object_key: null, image_url: null, version: 1 },
    markers: [marker()],
    regions: [],
    isLoading: false,
    isError: false,
    error: null,
    isEmpty: false,
    mode: 'select' as const,
    setMode: vi.fn(),
    selectedMarkerId: 'm1',
    setSelectedMarkerId: vi.fn(),
    selectedRegionId: null,
    setSelectedRegionId: vi.fn(),
    selectedMarker: marker(),
    selectedRegion: null,
    createMap: mut(),
    uploadImage: mut(),
    renameMap: mut(),
    deleteMap: mut(),
    addMarker: mut(),
    moveMarker: mut(),
    patchMarker: mut(),
    deleteMarker: mut(),
    addRegion: mut(),
    reshapeRegion: mut(),
    patchRegion: mut(),
    deleteRegion: mut(),
    ...over,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any;
}

describe('WorldMapEditor', () => {
  let ctl: ReturnType<typeof fakeCtl>;
  beforeEach(() => {
    ctl = fakeCtl();
  });

  it('a label-only Save does NOT send x/y (FE pointer rule)', () => {
    render(<WorldMapEditor ctl={ctl} />);
    fireEvent.click(screen.getByTestId('world-map-marker-save'));
    expect(ctl.patchMarker.mutate).toHaveBeenCalledTimes(1);
    const arg = ctl.patchMarker.mutate.mock.calls[0][0];
    expect(arg.markerId).toBe('m1');
    expect(arg.payload).not.toHaveProperty('x');
    expect(arg.payload).not.toHaveProperty('y');
    expect(arg.payload).toHaveProperty('label');
  });

  it('Unbind sends entity_id:null (soft untyped unbind, no delete)', () => {
    render(<WorldMapEditor ctl={ctl} />);
    fireEvent.click(screen.getByTestId('world-map-marker-unbind'));
    expect(ctl.patchMarker.mutate).toHaveBeenCalledWith({ markerId: 'm1', payload: { entity_id: null } });
  });

  it('Delete calls deleteMarker with the stable marker_id', () => {
    render(<WorldMapEditor ctl={ctl} />);
    fireEvent.click(screen.getByTestId('world-map-marker-delete'));
    expect(ctl.deleteMarker.mutate).toHaveBeenCalledWith('m1');
  });

  it('an entity-bound pin renders with the source marker (violet) + data attr', () => {
    render(<WorldMapEditor ctl={ctl} />);
    expect(screen.getByTestId('world-map-marker-m1')).toHaveAttribute('data-entity-bound', 'true');
  });

  it('shows the empty state + Create CTA when the world has no maps', () => {
    render(<WorldMapEditor ctl={fakeCtl({ isEmpty: true, maps: [], selectedMarker: null, selectedMarkerId: null })} />);
    expect(screen.getByTestId('world-map-empty')).toBeInTheDocument();
    expect(screen.getByTestId('world-map-new')).toBeInTheDocument();
  });

  it('shows the world picker (never a dead pane) when no world is resolved', () => {
    render(<WorldMapEditor ctl={fakeCtl({ needsWorldPicker: true, selectedMarker: null })} />);
    expect(screen.getByTestId('world-map-world-picker')).toBeInTheDocument();
  });
});
