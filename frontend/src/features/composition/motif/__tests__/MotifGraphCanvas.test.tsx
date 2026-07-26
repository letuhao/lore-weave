// Wave-4 (D-MOTIF-GRAPH-CANVAS) — the reactflow canvas wiring. RF is mocked to a passthrough that
// CAPTURES the props, so a test invokes onNodeDragStop directly and asserts the persist call BY
// EFFECT (the debounced write + OCC live in useMotifGraph, mocked here to a spy). Mirrors
// PlanCanvasDrag.test.tsx (the controlled-drag v11 rules: onNodesChange wired, threshold > 0).
import type { ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

type DropNode = { id: string; position: { x: number; y: number } };
type RFProps = {
  onNodeDragStop?: (e: unknown, n: DropNode) => void;
  onNodesChange?: (c: unknown[]) => void;
  nodes?: { id: string; position: { x: number; y: number } }[];
  edges?: { id: string; source: string; target: string }[];
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
    useNodesState: (init: unknown[]) => { const [n, s] = React.useState(init); return [n, s, vi.fn()]; },
    useEdgesState: (init: unknown[]) => { const [e, s] = React.useState(init); return [e, s, vi.fn()]; },
  };
});

const savePosition = vi.fn();
let graphReturn: Record<string, unknown>;
vi.mock('../hooks/useMotifGraph', () => ({ useMotifGraph: () => graphReturn }));

import { MotifGraphCanvas } from '../components/MotifGraphCanvas';

const DATA = {
  nodes: [
    { id: 'm1', code: 'a', name: 'Alpha', kind: 'scheme', mine: true, book_shared: false },
    { id: 'm2', code: 'b', name: 'Beta', kind: 'sequence', mine: false, book_shared: true },
  ],
  edges: [{ id: 'e1', from_motif_id: 'm1', to_motif_id: 'm2', kind: 'precedes', ord: 1 }],
  layout: { positions: { m1: { x: 100, y: 50 } }, version: 3 },
  truncated: false, node_cap: 300,
};

function base(over: Record<string, unknown> = {}) {
  return { data: DATA, isLoading: false, isError: false, refetch: vi.fn(), savePosition, ...over };
}

describe('MotifGraphCanvas — reactflow controlled-drag + persist wiring', () => {
  beforeEach(() => { captured.onNodeDragStop = undefined; captured.onNodesChange = undefined; savePosition.mockClear(); });

  it('wires onNodesChange (a controlled RF needs it to move a node under the cursor)', () => {
    graphReturn = base();
    render(<MotifGraphCanvas bookId="b" token="t" />);
    expect(captured.onNodesChange).toBeTypeOf('function');
  });

  it('sets a non-zero drag threshold (RF defaults to 0 → every click a 0px drag)', () => {
    graphReturn = base();
    render(<MotifGraphCanvas bookId="b" token="t" />);
    expect(captured.nodeDragThreshold).toBeGreaterThan(0);
  });

  it('builds nodes (stored position wins, else auto-layout) + edges from the graph', () => {
    graphReturn = base();
    render(<MotifGraphCanvas bookId="b" token="t" />);
    const m1 = captured.nodes!.find((n) => n.id === 'm1')!;
    expect(m1.position).toEqual({ x: 100, y: 50 });        // stored layout wins
    const m2 = captured.nodes!.find((n) => n.id === 'm2')!;
    expect(m2.position.x).toBeGreaterThan(0);               // auto-layout slot (no stored pos)
    expect(captured.edges).toHaveLength(1);
    expect(captured.edges![0]).toMatchObject({ source: 'm1', target: 'm2' });
  });

  it('drag-stop persists the DROPPED position (node.position) for that motif', () => {
    graphReturn = base();
    render(<MotifGraphCanvas bookId="b" token="t" />);
    captured.onNodeDragStop!({}, { id: 'm2', position: { x: 321, y: 654 } });
    expect(savePosition).toHaveBeenCalledWith('m2', 321, 654);
  });

  it('read-only freezes the drag persist but not the render', () => {
    graphReturn = base();
    render(<MotifGraphCanvas bookId="b" token="t" readOnly />);
    expect(captured.nodesDraggable).toBe(false);
    captured.onNodeDragStop!({}, { id: 'm1', position: { x: 9, y: 9 } });
    expect(savePosition).not.toHaveBeenCalled();
  });

  it('renders honest empty / loading / error states', () => {
    graphReturn = base({ data: { ...DATA, nodes: [] } });
    const { rerender } = render(<MotifGraphCanvas bookId="b" token="t" />);
    expect(screen.getByTestId('motif-graph-empty')).toBeInTheDocument();
    graphReturn = base({ isLoading: true, data: undefined });
    rerender(<MotifGraphCanvas bookId="b" token="t" />);
    expect(screen.getByTestId('motif-graph-loading')).toBeInTheDocument();
    graphReturn = base({ isError: true, data: undefined });
    rerender(<MotifGraphCanvas bookId="b" token="t" />);
    expect(screen.getByTestId('motif-graph-error')).toBeInTheDocument();
  });

  it('flags truncation loudly when the book exceeds the node cap', () => {
    graphReturn = base({ data: { ...DATA, truncated: true } });
    render(<MotifGraphCanvas bookId="b" token="t" />);
    expect(screen.getByTestId('motif-graph-truncated')).toBeInTheDocument();
  });
});
