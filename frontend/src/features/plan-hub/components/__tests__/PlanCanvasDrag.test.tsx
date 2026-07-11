// 24 H5 Row-1 — the drag-to-rebind handler (onNodeDragStop). React Flow is mocked to a passthrough
// that CAPTURES the props PlanCanvas hands it, so the test invokes onNodeDragStop directly with a
// dropped-node payload and asserts the drop-target resolution + the onMoveChapter call BY EFFECT —
// the drag hit-test itself (leafLaneAtY) is unit-tested in laneLayout.test.ts.
import type { ReactNode } from 'react';
import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

type RFProps = { onNodeDragStop?: (e: unknown, node: { id: string; position: { x: number; y: number } }) => void };
const captured: RFProps = {};

vi.mock('reactflow', () => ({
  __esModule: true,
  default: (props: RFProps & { children?: ReactNode }) => {
    captured.onNodeDragStop = props.onNodeDragStop;
    return <div data-testid="rf">{props.children}</div>;
  },
  Background: () => null,
  Controls: () => null,
  ReactFlowProvider: ({ children }: { children?: ReactNode }) => <>{children}</>,
  useReactFlow: () => ({ setCenter: vi.fn() }),
  MarkerType: { ArrowClosed: 'arrowclosed' },
  Position: { Left: 'left', Right: 'right' },
  Handle: () => null,
}));

import { PlanCanvas } from '../PlanCanvas';
import type { LaneBand, LaneLayout, PlanCanvasProps } from '../../types';

// Two stacked LEAF arc lanes; a chapter card c1 lives in arc-a.
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
    unplanned: [], width: 400, height: 320,
  };
}

function makeProps(over: Partial<PlanCanvasProps> = {}): PlanCanvasProps {
  return {
    layout: makeLayout(), edges: [], overlay: null, conformance: null, unionState: {}, nodeContent: {},
    selectedId: null, onSelect: vi.fn(), onToggleArc: vi.fn(), onToggleChapter: vi.fn(), ...over,
  };
}

describe('PlanCanvas drag-to-rebind (H5 Row-1)', () => {
  beforeEach(() => { captured.onNodeDragStop = undefined; });

  it('dropping a chapter into a DIFFERENT leaf lane rebinds it to that arc', () => {
    const onMoveChapter = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveChapter })} />);
    // c1 (from arc-a) dropped at y=200 → inside arc-b's band.
    captured.onNodeDragStop!({}, { id: 'c1', position: { x: 40, y: 200 } });
    expect(onMoveChapter).toHaveBeenCalledWith('c1', 'arc-b');
  });

  it('dropping a chapter back into its OWN lane is a no-op (no rebind)', () => {
    const onMoveChapter = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveChapter })} />);
    captured.onNodeDragStop!({}, { id: 'c1', position: { x: 90, y: 50 } }); // still inside arc-a
    expect(onMoveChapter).not.toHaveBeenCalled();
  });

  it('a drop landing in no leaf lane (a gap) is a no-op', () => {
    const onMoveChapter = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveChapter })} />);
    captured.onNodeDragStop!({}, { id: 'c1', position: { x: 40, y: 140 } }); // arc-a bottom edge / gap
    expect(onMoveChapter).not.toHaveBeenCalled();
  });

  it('dragging a NON-chapter node never rebinds (only chapters carry an arc)', () => {
    const onMoveChapter = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveChapter })} />);
    captured.onNodeDragStop!({}, { id: 's1', position: { x: 40, y: 200 } });
    expect(onMoveChapter).not.toHaveBeenCalled();
  });

  it('without an onMoveChapter handler the canvas is read-only (handler guards)', () => {
    render(<PlanCanvas {...makeProps()} />);
    // onNodeDragStop is still wired but no-ops without the callback; invoking it must not throw.
    expect(() => captured.onNodeDragStop!({}, { id: 'c1', position: { x: 40, y: 200 } })).not.toThrow();
  });
});

describe('PlanCanvas scene drag-to-reparent (H5 Row-4)', () => {
  beforeEach(() => { captured.onNodeDragStop = undefined; });

  it('dropping a scene onto a chapter card re-parents it under that chapter', () => {
    const onMoveScene = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveScene })} />);
    // s1 dropped over c2's card box (x 240..368, y 8..8+laneHeight).
    captured.onNodeDragStop!({}, { id: 's1', position: { x: 260, y: 30 } });
    expect(onMoveScene).toHaveBeenCalledWith('s1', 'c2');
  });

  it('the canvas resolves the TARGET only — it fires even for the scene\'s own chapter, and the controller no-ops', () => {
    const onMoveScene = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveScene })} />);
    // Dropped back over c1 (its own chapter): the canvas has no parent knowledge, so it still
    // reports the target; usePlanHub.moveSceneToChapter is what skips the write.
    captured.onNodeDragStop!({}, { id: 's1', position: { x: 60, y: 30 } });
    expect(onMoveScene).toHaveBeenCalledWith('s1', 'c1');
  });

  it('a scene dropped on NO chapter card (a gutter / empty canvas) is a no-op', () => {
    const onMoveScene = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveScene })} />);
    captured.onNodeDragStop!({}, { id: 's1', position: { x: 200, y: 30 } }); // gutter between c1 and c2
    expect(onMoveScene).not.toHaveBeenCalled();
    captured.onNodeDragStop!({}, { id: 's1', position: { x: 60, y: 300 } }); // far below any chapter row
    expect(onMoveScene).not.toHaveBeenCalled();
  });

  it('a chapter drag never fires the scene handler, and vice versa (kind routing)', () => {
    const onMoveChapter = vi.fn();
    const onMoveScene = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveChapter, onMoveScene })} />);
    captured.onNodeDragStop!({}, { id: 'c1', position: { x: 40, y: 200 } }); // chapter → arc-b lane
    expect(onMoveChapter).toHaveBeenCalledWith('c1', 'arc-b');
    expect(onMoveScene).not.toHaveBeenCalled();

    onMoveChapter.mockClear();
    captured.onNodeDragStop!({}, { id: 's1', position: { x: 260, y: 30 } }); // scene → c2
    expect(onMoveScene).toHaveBeenCalledWith('s1', 'c2');
    expect(onMoveChapter).not.toHaveBeenCalled();
  });

  it('without an onMoveScene handler a scene drop is a no-op (read-only scenes)', () => {
    const onMoveChapter = vi.fn();
    render(<PlanCanvas {...makeProps({ onMoveChapter })} />);
    expect(() => captured.onNodeDragStop!({}, { id: 's1', position: { x: 260, y: 30 } })).not.toThrow();
  });
});
