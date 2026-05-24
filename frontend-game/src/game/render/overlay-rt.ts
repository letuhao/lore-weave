import Phaser from 'phaser';
import { TILE_PX } from '../config/constants';
import type { TilemapView } from '@/types/tilemap';

// L1 roads + L2 rivers + L2.5 crossings + L6 zone-center markers —
// Strategy C (RenderTexture pre-bake) per render-strategy spec §2 C.
//
// One `RenderTexture` sized to the world extent. After build, all
// frames render the RT as a single quad blit. Re-baked only when
// `useZoneTilemap` data changes (via clearAndRerender in WorldScene).
//
// Zone-boundary overlay (L5) deferred to V2: `zones[].assigned_tiles`
// is a u64 bitmap in the wire response, but JSON deserialization loses
// precision past 2^53 — needs BigInt JSON reviver to be reliable.
// V1.2 ships zone CENTERS only (cheap, no bitmap needed).

const ROAD_COLOR = 0x8a6e4b; // earth brown
const ROAD_ALPHA = 0.85;
const ROAD_WIDTH = 6;

const RIVER_COLOR = 0x2e5c8a; // deep blue
const RIVER_ALPHA = 0.9;
const RIVER_WIDTH = 10;

const BRIDGE_COLOR = 0xd4a13a; // golden plank
const FORD_COLOR = 0x9bc6d8; // light stones-in-water

const ZONE_CENTER_COLORS: Record<string, number> = {
  capital: 0xfacc15,
  hub: 0x818cf8,
  wilderness: 0x4ade80,
  forbidden: 0xf87171,
  sea: 0x60a5fa,
  arena: 0xf472b6,
  mine_camp: 0xa78bfa,
  town: 0xfbbf24,
};

export interface OverlayRtHandle {
  destroy(): void;
}

function tileCenterX(x: number): number {
  return x * TILE_PX + TILE_PX / 2;
}
function tileCenterY(y: number): number {
  return y * TILE_PX + TILE_PX / 2;
}

function drawRoads(g: Phaser.GameObjects.Graphics, view: TilemapView): void {
  g.lineStyle(ROAD_WIDTH, ROAD_COLOR, ROAD_ALPHA);
  for (const seg of view.road_segments ?? []) {
    if (!seg.waypoints || seg.waypoints.length < 2) continue;
    g.beginPath();
    const first = seg.waypoints[0];
    if (!first) continue;
    g.moveTo(tileCenterX(first.x), tileCenterY(first.y));
    for (let i = 1; i < seg.waypoints.length; i++) {
      const wp = seg.waypoints[i];
      if (!wp) continue;
      g.lineTo(tileCenterX(wp.x), tileCenterY(wp.y));
    }
    g.strokePath();
  }
}

function drawRivers(g: Phaser.GameObjects.Graphics, view: TilemapView): void {
  g.lineStyle(RIVER_WIDTH, RIVER_COLOR, RIVER_ALPHA);
  for (const seg of view.river_segments ?? []) {
    if (!seg.tiles || seg.tiles.length < 2) continue;
    g.beginPath();
    const first = seg.tiles[0];
    if (!first) continue;
    g.moveTo(tileCenterX(first.x), tileCenterY(first.y));
    for (let i = 1; i < seg.tiles.length; i++) {
      const t = seg.tiles[i];
      if (!t) continue;
      g.lineTo(tileCenterX(t.x), tileCenterY(t.y));
    }
    g.strokePath();
  }
}

function drawCrossings(g: Phaser.GameObjects.Graphics, view: TilemapView): void {
  for (const seg of view.river_segments ?? []) {
    for (const c of seg.crossings ?? []) {
      const cx = tileCenterX(c.at.x);
      const cy = tileCenterY(c.at.y);
      if (c.kind === 'bridge') {
        // Golden plank: filled rect rotated to follow the river axis.
        // Cheap approximation — axis detection deferred V2; for V1 use
        // horizontal plank.
        g.fillStyle(BRIDGE_COLOR, 1.0);
        g.fillRect(cx - 18, cy - 6, 36, 12);
        g.lineStyle(2, 0x5a4422, 1.0);
        g.strokeRect(cx - 18, cy - 6, 36, 12);
      } else {
        // Ford: 3 small light-blue circles "stones"
        g.fillStyle(FORD_COLOR, 1.0);
        g.fillCircle(cx - 10, cy, 5);
        g.fillCircle(cx, cy, 5);
        g.fillCircle(cx + 10, cy, 5);
      }
    }
  }
}

function drawZoneCenters(
  scene: Phaser.Scene,
  view: TilemapView,
  parent: Phaser.GameObjects.Container,
): void {
  for (const zone of view.zones ?? []) {
    const cx = tileCenterX(zone.center_position.x);
    const cy = tileCenterY(zone.center_position.y);
    const color = ZONE_CENTER_COLORS[zone.zone_role] ?? 0xffffff;
    // Ring + dot marker so it stands out against any underlying terrain.
    const ring = scene.add.circle(cx, cy, 18, color, 0).setStrokeStyle(4, color, 0.9);
    const dot = scene.add.circle(cx, cy, 5, color, 0.9);
    // Zone-id label slightly below the marker.
    const label = scene.add
      .text(cx, cy + 26, zone.zone_id, {
        fontFamily: 'monospace',
        fontSize: '14px',
        color: '#f1f5f9',
        backgroundColor: 'rgba(15,23,42,0.85)',
        padding: { left: 4, right: 4, top: 1, bottom: 1 },
      })
      .setOrigin(0.5, 0)
      .setDepth(200);
    parent.add(ring);
    parent.add(dot);
    parent.add(label);
  }
}

export function buildOverlayRt(
  scene: Phaser.Scene,
  view: TilemapView,
): OverlayRtHandle {
  const w = view.grid_size.width;
  const h = view.grid_size.height;
  const renderedW = w * TILE_PX;
  const renderedH = h * TILE_PX;

  // RenderTexture for roads + rivers + crossings.
  const rt = scene.add.renderTexture(0, 0, renderedW, renderedH);
  rt.setOrigin(0, 0);
  rt.setDepth(50); // above L0 foundation (depth 0), below L4 props (100)

  const g = scene.add.graphics();
  drawRoads(g, view);
  drawRivers(g, view);
  drawCrossings(g, view);
  rt.draw(g);
  g.destroy();

  // Zone centers — separate Container above props/RT (depth 200).
  // Each marker is small + dynamic; keeping them as live GameObjects
  // lets a future viewer-store toggle them visible/hidden cheaply.
  const zoneContainer = scene.add.container(0, 0);
  zoneContainer.setDepth(200);
  drawZoneCenters(scene, view, zoneContainer);

  return {
    destroy: () => {
      rt.destroy();
      zoneContainer.destroy(true);
    },
  };
}
