import { describe, expect, it } from 'vitest';
import { screenToTile, tileToScreen } from '@/lib/world-math';

// V1 tilemap-viewer rescope: identity (top-down) tile math round-trip.
// Replaces the V0 iso-math test set; spec
// `docs/specs/2026-05-24-v1-tilemap-viewer-rescope.md` §5.

const TILE_PX = 64;

describe('world-math', () => {
  it('tileToScreen of (0,0) is (0,0)', () => {
    expect(tileToScreen({ x: 0, y: 0 }, TILE_PX)).toEqual({ x: 0, y: 0 });
  });

  it('tileToScreen scales by TILE_PX', () => {
    expect(tileToScreen({ x: 3, y: 5 }, TILE_PX)).toEqual({ x: 192, y: 320 });
  });

  it('screenToTile floors fractional pixels into the owning tile', () => {
    // A click at (10, 70) is inside tile (0, 1) — the y-coord crosses
    // one tile boundary (64), the x-coord stays in tile 0.
    expect(screenToTile({ x: 10, y: 70 }, TILE_PX)).toEqual({ x: 0, y: 1 });
    // Boundary inclusivity — exactly on the line goes to the next tile.
    expect(screenToTile({ x: 64, y: 64 }, TILE_PX)).toEqual({ x: 1, y: 1 });
    expect(screenToTile({ x: 63, y: 63 }, TILE_PX)).toEqual({ x: 0, y: 0 });
  });

  it('tileToScreen → screenToTile round-trips integer tiles', () => {
    for (let x = 0; x < 10; x++) {
      for (let y = 0; y < 10; y++) {
        const s = tileToScreen({ x, y }, TILE_PX);
        const back = screenToTile(s, TILE_PX);
        expect(back).toEqual({ x, y });
      }
    }
  });

  it('uses default TILE_PX from constants when not passed', () => {
    // Default param value should match constants.TILE_PX (64).
    expect(tileToScreen({ x: 1, y: 1 })).toEqual({ x: 64, y: 64 });
    expect(screenToTile({ x: 128, y: 192 })).toEqual({ x: 2, y: 3 });
  });
});
