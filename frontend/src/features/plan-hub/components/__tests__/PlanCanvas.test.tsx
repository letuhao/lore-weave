import { render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import type { LaneLayout, PlanCanvasProps, SceneLinkEdge } from '../../types';
import { PlanCanvas } from '../PlanCanvas';

// React Flow needs a few browser APIs jsdom lacks (ResizeObserver, DOMMatrixReadOnly,
// SVGElement.getBBox, a non-zero-throwing getBoundingClientRect). This is React Flow's
// documented testing shim — with it the real RF renders our custom nodes/edges into the DOM,
// so the test exercises the actual mapping rather than a mocked-away canvas.
beforeAll(() => {
  // Fire the callback on observe so React Flow measures node/handle bounds — without a
  // measurement pass RF never resolves edge endpoints and drops every edge silently.
  class ResizeObserverMock {
    cb: (entries: { target: Element }[], obs: unknown) => void;
    constructor(cb: (entries: { target: Element }[], obs: unknown) => void) {
      this.cb = cb;
    }
    observe(el: Element) {
      this.cb([{ target: el }], this);
    }
    unobserve() {}
    disconnect() {}
  }
  // @ts-expect-error jsdom shim
  global.ResizeObserver = ResizeObserverMock;

  class DOMMatrixReadOnlyMock {
    m22 = 1;
    constructor(_t?: string) {}
  }
  // @ts-expect-error jsdom shim
  global.DOMMatrixReadOnly = DOMMatrixReadOnlyMock;

  // @ts-expect-error jsdom shim
  global.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 0, height: 0 });
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.getBoundingClientRect = () =>
    ({ x: 0, y: 0, width: 200, height: 100, top: 0, left: 0, bottom: 100, right: 200, toJSON: () => {} }) as DOMRect;
  // React Flow measures node size via offsetWidth/offsetHeight (not getBoundingClientRect);
  // jsdom lays nothing out and reports 0, so without this an edge's endpoints stay unmeasured
  // and RF renders the marker def but never the edge path.
  Object.defineProperties(HTMLElement.prototype, {
    offsetWidth: { configurable: true, get: () => 200 },
    offsetHeight: { configurable: true, get: () => 100 },
  });
});

/** A tiny fixed layout: one collapsed arc-rollup + two chapters on one lane, one edge. */
function makeLayout(): LaneLayout {
  return {
    lanes: [
      {
        id: 'arc-1',
        kind: 'arc',
        depth: 0,
        title: 'Arc One',
        y: 0,
        height: 128,
        chapterY: 28,
        sceneY: 112,
        isLeaf: true,
        contiguous: true,
        segments: [],
        collapsed: false,
      },
    ],
    nodes: [
      {
        id: 'roll-1',
        shape: 'arc-rollup',
        laneId: 'arc-1',
        x: 24,
        y: 28,
        width: 128,
        collapsed: true,
        rollupCount: 2,
        storyOrder: 1,
      },
      {
        id: 'ch-1',
        shape: 'chapter',
        laneId: 'arc-1',
        x: 200,
        y: 28,
        width: 128,
        collapsed: false,
        storyOrder: 2,
      },
      {
        id: 'ch-2',
        shape: 'chapter',
        laneId: 'arc-1',
        x: 360,
        y: 28,
        width: 128,
        collapsed: false,
        storyOrder: 3,
      },
    ],
    unassigned: [], unassignedY: null,
    width: 520,
    height: 160,
  };
}

function makeProps(overrides: Partial<PlanCanvasProps> = {}): PlanCanvasProps {
  const edges: SceneLinkEdge[] = [
    {
      id: 'edge-1',
      from_node_id: 'ch-1',
      to_node_id: 'ch-2',
      kind: 'setup_payoff',
      label: null,
      // PH13 endpoint ancestry. Both ends are rendered here, so resolution short-circuits on the
      // nodes themselves — but the fixture carries the real wire shape rather than a stale subset.
      from_chapter_node_id: null,
      to_chapter_node_id: null,
      from_arc_id: 'arc-1',
      to_arc_id: 'arc-1',
    },
  ];
  return {
    layout: makeLayout(),
    edges,
    overlay: null,
    conformance: null,
    unionState: { 'ch-1': 'written', 'ch-2': 'planned-only' },
    nodeContent: {},
    selectedId: null,
    onSelect: vi.fn(),
    onToggleArc: vi.fn(),
    onToggleChapter: vi.fn(),
    ...overrides,
  };
}

describe('PlanCanvas', () => {
  it('renders the lane band, chapter/arc-rollup nodes and the scene-link edge', () => {
    const { container } = render(<PlanCanvas {...makeProps()} />);

    // Lane band (background swimlane) with its title.
    expect(screen.getByTestId('plan-lane-arc-1')).toBeInTheDocument();
    expect(screen.getByText('Arc One')).toBeInTheDocument();

    // The two chapter cards + the collapsed arc-rollup card.
    expect(screen.getByTestId('plan-node-chapter-ch-1')).toBeInTheDocument();
    expect(screen.getByTestId('plan-node-chapter-ch-2')).toBeInTheDocument();
    expect(screen.getByTestId('plan-node-arc-rollup-roll-1')).toBeInTheDocument();
    // rollupCount → summary label ("2 chapters"), rendered from the shell, not child nodes.
    expect(screen.getByTestId('plan-node-arc-rollup-roll-1').textContent).toContain('2 chapters');

    // The edge is mapped to a React Flow edge in the DOM.
    expect(container.querySelectorAll('.react-flow__edge').length).toBe(1);
    expect(screen.getByTestId('rf__edge-edge-1')).toBeInTheDocument();

    // Three content nodes + one band = four React Flow nodes.
    expect(container.querySelectorAll('.react-flow__node').length).toBe(4);
  });

  it('selecting a chapter node calls onSelect with its id; a lane click does not', () => {
    const onSelect = vi.fn();
    render(<PlanCanvas {...makeProps({ onSelect })} />);

    screen.getByTestId('plan-node-chapter-ch-1').click();
    expect(onSelect).toHaveBeenCalledWith('ch-1');

    onSelect.mockClear();
    // The band body click is NOT a selection (its header owns the toggle instead).
    screen.getByTestId('plan-lane-arc-1').click();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('the rollup expand affordance calls onToggleArc, the lane toggle too', () => {
    const onToggleArc = vi.fn();
    render(<PlanCanvas {...makeProps({ onToggleArc })} />);

    screen.getByTestId('plan-node-arc-rollup-toggle-roll-1').click();
    expect(onToggleArc).toHaveBeenCalledWith('roll-1');

    screen.getByTestId('plan-lane-toggle-arc-1').click();
    expect(onToggleArc).toHaveBeenCalledWith('arc-1');
  });

  it('renders a real chapter title from nodeContent, falling back to a story-order label', () => {
    render(
      <PlanCanvas
        {...makeProps({
          nodeContent: {
            'ch-1': { title: 'The Summons', status: 'outline', kind: 'chapter', tension: null, beatRole: null, chapterId: 'c1' },
          },
        })}
      />,
    );
    // ch-1 has content ⇒ its real title; ch-2 has none ⇒ the story-order placeholder.
    expect(screen.getByTestId('plan-node-chapter-ch-1').textContent).toContain('The Summons');
    expect(screen.getByTestId('plan-node-chapter-ch-2').textContent).toContain('Ch 3');
  });

  it('marks the active (you-are-here) node with data-here and leaves others unmarked', () => {
    render(<PlanCanvas {...makeProps({ activeNodeId: 'ch-1' })} />);
    // ch-1 is the editor's active chapter ⇒ data-here="true"; ch-2 is not ⇒ attribute absent.
    expect(screen.getByTestId('plan-node-chapter-ch-1').getAttribute('data-here')).toBe('true');
    expect(screen.getByTestId('plan-node-chapter-ch-2').getAttribute('data-here')).toBeNull();
  });

  it('a chapter branch toggle calls onToggleChapter, not onSelect', () => {
    const onToggleChapter = vi.fn();
    const onSelect = vi.fn();
    render(<PlanCanvas {...makeProps({ onToggleChapter, onSelect })} />);

    screen.getByTestId('plan-node-chapter-toggle-ch-1').click();
    expect(onToggleChapter).toHaveBeenCalledWith('ch-1');
    // stopPropagation keeps the toggle from bubbling into a node selection.
    expect(onSelect).not.toHaveBeenCalled();
  });

  // PH18 — the canon badge's deep-link, end to end through the REAL chain:
  // PlanCanvas → node `data` → the node card → NodeBadges.
  //
  // Every link in that chain already existed and every one honoured `onOpenRef`. But PlanCanvas
  // never put it into `data`, so the chain resolved to `undefined` and the badge was permanently a
  // plain chip. Each piece unit-tested green in isolation; nobody tested the JOIN. This is that test.
  it('threads onOpenRef into the node data so the canon badge is a live deep-link', () => {
    const onOpenRef = vi.fn();
    const overlay = {
      problems: {
        by_node: {
          'ch-1': {
            canon: 1,
            threads_open: 0,
            refs: [{ kind: 'canon' as const, id: 'rule-9', line: 'Ha cannot fly before ch 40' }],
          },
        },
        refs_capped: false,
      },
      tension_rollup: [],
      motif_chips: [],
      unplanned_chapters: [],
    };
    render(<PlanCanvas {...makeProps({ overlay, onOpenRef })} />);

    const badge = screen.getByTestId('plan-badge-canon-ch-1');
    expect(badge.tagName).toBe('BUTTON'); // a chip here would mean the seam is dead again
    badge.click();
    expect(onOpenRef).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'canon', id: 'rule-9' }),
      'ch-1',
    );
  });

  // PH13 — an edge into a COLLAPSED arc must render as a stub, never vanish.
  //
  // Before this, the canvas handed React Flow `target: 's-hidden'` — a node not in the list — and RF
  // dropped the edge silently: a setup with no payoff, and nothing saying a payoff existed.
  it('stubs an edge into a collapsed arc instead of dropping it', () => {
    const edges: SceneLinkEdge[] = [
      {
        id: 'edge-stub',
        from_node_id: 'ch-1',
        to_node_id: 's-hidden', // NOT rendered — it lives inside the collapsed arc
        kind: 'setup_payoff',
        label: null,
        from_chapter_node_id: null,
        to_chapter_node_id: 'ch-hidden', // also not rendered
        from_arc_id: 'arc-1',
        to_arc_id: 'roll-1', // the collapsed arc's rollup IS on screen
      },
    ];
    const { container } = render(<PlanCanvas {...makeProps({ edges })} />);
    // The edge still exists, re-anchored onto the rollup card.
    expect(container.querySelectorAll('.react-flow__edge').length).toBe(1);
    expect(screen.getByTestId('rf__edge-edge-stub')).toBeInTheDocument();
  });

  it('badges edges folded INSIDE a collapsed arc rather than losing them', () => {
    const edges: SceneLinkEdge[] = [
      {
        id: 'edge-inside',
        from_node_id: 's-a',
        to_node_id: 's-b', // both ends inside the SAME collapsed arc
        kind: 'setup_payoff',
        label: null,
        from_chapter_node_id: null,
        to_chapter_node_id: null,
        from_arc_id: 'roll-1',
        to_arc_id: 'roll-1',
      },
    ];
    const { container } = render(<PlanCanvas {...makeProps({ edges })} />);
    // A self-loop onto one card would be noise, so no edge is drawn…
    expect(container.querySelectorAll('.react-flow__edge').length).toBe(0);
    // …but the rollup ACCOUNTS for it. Silently dropping it is the bug PH13 names.
    expect(screen.getByTestId('plan-node-edges-roll-1').textContent).toContain('1');
  });

  it('without onOpenRef the canon badge stays a plain chip (the designed fallback)', () => {
    const overlay = {
      problems: {
        by_node: {
          'ch-1': { canon: 1, threads_open: 0, refs: [] },
        },
        refs_capped: false,
      },
      tension_rollup: [],
      motif_chips: [],
      unplanned_chapters: [],
    };
    render(<PlanCanvas {...makeProps({ overlay })} />);
    expect(screen.getByTestId('plan-badge-canon-ch-1').tagName).not.toBe('BUTTON');
  });
});
