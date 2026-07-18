import { render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { ReactFlowProvider, type NodeProps } from 'reactflow';

import type { ConformanceStatus, PlanOverlay } from '../../types';
import { ChapterNode } from '../ChapterNode';
import { NodeBadges } from '../NodeBadges';
import { orderNodeBadges, type NodeBadge, type PlanNodeData } from '../nodePresentation';

// React Flow's <Handle> reads its store via context; jsdom also lacks ResizeObserver. The RF
// testing shim (same as PlanCanvas.test) lets the real ChapterNode render its handles + badges.
beforeAll(() => {
  class ResizeObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  // @ts-expect-error jsdom shim
  global.ResizeObserver = ResizeObserverMock;
});

/** An overlay rich enough to exercise every badge kind on node `ch-1` / arc `arc-1`. */
function makeOverlay(): PlanOverlay {
  return {
    problems: {
      by_node: {
        'ch-1': {
          canon: 2,
          threads_open: 3,
          refs: [{ kind: 'canon', id: 'rule-9', line: 'Ha cannot fly before ch 40' }],
        },
        'arc-1': {
          canon: 1,
          threads_open: 4,
          refs: [{ kind: 'canon', id: 'rule-2', line: 'arc canon' }],
        },
      },
      refs_capped: false,
    },
    tension_rollup: [{ chapter_node_id: 'ch-1', story_order: 12, tension: 70 }],
    motif_chips: [
      // three chips ⇒ cap at 2 + one overflow; the first is stale (live > pinned)
      { node_ref: 'ch-1', motif_id: 'm1', title: 'The red thread', pinned_version: 3, live_version: 4 },
      { node_ref: 'ch-1', motif_id: 'm2', title: 'Iron rain', pinned_version: 1, live_version: 1 },
      { node_ref: 'ch-1', motif_id: 'm3', title: 'Third motif', pinned_version: 1, live_version: 1 },
    ],
    unplanned_chapters: [],
  };
}

function makeConformance(): ConformanceStatus {
  return {
    arcs: [{ structure_node_id: 'arc-1', dirty: true, dirty_reasons: ['stale'], stale_chapters: 2, computed_at: null, summary: null }],
    index: { stale_chapter_count: 2 },
  };
}

describe('orderNodeBadges (PH23 precedence — the single ordering home)', () => {
  it('orders a chapter canon > threads > tension > motif(≤2) > overflow, no drift on a non-arc', () => {
    const badges = orderNodeBadges({ overlay: makeOverlay(), nodeId: 'ch-1', showTension: true });
    expect(badges.map((b) => b.kind)).toEqual([
      'canon',
      'threads',
      'tension',
      'motif',
      'motif',
      'overflow',
    ]);
    // Cap held: 3 chips → 2 rendered + overflow of 1.
    const overflow = badges.find((b) => b.kind === 'overflow') as Extract<NodeBadge, { kind: 'overflow' }>;
    expect(overflow.count).toBe(1);
    // The stale chip is flagged (live 4 > pinned 3); the second is not.
    const motifs = badges.filter((b) => b.kind === 'motif') as Extract<NodeBadge, { kind: 'motif' }>[];
    expect(motifs.map((m) => m.stale)).toEqual([true, false]);
    // Canon carries the fired-rule ref for the deep-link.
    const canon = badges[0] as Extract<NodeBadge, { kind: 'canon' }>;
    expect(canon.ref?.id).toBe('rule-9');
  });

  it('places the conformance-drift badge for an arc AFTER canon and BEFORE thread debt', () => {
    const badges = orderNodeBadges({
      overlay: makeOverlay(),
      conformance: makeConformance(),
      nodeId: 'arc-1',
      isArc: true,
    });
    const kinds = badges.map((b) => b.kind);
    expect(kinds.indexOf('canon')).toBeLessThan(kinds.indexOf('dirty'));
    expect(kinds.indexOf('dirty')).toBeLessThan(kinds.indexOf('threads'));
    // No tension slot on an arc lane (not chapter-keyed).
    expect(kinds).not.toContain('tension');
  });

  it('emits nothing for an absent overlay (absent ≠ zero, no defaulted badges)', () => {
    expect(orderNodeBadges({ overlay: null, nodeId: 'ch-1', showTension: true })).toEqual([]);
    // A clean node (no problems, no chips) also yields an empty row.
    const clean: PlanOverlay = { problems: { by_node: {}, refs_capped: false }, tension_rollup: [], motif_chips: [], unplanned_chapters: [] };
    expect(orderNodeBadges({ overlay: clean, nodeId: 'ch-1', showTension: true })).toEqual([]);
  });
});

describe('NodeBadges (render)', () => {
  const badges = orderNodeBadges({ overlay: makeOverlay(), nodeId: 'ch-1', showTension: true });

  it('renders every badge kind: canon, threads, pacing bar, motif chips (stale marked), overflow', () => {
    render(<NodeBadges nodeId="ch-1" badges={badges} />);
    expect(screen.getByTestId('plan-badge-canon-ch-1')).toBeInTheDocument();
    expect(screen.getByTestId('plan-badge-threads-ch-1')).toBeInTheDocument();
    expect(screen.getByTestId('plan-pacing-ch-1')).toBeInTheDocument();
    expect(screen.getByTestId('plan-badge-motif-ch-1-m1')).toHaveTextContent('The red thread');
    expect(screen.getByTestId('plan-badge-motif-ch-1-m2')).toBeInTheDocument();
    // The third motif is not a chip — it collapses into the +N overflow.
    expect(screen.queryByTestId('plan-badge-motif-ch-1-m3')).not.toBeInTheDocument();
    // The overflow testid names its SOURCE: cast and motif can both overflow on one card, and
    // without the discriminator they collided on the React key and the tooltip lied about which.
    expect(screen.getByTestId('plan-badge-overflow-motif-ch-1')).toHaveTextContent('+1');
  });

  it('canon is a deep-link button ONLY when onOpenRef is wired; a plain chip otherwise', () => {
    const onOpenRef = vi.fn();
    const { rerender } = render(<NodeBadges nodeId="ch-1" badges={badges} onOpenRef={onOpenRef} />);
    const wired = screen.getByTestId('plan-badge-canon-ch-1');
    expect(wired.tagName).toBe('BUTTON');
    wired.click();
    expect(onOpenRef).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'rule-9', kind: 'canon' }),
      'ch-1', // the NODE rides along: the canon lens cannot filter by rule id, only by chapter
    );

    rerender(<NodeBadges nodeId="ch-1" badges={badges} />);
    // No handler ⇒ the count still shows, but it is NOT an interactive button (no dead affordance).
    expect(screen.getByTestId('plan-badge-canon-ch-1').tagName).not.toBe('BUTTON');
  });

  it('renders nothing when the badge list is empty', () => {
    const { container } = render(<NodeBadges nodeId="ch-1" badges={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('ChapterNode (node render)', () => {
  it('shows the badge row decorations on the rendered chapter card', () => {
    const data: PlanNodeData = {
      node: { id: 'ch-1', shape: 'chapter', laneId: 'arc-1', x: 0, y: 0, width: 140, collapsed: false, storyOrder: 12 },
      content: { title: 'The Summons', status: 'outline', kind: 'chapter', tension: 70, beatRole: null, chapterId: 'c1' },
      overlay: makeOverlay(),
      conformance: null,
      unionState: 'written',
      selected: false,
    };
    render(
      <ReactFlowProvider>
        <ChapterNode {...({ data } as NodeProps<PlanNodeData>)} />
      </ReactFlowProvider>,
    );
    expect(screen.getByTestId('plan-node-chapter-ch-1')).toHaveTextContent('The Summons');
    expect(screen.getByTestId('plan-node-badges-ch-1')).toBeInTheDocument();
    expect(screen.getByTestId('plan-badge-canon-ch-1')).toBeInTheDocument();
    expect(screen.getByTestId('plan-pacing-ch-1')).toBeInTheDocument();
    expect(screen.getByTestId('plan-badge-motif-ch-1-m1')).toBeInTheDocument();
  });
});
