import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { GraphCanvas, type Pos } from '../GraphCanvas';

// C19 — pan/zoom added to the shared GraphCanvas as an opt-in `zoomable` mode.
// These tests guard (1) the new zoom/pan/reset behaviour and (2) that
// node-drag still works in zoomable mode, and (3) that NON-zoomable mode is
// byte-compatible (no transform/reset — the T2.2 RelationshipMap is untouched).

type E = { id: string; from: string; to: string };
const edges: E[] = [{ id: 'e1', from: 'a', to: 'b' }];
const positions: Record<string, Pos> = { a: { x: 50, y: 50 }, b: { x: 200, y: 150 } };

function renderCanvas(props: Partial<React.ComponentProps<typeof GraphCanvas<E>>> = {}) {
  const onNodeDrag = vi.fn();
  const onNodeClick = vi.fn();
  render(
    <GraphCanvas<E>
      testid="g"
      positions={positions}
      nodeIds={['a', 'b']}
      edges={edges}
      edgeEndpoints={(e) => ({ from: e.from, to: e.to })}
      edgeKey={(e) => e.id}
      nodeSize={{ w: 140, h: 46 }}
      onNodeDrag={onNodeDrag}
      onNodeClick={onNodeClick}
      renderEdge={(e, from, to) => <line data-testid={`edge-${e.id}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} />}
      renderNode={(id, h) => (
        <g key={id} data-testid={`node-${id}`}>
          <rect data-testid={`node-body-${id}`} width={140} height={46} onPointerDown={h.onPointerDown} />
        </g>
      )}
      {...props}
    />,
  );
  return { onNodeDrag, onNodeClick };
}

describe('GraphCanvas zoomable mode (C19)', () => {
  it('wraps content in a pan/zoom transform group with a reset control', () => {
    renderCanvas({ zoomable: true });
    expect(screen.getByTestId('g-transform')).toBeInTheDocument();
    expect(screen.getByTestId('g-reset')).toBeInTheDocument();
    expect(screen.getByTestId('g-viewport')).toBeInTheDocument();
  });

  it('mouse-wheel zooms the canvas (scale changes)', () => {
    renderCanvas({ zoomable: true });
    const svg = screen.getByTestId('g');
    expect(svg.getAttribute('data-zoom')).toBe('1.000');
    fireEvent.wheel(svg, { deltaY: -200, clientX: 100, clientY: 100 }); // zoom in
    expect(Number(svg.getAttribute('data-zoom'))).toBeGreaterThan(1);
  });

  it('reset returns the view to identity', () => {
    renderCanvas({ zoomable: true });
    const svg = screen.getByTestId('g');
    fireEvent.wheel(svg, { deltaY: -300, clientX: 0, clientY: 0 });
    expect(Number(svg.getAttribute('data-zoom'))).toBeGreaterThan(1);
    fireEvent.click(screen.getByTestId('g-reset'));
    expect(svg.getAttribute('data-zoom')).toBe('1.000');
  });

  it('empty-space drag pans (transform translates)', () => {
    renderCanvas({ zoomable: true });
    const svg = screen.getByTestId('g');
    const g = screen.getByTestId('g-transform');
    expect(g.getAttribute('transform')).toContain('translate(0, 0)');
    fireEvent.pointerDown(screen.getByTestId('g-pan-catcher'), { clientX: 10, clientY: 10 });
    fireEvent.pointerMove(svg, { clientX: 60, clientY: 40 });
    expect(g.getAttribute('transform')).toContain('translate(50, 30)');
    fireEvent.pointerUp(svg);
  });

  it('node-drag still works in zoomable mode', () => {
    const { onNodeDrag } = renderCanvas({ zoomable: true });
    const svg = screen.getByTestId('g');
    fireEvent.pointerDown(screen.getByTestId('node-body-a'), { clientX: 0, clientY: 0 });
    fireEvent.pointerMove(svg, { clientX: 30, clientY: 0 }); // past the 5px threshold
    expect(onNodeDrag).toHaveBeenCalled();
    fireEvent.pointerUp(svg);
  });

  it('non-zoomable mode is unchanged — no transform/reset (T2.2 back-compat)', () => {
    renderCanvas({ zoomable: false });
    expect(screen.queryByTestId('g-transform')).toBeNull();
    expect(screen.queryByTestId('g-reset')).toBeNull();
    expect(screen.getByTestId('g-bg')).toBeInTheDocument();
  });
});
