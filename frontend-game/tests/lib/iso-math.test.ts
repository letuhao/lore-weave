import { describe, expect, it } from 'vitest';
import { screenToTile, screenToWorld, worldToScreen } from '@/lib/iso-math';

// Sanity test: iso-math round-trip. Spec §16 Session C ACs require
// scaffold + 1 sanity test pass.

describe('iso-math', () => {
  it('worldToScreen of (0,0) is (0,0)', () => {
    expect(worldToScreen({ x: 0, y: 0 })).toEqual({ x: 0, y: 0 });
  });

  it('round-trips integer tile coordinates', () => {
    for (let x = -5; x <= 5; x++) {
      for (let y = -5; y <= 5; y++) {
        const screen = worldToScreen({ x, y });
        const tile = screenToTile(screen);
        expect(tile).toEqual({ x, y });
      }
    }
  });

  it('screenToWorld is the inverse of worldToScreen', () => {
    const worlds = [
      { x: 1, y: 2 },
      { x: -3, y: 4 },
      { x: 10, y: -7 },
    ];
    for (const w of worlds) {
      const s = worldToScreen(w);
      const back = screenToWorld(s);
      expect(back.x).toBeCloseTo(w.x, 10);
      expect(back.y).toBeCloseTo(w.y, 10);
    }
  });
});
