import { describe, expect, it } from 'vitest';
import { tileSet, detectZoneEdges } from '@/game/render/zone-boundary-overlay';
import type { TileMask } from '@/types/tilemap';

function mask(bits: bigint[], width: number, height: number): TileMask {
  return { width, height, bits };
}

function setTile(bits: bigint[], width: number, x: number, y: number): void {
  const idx = y * width + x;
  const word = idx >> 6;
  const pos = BigInt(idx & 63);
  bits[word] = (bits[word] ?? 0n) | (1n << pos);
}

describe('zone-boundary tileSet', () => {
  it('reads back set bits', () => {
    const bits = [0n];
    setTile(bits, 8, 3, 1); // idx = 11
    const m = mask(bits, 8, 8);
    expect(tileSet(m, 3, 1)).toBe(true);
    expect(tileSet(m, 2, 1)).toBe(false);
  });

  it('handles bits crossing u64 word boundary', () => {
    // Width 16 → bit 63 = (15, 3); bit 64 = (0, 4)
    const bits = [0n, 0n];
    setTile(bits, 16, 15, 3); // idx 63 → word 0 high bit
    setTile(bits, 16, 0, 4);  // idx 64 → word 1 low bit
    const m = mask(bits, 16, 8);
    expect(tileSet(m, 15, 3)).toBe(true);
    expect(tileSet(m, 0, 4)).toBe(true);
    expect(tileSet(m, 1, 4)).toBe(false);
  });

  it('out-of-range coords return false (no buffer overrun)', () => {
    const m = mask([0xffffffffffffffffn], 8, 8);
    expect(tileSet(m, -1, 0)).toBe(false);
    expect(tileSet(m, 0, -1)).toBe(false);
    expect(tileSet(m, 8, 0)).toBe(false);
    expect(tileSet(m, 0, 8)).toBe(false);
  });
});

describe('zone-boundary detectZoneEdges', () => {
  it('single isolated tile emits all 4 sides', () => {
    const bits = [0n];
    setTile(bits, 8, 3, 3);
    const m = mask(bits, 8, 8);
    const { edges } = detectZoneEdges(m, 0xff00ff);
    expect(edges).toHaveLength(4);
  });

  it('2-tile horizontal pair emits 6 sides (no edge between them)', () => {
    const bits = [0n];
    setTile(bits, 8, 3, 3);
    setTile(bits, 8, 4, 3);
    const m = mask(bits, 8, 8);
    const { edges } = detectZoneEdges(m, 0xff00ff);
    expect(edges).toHaveLength(6);
  });

  it('full 8x8 grid emits perimeter only — 4 sides × 8 = 32', () => {
    const bits = [0xffffffffffffffffn];
    const m = mask(bits, 8, 8);
    const { edges } = detectZoneEdges(m, 0xff00ff);
    expect(edges).toHaveLength(32);
  });

  it('empty bitmap → 0 edges', () => {
    const m = mask([0n], 8, 8);
    expect(detectZoneEdges(m, 0xff00ff).edges).toHaveLength(0);
  });
});
