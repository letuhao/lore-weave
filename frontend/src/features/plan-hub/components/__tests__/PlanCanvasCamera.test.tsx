// 24 H2.6 / OQ-5 — the camera controller: a focusTarget (nodeId + seq) pans the viewport to that
// node's CENTER via React Flow's setCenter. React Flow is mocked here (a passthrough ReactFlow that
// renders its children + a useReactFlow returning a setCenter spy) so the test asserts the pan BY
// EFFECT — that CameraController's effect fires on a seq change and computes the node's center from
// the layout — without the full RF viewport machinery. The real-RF node/edge mapping is covered by
// PlanCanvas.test.tsx; this file isolates the imperative camera seam.
import type { ReactNode } from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const setCenter = vi.fn();

vi.mock('reactflow', async () => {
  const React = await import('react');
  return {
    __esModule: true,
    default: ({ children }: { children?: ReactNode }) => <div data-testid="rf">{children}</div>,
    Background: () => null,
    Controls: () => null,
    ReactFlowProvider: ({ children }: { children?: ReactNode }) => <>{children}</>,
    useReactFlow: () => ({ setCenter, screenToFlowPosition: (p: unknown) => p }),
    useNodesState: (initial: unknown[]) => {
      const [nodes, setNodes] = React.useState(initial);
      return [nodes, setNodes, vi.fn()];
    },
    MarkerType: { ArrowClosed: 'arrowclosed' },
    Position: { Left: 'left', Right: 'right' },
    Handle: () => null,
  };
});

import { PlanCanvas } from '../PlanCanvas';
import type { LaneLayout, PlanCanvasProps } from '../../types';

function makeLayout(): LaneLayout {
  return {
    lanes: [
      {
        id: 'arc-1', kind: 'arc', depth: 0, title: 'Arc One', y: 0, height: 128,
        chapterY: 28, sceneY: 112, isLeaf: true, contiguous: true, segments: [], collapsed: false,
      },
    ],
    nodes: [
      { id: 'ch-1', shape: 'chapter', laneId: 'arc-1', x: 200, y: 28, width: 128, collapsed: false, storyOrder: 1 },
      { id: 'ch-2', shape: 'chapter', laneId: 'arc-1', x: 360, y: 28, width: 128, collapsed: false, storyOrder: 2 },
    ],
    unassigned: [], unassignedY: null,
    width: 520,
    height: 160,
  };
}

function makeProps(overrides: Partial<PlanCanvasProps> = {}): PlanCanvasProps {
  return {
    layout: makeLayout(),
    edges: [],
    overlay: null,
    conformance: null,
    unionState: {},
    nodeContent: {},
    selectedId: null,
    onSelect: vi.fn(),
    onToggleArc: vi.fn(),
    onToggleChapter: vi.fn(),
    ...overrides,
  };
}

describe('PlanCanvas camera (OQ-5)', () => {
  it('does not pan when there is no focus target', () => {
    setCenter.mockClear();
    render(<PlanCanvas {...makeProps({ focusTarget: null })} />);
    expect(setCenter).not.toHaveBeenCalled();
  });

  it('pans to the focused node centre (x+width/2) when the focus seq changes', () => {
    setCenter.mockClear();
    const props = makeProps();
    const { rerender } = render(<PlanCanvas {...props} focusTarget={null} />);
    expect(setCenter).not.toHaveBeenCalled();

    rerender(<PlanCanvas {...props} focusTarget={{ nodeId: 'ch-1', seq: 1 }} />);
    // ch-1 is at x=200,width=128,y=28 → centre x = 264, near-top y = 48.
    expect(setCenter).toHaveBeenCalledTimes(1);
    expect(setCenter).toHaveBeenLastCalledWith(264, 48, expect.objectContaining({ zoom: expect.any(Number) }));

    // Re-focusing the SAME node with a bumped seq pans again (a bare id wouldn't re-trigger).
    rerender(<PlanCanvas {...props} focusTarget={{ nodeId: 'ch-2', seq: 2 }} />);
    expect(setCenter).toHaveBeenCalledTimes(2);
    expect(setCenter).toHaveBeenLastCalledWith(424, 48, expect.objectContaining({ zoom: expect.any(Number) }));
  });

  it('is a no-op (no throw) when the focused node is not in the current layout', () => {
    setCenter.mockClear();
    const props = makeProps();
    const { rerender } = render(<PlanCanvas {...props} focusTarget={null} />);
    rerender(<PlanCanvas {...props} focusTarget={{ nodeId: 'not-loaded', seq: 1 }} />);
    expect(setCenter).not.toHaveBeenCalled();
  });
});

describe('PlanCanvas camera — OQ-5 auto-expand (the node appears a render LATER)', () => {
  it('pans as soon as the focused node APPEARS, not only on the frame it was requested', () => {
    // Focusing a nested arc first expands its ancestors, and that layout change lands on a later
    // render. The old camera checked once, found nothing, and gave up — so a rail click on any
    // arc under a collapsed one highlighted the row but never moved the viewport.
    setCenter.mockClear();
    const empty = { ...makeLayout(), nodes: [] };
    const props = makeProps({ layout: empty });
    const { rerender } = render(<PlanCanvas {...props} focusTarget={null} />);

    rerender(<PlanCanvas {...props} focusTarget={{ nodeId: 'ch-2', seq: 1 }} />);
    expect(setCenter).not.toHaveBeenCalled(); // not rendered yet — no throw, no pan

    // The expansion lands: the node now exists, with the SAME focus request outstanding.
    rerender(<PlanCanvas {...makeProps()} focusTarget={{ nodeId: 'ch-2', seq: 1 }} />);
    expect(setCenter).toHaveBeenCalledTimes(1);
    expect(setCenter).toHaveBeenLastCalledWith(424, 48, expect.objectContaining({ zoom: expect.any(Number) }));
  });

  it('pans only ONCE per focus request (an unrelated layout change must not re-pan)', () => {
    setCenter.mockClear();
    const props = makeProps();
    const { rerender } = render(<PlanCanvas {...props} focusTarget={{ nodeId: 'ch-1', seq: 1 }} />);
    expect(setCenter).toHaveBeenCalledTimes(1);

    // A new layout object (e.g. a window refetch) with the same focus request — the user is not
    // asking to be moved again, so the viewport must stay where they left it.
    rerender(<PlanCanvas {...makeProps()} focusTarget={{ nodeId: 'ch-1', seq: 1 }} />);
    expect(setCenter).toHaveBeenCalledTimes(1);
  });
});
