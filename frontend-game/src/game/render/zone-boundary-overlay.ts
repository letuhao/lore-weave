import Phaser from 'phaser';
import { TILE_PX } from '../config/constants';
import type { TileMask, TilemapView } from '@/types/tilemap';

// L5 zone boundary overlay — render an outline around each zone using
// the authoritative `zones[].assigned_tiles` bitmap. Re-baked into a
// single RenderTexture (Strategy C) so the live blit is 1 quad.
//
// Boundary detection: 4-neighbour. A tile T at (x,y) is a boundary tile
// for zone Z when:
//   - T belongs to Z (bit set in Z.assigned_tiles)
//   - At least one of T's 4 neighbours (x±1, y±1) either belongs to a
//     DIFFERENT zone or is outside the grid.
//
// 4-neighbour avoids the over-detection 8-neighbour would produce on
// thin diagonal seams; for boundary lines visible at 64-px tile scale
// this matches the player's perception of "this tile is on the edge".

const BOUNDARY_LINE_WIDTH = 3;

// Role-colored outlines mirror the zone-center marker palette in
// overlay-rt.ts so the eye links centre dot ↔ outline at a glance.
const ZONE_ROLE_COLORS: Record<string, number> = {
  capital: 0xfacc15,
  hub: 0x818cf8,
  wilderness: 0x4ade80,
  forbidden: 0xf87171,
  sea: 0x60a5fa,
  arena: 0xf472b6,
  mine_camp: 0xa78bfa,
  town: 0xfbbf24,
};

function tileSet(mask: TileMask, x: number, y: number): boolean {
  if (x < 0 || y < 0 || x >= mask.width || y >= mask.height) return false;
  const idx = y * mask.width + x;
  const wordIdx = idx >> 6;
  const bitPos = BigInt(idx & 63);
  const word = mask.bits[wordIdx];
  if (word === undefined) return false;
  return (word >> bitPos) & 1n ? true : false;
}

type EdgeSegment = readonly [number, number, number, number];

interface ZoneEdges {
  /** Each entry is [x1, y1, x2, y2] in pixel coords. */
  edges: EdgeSegment[];
  color: number;
}

function detectZoneEdges(
  mask: TileMask,
  color: number,
): ZoneEdges {
  // Instead of detecting boundary TILES then walking around them, we
  // walk every (x,y) tile in the zone and emit one or more pixel-line
  // segments for whichever of its 4 sides has no in-zone neighbour.
  // Result is exact (line segments between tiles) without needing a
  // polygon-trace pass.
  const edges: EdgeSegment[] = [];
  for (let y = 0; y < mask.height; y++) {
    for (let x = 0; x < mask.width; x++) {
      if (!tileSet(mask, x, y)) continue;
      const x0 = x * TILE_PX;
      const y0 = y * TILE_PX;
      const x1 = x0 + TILE_PX;
      const y1 = y0 + TILE_PX;
      if (!tileSet(mask, x, y - 1)) edges.push([x0, y0, x1, y0]); // top
      if (!tileSet(mask, x + 1, y)) edges.push([x1, y0, x1, y1]); // right
      if (!tileSet(mask, x, y + 1)) edges.push([x0, y1, x1, y1]); // bottom
      if (!tileSet(mask, x - 1, y)) edges.push([x0, y0, x0, y1]); // left
    }
  }
  return { edges, color };
}

export interface ZoneBoundaryHandle {
  destroy(): void;
  setVisible(v: boolean): void;
}

export function buildZoneBoundaryOverlay(
  scene: Phaser.Scene,
  view: TilemapView,
): ZoneBoundaryHandle {
  const w = view.grid_size.width;
  const h = view.grid_size.height;
  const renderedW = w * TILE_PX;
  const renderedH = h * TILE_PX;

  const rt = scene.add.renderTexture(0, 0, renderedW, renderedH);
  rt.setOrigin(0, 0);
  rt.setDepth(60); // above paths RT (50), below props (100)

  const g = scene.add.graphics();
  for (const zone of view.zones) {
    if (!zone.assigned_tiles || !zone.assigned_tiles.bits) continue;
    const color = ZONE_ROLE_COLORS[zone.zone_role] ?? 0xffffff;
    const { edges } = detectZoneEdges(zone.assigned_tiles, color);
    if (edges.length === 0) continue;
    g.lineStyle(BOUNDARY_LINE_WIDTH, color, 0.95);
    g.beginPath();
    for (const [x1, y1, x2, y2] of edges) {
      g.moveTo(x1, y1);
      g.lineTo(x2, y2);
    }
    g.strokePath();
  }
  rt.draw(g);
  g.destroy();

  // Default hidden — zone boundaries are a debug toggle.
  rt.visible = false;

  return {
    destroy: () => rt.destroy(),
    setVisible: (v) => {
      rt.visible = v;
    },
  };
}

// Exported for unit tests (test fixture builds a TileMask then asserts
// per-side edge counts).
export { tileSet, detectZoneEdges };
