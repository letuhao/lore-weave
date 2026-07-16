import { describe, expect, it } from 'vitest';
import { nodeIntersectsViewport } from '../GraphCanvas';

// D-S5-SCENEGRAPH-VIRTUALIZE — the viewport-cull predicate (grown by 1 viewport each way).
const NS = { w: 160, h: 90 };
const vp = { l: 1000, t: 1000, r: 1800, b: 1600 }; // 800×600 viewport, scrolled to (1000,1000)

describe('nodeIntersectsViewport', () => {
  it('a node inside the viewport intersects', () => {
    expect(nodeIntersectsViewport({ x: 1200, y: 1200 }, NS, vp)).toBe(true);
  });

  it('a node within ONE viewport of margin still intersects (pre-mount before scroll-in)', () => {
    // just left of the viewport by ~half a viewport-width — within the 1-viewport margin
    expect(nodeIntersectsViewport({ x: 700, y: 1200 }, NS, vp)).toBe(true);
    // just below by ~half a viewport-height
    expect(nodeIntersectsViewport({ x: 1200, y: 1900 }, NS, vp)).toBe(true);
  });

  it('a node THREE viewports away is culled', () => {
    // viewport width 800; 3× to the right → x ~ 1800 + 2*800 = 3400 (beyond the +1vp margin at 2600)
    expect(nodeIntersectsViewport({ x: 3400, y: 1200 }, NS, vp)).toBe(false);
    // far above
    expect(nodeIntersectsViewport({ x: 1200, y: -800 }, NS, vp)).toBe(false);
  });

  it('a node straddling the viewport edge intersects (its box overlaps)', () => {
    expect(nodeIntersectsViewport({ x: 1750, y: 1550 }, NS, vp)).toBe(true); // box crosses r/b edge
  });

  it('at book scale, only a viewport-sized slice of a 10k grid survives the cull', () => {
    // 10k nodes on a 100×100 grid at 200px pitch → a 20000×20000 world.
    const nodes: { x: number; y: number }[] = [];
    for (let i = 0; i < 100; i++) for (let j = 0; j < 100; j++) nodes.push({ x: i * 200, y: j * 200 });
    const kept = nodes.filter((p) => nodeIntersectsViewport(p, NS, vp)).length;
    expect(kept).toBeGreaterThan(0);
    expect(kept).toBeLessThan(400); // O(viewport), not O(10000)
  });
});
