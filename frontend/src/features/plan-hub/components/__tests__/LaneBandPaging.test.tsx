// 24 PH11 — the lane header's window-pagination affordance.
//
// The bug this covers: `loadMoreArc` / `arcHasMore` were EXPORTED by usePlanWindows and consumed by
// nobody. The children route pages at 100, so an arc with 340 chapters rendered 100 cards and the
// other 240 were unreachable — not merely un-scrolled but INVISIBLE and therefore un-draggable, and
// nothing on screen admitted they existed. A silent truncation is the one thing OUT-5 forbids.
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ReactFlowProvider } from 'reactflow';
import { LaneBandNode } from '../LaneBandLayer';
import { buildLaneNodes } from '../LaneBandLayer';
import type { LaneBand } from '../../types';

const band = (o: Partial<LaneBand> = {}): LaneBand => ({
  id: 'arc-1',
  kind: 'arc',
  depth: 1,
  title: 'Arc One',
  y: 0,
  height: 84,
  chapterY: 28,
  sceneY: 60,
  isLeaf: true,
  contiguous: true,
  segments: [],
  collapsed: false,
  ...o,
});

function renderBand(data: Record<string, unknown>) {
  return render(
    <ReactFlowProvider>
      {/* NodeProps shim — we only exercise the presentational body. */}
      <LaneBandNode
        id="lane:arc-1"
        type="lane-band"
        data={data as never}
        selected={false}
        zIndex={1}
        isConnectable={false}
        xPos={0}
        yPos={0}
        dragging={false}
      />
    </ReactFlowProvider>,
  );
}

describe('lane header pagination (PH11)', () => {
  it('shows loaded/total so a truncated window can never look complete', () => {
    renderBand({
      band: band(),
      onToggleArc: vi.fn(),
      pagination: { loaded: 100, total: 340, hasMore: true, loading: false },
      onLoadMore: vi.fn(),
    });
    expect(screen.getByTestId('plan-lane-count-arc-1').textContent).toBe('100/340');
  });

  it('the counter is HIDDEN when fully loaded — nothing is hidden, so it is just clutter', () => {
    // Changed 2026-07-18 (S4): a 3-user panel flagged the always-on "100/340" pill as telemetry
    // clutter on a writing surface. The count exists to warn "not everything is loaded" — so it now
    // shows ONLY when hasMore. Fully loaded (hasMore false) ⇒ nothing is hidden ⇒ no signal needed ⇒
    // no pill. The anti-silent-truncation guarantee is preserved: whenever chapters ARE hidden
    // (hasMore true) the count + "+ more" both appear (see the test above).
    renderBand({
      band: band(),
      onToggleArc: vi.fn(),
      pagination: { loaded: 100, total: 100, hasMore: false, loading: false },
      onLoadMore: vi.fn(),
    });
    expect(screen.queryByTestId('plan-lane-count-arc-1')).toBeNull(); // fully loaded → no clutter
    expect(screen.queryByTestId('plan-lane-more-arc-1')).toBeNull(); // nothing left to fetch
  });

  it('"+ more" pages the arc in — the affordance that was missing', () => {
    const onLoadMore = vi.fn();
    renderBand({
      band: band(),
      onToggleArc: vi.fn(),
      pagination: { loaded: 100, total: 340, hasMore: true, loading: false },
      onLoadMore,
    });
    fireEvent.click(screen.getByTestId('plan-lane-more-arc-1'));
    expect(onLoadMore).toHaveBeenCalledWith('arc-1');
  });

  it('disables "+ more" while a page is in flight (no double-fetch)', () => {
    renderBand({
      band: band(),
      onToggleArc: vi.fn(),
      pagination: { loaded: 100, total: 340, hasMore: true, loading: true },
      onLoadMore: vi.fn(),
    });
    expect((screen.getByTestId('plan-lane-more-arc-1') as HTMLButtonElement).disabled).toBe(true);
  });

  it('clicking "+ more" does NOT toggle the lane collapsed', () => {
    const onToggleArc = vi.fn();
    renderBand({
      band: band(),
      onToggleArc,
      pagination: { loaded: 100, total: 340, hasMore: true, loading: false },
      onLoadMore: vi.fn(),
    });
    fireEvent.click(screen.getByTestId('plan-lane-more-arc-1'));
    expect(onToggleArc).not.toHaveBeenCalled(); // stopPropagation holds
  });

  it('a COLLAPSED lane shows no counter — it is meant to have zero chapters loaded', () => {
    const nodes = buildLaneNodes(
      [band({ collapsed: true })],
      500,
      vi.fn(),
      false,
      { 'arc-1': { loaded: 0, total: 340, hasMore: false, loading: false } },
      vi.fn(),
    );
    expect(nodes[0].data.pagination).toBeUndefined(); // "0/340" on a rollup would be nonsense
  });

  it('an EXPANDED lane carries its pagination through to the band', () => {
    const pag = { loaded: 100, total: 340, hasMore: true, loading: false };
    const nodes = buildLaneNodes([band()], 500, vi.fn(), false, { 'arc-1': pag }, vi.fn());
    expect(nodes[0].data.pagination).toEqual(pag);
  });
});
