import { useEffect } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PowerViewOverlay } from '../PowerViewOverlay';

// The Power-view is a full-screen overlay hosting the 5 story-map views behind a
// switcher. Switching between views must NOT remount them (CSS hidden), so
// pan/zoom/selection survive; Esc + the close button exit. We mock each view to
// bump a mount counter — a remount (the bug) would bump it past 1.

const mounts = vi.hoisted(() => ({ graph: 0, timeline: 0, beats: 0, relmap: 0, worldmap: 0 }));
function mockView(name: keyof typeof mounts) {
  return function Mock() {
    useEffect(() => { mounts[name] += 1; }, []);
    return <div data-testid={`mock-${name}`}>{name}</div>;
  };
}
vi.mock('../SceneGraphCanvas', () => ({ SceneGraphCanvas: mockView('graph') }));
vi.mock('../TimelineView', () => ({ TimelineView: mockView('timeline') }));
vi.mock('../BeatSheetView', () => ({ BeatSheetView: mockView('beats') }));
vi.mock('../RelationshipMap', () => ({ RelationshipMap: mockView('relmap') }));
vi.mock('../WorldMap', () => ({ WorldMap: mockView('worldmap') }));

const work = { project_id: 'p1', book_id: 'b', settings: {} as Record<string, unknown> };

function renderOverlay(onClose = vi.fn(), onViewCast = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PowerViewOverlay work={work as never} bookId="b" chapterId="c" token="t" onClose={onClose} onViewCast={onViewCast} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onClose, onViewCast };
}
const wrapperOf = (name: string) => screen.getByTestId(`mock-${name}`).parentElement;

beforeEach(() => { mounts.graph = mounts.timeline = mounts.beats = mounts.relmap = mounts.worldmap = 0; });

describe('PowerViewOverlay (T5.5)', () => {
  it('mounts all five views; Scene Graph is the default visible one', () => {
    renderOverlay();
    for (const n of ['graph', 'timeline', 'beats', 'relmap', 'worldmap']) {
      expect(screen.getByTestId(`mock-${n}`)).toBeInTheDocument();
    }
    expect(wrapperOf('graph')).not.toHaveClass('hidden');
    expect(wrapperOf('timeline')).toHaveClass('hidden');
  });

  it('switching views toggles visibility WITHOUT remounting (state survives)', () => {
    renderOverlay();
    expect(mounts.timeline).toBe(1);
    fireEvent.click(screen.getByTestId('power-view-tab-timeline'));
    expect(wrapperOf('timeline')).not.toHaveClass('hidden');
    expect(wrapperOf('graph')).toHaveClass('hidden');
    fireEvent.click(screen.getByTestId('power-view-tab-graph'));
    // round-trip: timeline stayed mounted the whole time
    expect(mounts.timeline).toBe(1);
    expect(mounts.graph).toBe(1);
  });

  it('the close button exits', () => {
    const { onClose } = renderOverlay();
    fireEvent.click(screen.getByTestId('power-view-close'));
    expect(onClose).toHaveBeenCalled();
  });

  it('Escape exits', () => {
    const { onClose } = renderOverlay();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });
});
