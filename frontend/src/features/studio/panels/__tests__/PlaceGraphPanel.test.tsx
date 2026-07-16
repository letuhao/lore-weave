/**
 * S7-3 · Place Graph — the studio dock host for the operable World/KG place graph.
 * The wrapper is thin: it resolves the book's composition Work (from the {status,work,candidates}
 * envelope), mounts the EXISTING <WorldMap> leaf (DOCK-2, no fork), and owns the two states the leaf
 * assumes away — no Work (never mount the leaf null → crash on work.settings.world_map) and the
 * bus-fed activeChapterId (for the chapter-scoped backdrop bucket). Deep-links onViewCast → cast,
 * "Author other kinds" → kg-entities.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const openPanel = vi.fn();
let busChapterId: string | undefined;
vi.mock('../../host/StudioHostProvider', () => ({
  useStudioHost: () => ({ bookId: 'book-1', openPanel }),
  // The panel selects the activeChapterId slice; feed the current test value through the selector.
  useStudioBusSelector: (sel: (s: { activeChapterId?: string }) => unknown) =>
    sel({ activeChapterId: busChapterId }),
}));
vi.mock('../useStudioPanel', () => ({ useStudioPanel: () => 'Place Graph' }));

// useWorkResolution resolves to the ENVELOPE `{status, work, candidates}` — NOT a bare Work. The panel
// must dig out `.work` (the leaf reads work.settings); returning a bare object here would hide the shape
// mismatch (the WhatIfCanvasPanel live-smoke lesson). So the mock returns the real envelope shape.
let resolution: unknown = null;
let workLoading = false;
vi.mock('@/features/composition/hooks/useWork', () => ({
  useWorkResolution: () => ({ data: resolution, isLoading: workLoading }),
}));

// Capture the props the leaf is mounted with, so we can assert chapterId wiring + onViewCast deep-link
// without dragging in the whole GraphCanvas/knowledge stack.
const leafProps = vi.fn();
vi.mock('@/features/composition/components/WorldMap', () => ({
  WorldMap: (p: { chapterId: string; bookId: string; onViewCast: (n: string) => void }) => {
    leafProps(p);
    return (
      <div data-testid="worldmap-leaf" data-chapter={p.chapterId} data-book={p.bookId}>
        <button data-testid="leaf-fire-viewcast" onClick={() => p.onViewCast('Hollow Keep')}>view</button>
      </div>
    );
  },
}));

import { PlaceGraphPanel } from '../PlaceGraphPanel';

const props = { api: {} } as never;

beforeEach(() => {
  openPanel.mockReset();
  leafProps.mockReset();
  resolution = null;
  workLoading = false;
  busChapterId = undefined;
});

describe('PlaceGraphPanel (S7-3)', () => {
  it('shows the no-Work state (with an Open Compose CTA) and NEVER mounts the leaf with a null Work', () => {
    resolution = { status: 'not_found', work: null };
    render(<PlaceGraphPanel {...props} />);
    expect(screen.getByTestId('studio-place-graph-panel')).toBeInTheDocument();
    expect(screen.getByTestId('place-graph-nowork')).toBeInTheDocument();
    expect(screen.queryByTestId('worldmap-leaf')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('place-graph-setup-cowriter'));
    expect(openPanel).toHaveBeenCalledWith('compose');
  });

  it('shows a loading state while the Work resolves (and does not mount the leaf)', () => {
    workLoading = true;
    resolution = undefined;
    render(<PlaceGraphPanel {...props} />);
    expect(screen.getByTestId('studio-place-graph-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('worldmap-leaf')).not.toBeInTheDocument();
  });

  it('mounts the WorldMap leaf once a Work exists, passing the bus activeChapterId through', () => {
    resolution = { status: 'found', work: { id: 'w1', project_id: 'p1', settings: {} } };
    busChapterId = 'ch-7';
    render(<PlaceGraphPanel {...props} />);
    const leaf = screen.getByTestId('worldmap-leaf');
    expect(leaf).toHaveAttribute('data-chapter', 'ch-7');
    expect(leaf).toHaveAttribute('data-book', 'book-1');
  });

  it('passes empty chapterId (not undefined) to the leaf when no chapter is active — the §4.3 guard fires', () => {
    resolution = { status: 'found', work: { id: 'w1', project_id: 'p1', settings: {} } };
    busChapterId = undefined;
    render(<PlaceGraphPanel {...props} />);
    expect(leafProps).toHaveBeenCalledWith(expect.objectContaining({ chapterId: '' }));
  });

  it('handles the candidates envelope by mounting the first candidate Work', () => {
    resolution = { status: 'candidates', work: null, candidates: [{ id: 'c1', project_id: 'p2', settings: {} }] };
    render(<PlaceGraphPanel {...props} />);
    expect(screen.getByTestId('worldmap-leaf')).toBeInTheDocument();
  });

  it('onViewCast deep-links to the cast panel with a search prefill (OQ-1 params.search)', () => {
    resolution = { status: 'found', work: { id: 'w1', project_id: 'p1', settings: {} } };
    render(<PlaceGraphPanel {...props} />);
    fireEvent.click(screen.getByTestId('leaf-fire-viewcast'));
    expect(openPanel).toHaveBeenCalledWith('cast', { params: { search: 'Hollow Keep' } });
  });

  it('"Author other kinds" deep-links to the existing kg-entities panel (OQ-2)', () => {
    resolution = { status: 'found', work: { id: 'w1', project_id: 'p1', settings: {} } };
    render(<PlaceGraphPanel {...props} />);
    fireEvent.click(screen.getByTestId('place-graph-author-other'));
    expect(openPanel).toHaveBeenCalledWith('kg-entities');
  });
});
