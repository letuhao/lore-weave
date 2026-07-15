import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PropsWithChildren } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { WorldMapsSection } from '../WorldMapsSection';

// W10 maps canvas — mocks the data hook (fetch lives there) and proves: empty state,
// the picker when >1 map, and that markers/regions render from NORMALIZED coords.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

const { hook } = vi.hoisted(() => ({ hook: vi.fn() }));
vi.mock('../../hooks/useWorldMaps', () => ({ useWorldMaps: () => hook() }));

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}
const renderView = () => render(<WorldMapsSection worldId="w1" />, { wrapper: Wrapper });

describe('WorldMapsSection', () => {
  it('shows the empty state when the world has no maps', () => {
    hook.mockReturnValue({ maps: [], selectedId: null, select: vi.fn(), detail: null, isLoading: false });
    renderView();
    expect(screen.getByTestId('world-maps-empty')).toBeInTheDocument();
  });

  it('renders nothing while loading (no flash of empty)', () => {
    hook.mockReturnValue({ maps: [], selectedId: null, select: vi.fn(), detail: null, isLoading: true });
    const { container } = renderView();
    expect(container).toBeEmptyDOMElement();
  });

  it('renders markers + regions from normalized coordinates', () => {
    hook.mockReturnValue({
      maps: [{ map_id: 'm1', world_id: 'w1', name: 'Atlas', image_object_key: 'k', image_url: 'http://img/base.png' }],
      selectedId: 'm1',
      select: vi.fn(),
      detail: {
        map: { map_id: 'm1', world_id: 'w1', name: 'Atlas', image_object_key: 'k', image_url: 'http://img/base.png' },
        markers: [{ marker_id: 'mk1', label: 'Ironhold', x: 0.25, y: 0.5, entity_id: null, marker_type: 'city' }],
        regions: [{ region_id: 'rg1', name: 'The North', polygon: [[0, 0], [1, 0], [0.5, 1]], entity_id: null }],
      },
      isLoading: false,
    });
    renderView();
    // marker pin positioned by normalized coords → left 25%, top 50%
    const pin = screen.getByTestId('world-map-marker-mk1');
    expect(pin).toHaveStyle({ left: '25%', top: '50%' });
    expect(pin).toHaveAttribute('title', 'Ironhold');
    // region polygon points scaled into the 0..100 viewBox
    const svg = screen.getByTestId('world-map-regions');
    const poly = svg.querySelector('polygon');
    expect(poly).toHaveAttribute('points', '0,0 100,0 50,100');
    // the base image renders
    expect(screen.getByRole('img')).toHaveAttribute('src', 'http://img/base.png');
  });

  it('shows a picker when there is more than one map and switches on click', () => {
    const select = vi.fn();
    hook.mockReturnValue({
      maps: [
        { map_id: 'm1', world_id: 'w1', name: 'Atlas', image_object_key: null, image_url: null },
        { map_id: 'm2', world_id: 'w1', name: 'The Underdark', image_object_key: null, image_url: null },
      ],
      selectedId: 'm1',
      select,
      detail: { map: { map_id: 'm1', world_id: 'w1', name: 'Atlas', image_object_key: null, image_url: null }, markers: [], regions: [] },
      isLoading: false,
    });
    renderView();
    fireEvent.click(screen.getByTestId('world-map-tab-m2'));
    expect(select).toHaveBeenCalledWith('m2');
  });
});
