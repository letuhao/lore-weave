import { render, screen, fireEvent } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GraphCanvas, type Pos } from '../GraphCanvas';

// M5b — on a ≤767px viewport every heavy canvas becomes pan/zoom/pinch-able (the
// desktop overflow scroller is unusable on touch). useIsMobile → true here.
vi.mock('@/hooks/useIsMobile', () => ({ useIsMobile: () => true }));

type E = { id: string; from: string; to: string };
const edges: E[] = [{ id: 'e1', from: 'a', to: 'b' }];
const positions: Record<string, Pos> = { a: { x: 50, y: 50 }, b: { x: 200, y: 150 } };

function renderCanvas(props: Partial<React.ComponentProps<typeof GraphCanvas<E>>> = {}) {
  render(
    <GraphCanvas<E>
      testid="g"
      positions={positions}
      nodeIds={['a', 'b']}
      edges={edges}
      edgeEndpoints={(e) => ({ from: e.from, to: e.to })}
      edgeKey={(e) => e.id}
      nodeSize={{ w: 140, h: 46 }}
      onNodeDrag={vi.fn()}
      onNodeClick={vi.fn()}
      renderEdge={(e, from, to) => <line data-testid={`edge-${e.id}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} />}
      renderNode={(id, h) => (
        <g key={id} data-testid={`node-${id}`}>
          <rect data-testid={`node-body-${id}`} width={140} height={46} onPointerDown={h.onPointerDown} />
        </g>
      )}
      {...props}
    />,
  );
}

afterEach(() => vi.restoreAllMocks());

describe('GraphCanvas mobile (M5b)', () => {
  it('FORCES the pan/zoom viewport on mobile even when zoomable is false', () => {
    renderCanvas({ zoomable: false }); // desktop default for Scene Graph / Rel Map
    // mobile upgrades it to the zoomable viewport (vs the desktop overflow scroller)
    expect(screen.getByTestId('g-viewport')).toBeInTheDocument();
    expect(screen.getByTestId('g-transform')).toBeInTheDocument();
    expect(screen.getByTestId('g-reset')).toBeInTheDocument();
  });

  it('two-finger pinch zooms toward the gesture (scale grows as fingers spread)', () => {
    renderCanvas({ zoomable: false });
    const svg = screen.getByTestId('g');
    expect(svg.getAttribute('data-zoom')).toBe('1.000');
    // two pointers down 100px apart, then spread the 2nd to 200px → 2× distance
    fireEvent.pointerDown(svg, { pointerId: 1, clientX: 0, clientY: 0 });
    fireEvent.pointerDown(svg, { pointerId: 2, clientX: 100, clientY: 0 });
    fireEvent.pointerMove(svg, { pointerId: 2, clientX: 200, clientY: 0 });
    expect(Number(svg.getAttribute('data-zoom'))).toBeGreaterThan(1);
    fireEvent.pointerUp(svg, { pointerId: 1 });
    fireEvent.pointerUp(svg, { pointerId: 2 });
  });

  it('fits-to-screen on mount when the graph is larger than the viewport (scale < 1)', () => {
    // jsdom getBoundingClientRect is all-zero; mock a small viewport so fit fires.
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({
      width: 200, height: 200, left: 0, top: 0, right: 200, bottom: 200, x: 0, y: 0, toJSON: () => {},
    } as DOMRect);
    renderCanvas({ zoomable: false });
    // extent ~364×220 fit into 200×200 → scale ≈ 0.55 (< 1, never upscaled)
    const z = Number(screen.getByTestId('g').getAttribute('data-zoom'));
    expect(z).toBeGreaterThan(0);
    expect(z).toBeLessThan(1);
  });
});
