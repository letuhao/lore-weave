// 24 H5 — the drag-to-write handler (onNodeDragStop). React Flow is mocked to a passthrough that
// CAPTURES the props PlanCanvas hands it, so a test invokes onNodeDragStop directly with a drop
// event and asserts the drop-target resolution + the move call BY EFFECT — the hit-tests themselves
// (leafLaneAtY / chapterAtPoint / bandAtY) are unit-tested in laneLayout.test.ts.
//
// The drop point is the CURSOR (screenToFlowPosition), not the dragged node's corner — so the tests
// drive `event.clientX/clientY`, and the mocked projection is the identity (client coords ARE flow
// coords here). The node's own `position` is deliberately parked somewhere irrelevant in most cases,
// which is exactly what proves the cursor is what's read.
import type { ReactNode } from 'react';
import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

type DropNode = { id: string; position: { x: number; y: number } };
type RFProps = {
  onNodeDragStop?: (e: unknown, node: DropNode) => void;
  onNodesChange?: (changes: unknown[]) => void;
  nodes?: { id: string; position: { x: number; y: number }; draggable?: boolean }[];
  nodesDraggable?: boolean;
  nodeDragThreshold?: number;
};
const captured: RFProps = {};

vi.mock('reactflow', async () => {
  const React = await import('react');
  return {
    __esModule: true,
    default: (props: RFProps & { children?: ReactNode }) => {
      Object.assign(captured, props);
      return <div data-testid="rf">{props.children}</div>;
    },
    Background: () => null,
    Controls: () => null,
    ReactFlowProvider: ({ children }: { children?: ReactNode }) => <>{children}</>,
    // The identity projection: a test's clientX/clientY ARE the flow coords it means.
    useReactFlow: () => ({
      setCenter: vi.fn(),
      screenToFlowPosition: (p: { x: number; y: number }) => p,
    }),
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
import type { LaneBand, LaneLayout, PlanCanvasProps } from '../../types';

// Two stacked LEAF arc lanes; chapter cards c1/c2 live in arc-a, scene s1 hangs under c1.
function makeLayout(): LaneLayout {
  const band = (id: string, y: number, isLeaf: boolean): LaneBand => ({
    id, kind: 'arc', depth: 1, title: id, y, height: 130, chapterY: y + 8, sceneY: y + 40,
    isLeaf, contiguous: true, segments: [], collapsed: false,
  });
  return {
    lanes: [band('arc-a', 0, true), band('arc-b', 150, true)],
    nodes: [
      { id: 'c1', shape: 'chapter', laneId: 'arc-a', x: 40, y: 8, width: 128, collapsed: false, storyOrder: 1 },
      { id: 'c2', shape: 'chapter', laneId: 'arc-a', x: 240, y: 8, width: 128, collapsed: false, storyOrder: 2 },
      { id: 's1', shape: 'scene', laneId: 'arc-a', x: 40, y: 40, width: 100, collapsed: false, storyOrder: 1 },
    ],
    unassigned: [], unassignedY: null, width: 400, height: 320,
  };
}

function makeProps(over: Partial<PlanCanvasProps> = {}): PlanCanvasProps {
  return {
    layout: makeLayout(), edges: [], overlay: null, conformance: null, unionState: {}, nodeContent: {},
    selectedId: null, onSelect: vi.fn(), onToggleArc: vi.fn(), onToggleChapter: vi.fn(), ...over,
  };
}

/** Release the drag of `id` with the cursor at (x, y). The node's own position is parked at the
 *  origin — if a hit-test ever reads it instead of the cursor, these tests go red. */
function dropAt(id: string, x: number, y: number) {
  captured.onNodeDragStop!({ clientX: x, clientY: y }, { id, position: { x: 0, y: 0 } });
}

describe('PlanCanvas — the controlled-drag wiring (React Flow v11 rules)', () => {
  beforeEach(() => { captured.onNodeDragStop = undefined; captured.onNodesChange = undefined; });

  it('wires onNodesChange — without it a controlled RF never moves a card under the cursor', () => {
    // The live bug: with a `nodes` prop and NO onNodesChange, RF's store is never updated by a drag
    // (hasDefaultNodes is false ⇒ triggerNodeChanges only forwards to the absent callback), so the
    // user drags and NOTHING moves, yet the drop still fires a write.
    render(<PlanCanvas {...makeProps({ onMoveChapter: vi.fn() })} />);
    expect(captured.onNodesChange).toBeTypeOf('function');
  });

  it('sets a non-zero drag threshold — RF defaults to 0, making every click a 0px drag', () => {
    render(<PlanCanvas {...makeProps({ onMoveChapter: vi.fn() })} />);
    expect(captured.nodeDragThreshold).toBeGreaterThan(0);
  });

  it('a move in flight (busy) freezes dragging — the lanes are about to be replaced', () => {
    render(<PlanCanvas {...makeProps({ onMoveChapter: vi.fn(), onMoveScene: vi.fn(), busy: true })} />);
    expect(captured.nodesDraggable).toBe(false);
  });

  it('falls back to the node position when the drop event carries no cursor coords', () => {
    const onMoveChapter = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveChapter })} />);
    // A synthetic/keyboard drag: no clientX/clientY ⇒ use the dragged node's own position.
    captured.onNodeDragStop!({}, { id: 'c1', position: { x: 40, y: 200 } });
    expect(onMoveChapter).toHaveBeenCalledWith('c1', 'arc-b');
  });
});

describe('PlanCanvas chapter drag → rebind arc (H5 Row-1)', () => {
  beforeEach(() => { captured.onNodeDragStop = undefined; });

  it('releasing over a DIFFERENT leaf lane rebinds the chapter to that arc', () => {
    const onMoveChapter = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveChapter })} />);
    dropAt('c1', 40, 200); // cursor inside arc-b's band (150..280)
    expect(onMoveChapter).toHaveBeenCalledWith('c1', 'arc-b');
  });

  it('releasing over its OWN lane is a no-op (no rebind)', () => {
    const onMoveChapter = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveChapter })} />);
    dropAt('c1', 90, 50); // still inside arc-a
    expect(onMoveChapter).not.toHaveBeenCalled();
  });

  it('releasing in no leaf lane (a gap) is a no-op', () => {
    const onMoveChapter = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveChapter })} />);
    dropAt('c1', 40, 140); // the inter-band gap
    expect(onMoveChapter).not.toHaveBeenCalled();
  });

  it('a tiny nudge inside the card cannot rebind — the CURSOR decides, not the card corner', () => {
    // The corner-probe bug: dragging a card up by ~13px put its top-left in the lane ABOVE while the
    // card still sat visually inside its own lane, silently rebinding the chapter.
    const onMoveChapter = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveChapter })} />);
    captured.onNodeDragStop!({ clientX: 45, clientY: 12 }, { id: 'c1', position: { x: 40, y: -5 } });
    expect(onMoveChapter).not.toHaveBeenCalled();
  });

  it('without an onMoveChapter handler the canvas is read-only (handler guards)', () => {
    render(<PlanCanvas {...makeProps()} />);
    expect(() => dropAt('c1', 40, 200)).not.toThrow();
  });
});

describe('PlanCanvas scene drag → re-parent (H5 Row-4)', () => {
  beforeEach(() => { captured.onNodeDragStop = undefined; });

  it('releasing over a chapter card re-parents the scene under that chapter', () => {
    const onMoveScene = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveScene })} />);
    dropAt('s1', 260, 30); // cursor inside c2's card box (x 240..368, y 8..92)
    expect(onMoveScene).toHaveBeenCalledWith('s1', 'c2');
  });

  it('the canvas resolves the TARGET only — it fires even for the scene\'s own chapter, and the controller no-ops', () => {
    const onMoveScene = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveScene })} />);
    // Over c1 (its own chapter): the canvas has no parent knowledge, so it still reports the target;
    // usePlanMoves.moveSceneToChapter is what skips the write.
    dropAt('s1', 60, 30);
    expect(onMoveScene).toHaveBeenCalledWith('s1', 'c1');
  });

  it('releasing on NO chapter card (a gutter / empty canvas) is a no-op', () => {
    const onMoveScene = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveScene })} />);
    dropAt('s1', 200, 30); // the gutter between c1 and c2
    expect(onMoveScene).not.toHaveBeenCalled();
    dropAt('s1', 60, 300); // far below any chapter row
    expect(onMoveScene).not.toHaveBeenCalled();
  });

  it('a 1px twitch on a scene card cannot re-parent it under a neighbour', () => {
    // The corner-probe bug at its worst: scene cards (pitch 96) spill under the NEXT chapter card
    // (pitch 144), and the chapter hit box began exactly 1px above the scene row — so nudging the
    // 3rd scene up by 1px re-parented it AND renumbered two chapters. The cursor starts on the scene
    // card, which is below every chapter box ⇒ no target ⇒ no write.
    const onMoveScene = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveScene })} />);
    captured.onNodeDragStop!({ clientX: 60, clientY: 100 }, { id: 's1', position: { x: 40, y: 39 } });
    expect(onMoveScene).not.toHaveBeenCalled();
  });

  it('a chapter drag never fires the scene handler, and vice versa (kind routing)', () => {
    const onMoveChapter = vi.fn();
    const onMoveScene = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveChapter, onMoveScene })} />);
    dropAt('c1', 40, 200); // chapter → arc-b lane
    expect(onMoveChapter).toHaveBeenCalledWith('c1', 'arc-b');
    expect(onMoveScene).not.toHaveBeenCalled();

    onMoveChapter.mockClear();
    dropAt('s1', 260, 30); // scene → c2
    expect(onMoveScene).toHaveBeenCalledWith('s1', 'c2');
    expect(onMoveChapter).not.toHaveBeenCalled();
  });

  it('without an onMoveScene handler a scene drop is a no-op (read-only scenes)', () => {
    render(<PlanCanvas {...makeProps({ onMoveChapter: vi.fn() })} />);
    expect(() => dropAt('s1', 260, 30)).not.toThrow();
  });
});

describe('PlanCanvas arc-band drag (H5 Row-2)', () => {
  beforeEach(() => { captured.onNodeDragStop = undefined; });

  it('releasing over ANOTHER band reports that band as the target (controller decides nest/sibling)', () => {
    const onMoveArc = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveArc })} />);
    // The band's RF node id carries the `lane:` prefix; arc-a released over arc-b's band (150..280).
    dropAt('lane:arc-a', 0, 200);
    expect(onMoveArc).toHaveBeenCalledWith('arc-a', 'arc-b');
  });

  it('releasing over ITSELF is a no-op', () => {
    const onMoveArc = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveArc })} />);
    dropAt('lane:arc-a', 0, 40); // still inside arc-a
    expect(onMoveArc).not.toHaveBeenCalled();
  });

  it('releasing off every band is a no-op', () => {
    const onMoveArc = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveArc })} />);
    dropAt('lane:arc-a', 0, 999);
    expect(onMoveArc).not.toHaveBeenCalled();
  });

  it('a band drag never fires the chapter/scene handlers (prefix routing)', () => {
    const onMoveArc = vi.fn();
    const onMoveChapter = vi.fn();
    const onMoveScene = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveArc, onMoveChapter, onMoveScene })} />);
    dropAt('lane:arc-a', 0, 200);
    expect(onMoveArc).toHaveBeenCalledWith('arc-a', 'arc-b');
    expect(onMoveChapter).not.toHaveBeenCalled();
    expect(onMoveScene).not.toHaveBeenCalled();
  });

  it('without an onMoveArc handler a band drop is a no-op (read-only bands)', () => {
    render(<PlanCanvas {...makeProps()} />);
    expect(() => dropAt('lane:arc-a', 0, 200)).not.toThrow();
  });
});
