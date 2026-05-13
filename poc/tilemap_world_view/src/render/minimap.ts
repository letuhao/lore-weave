import type { TileMapView } from '../data/types';
import { indexToTerrain } from '../data/types';
import { TERRAIN_COLOR } from './colors';

/**
 * Minimap renderer — draws scaled-down view of full tilemap on a HTML canvas overlay.
 *
 * Positioned absolutely top-right of #game-container. Click on minimap pans main camera.
 * Highlights current camera viewport as a wireframe rectangle.
 *
 * Pure DOM/canvas — no Phaser dependency. Could move to Phaser scene if perf demands.
 */
export class Minimap {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private view: TileMapView;
  private tileScale = 2; // each tile = 2×2 px on minimap
  private viewportRect: { x: number; y: number; w: number; h: number } | null = null;
  private onJump?: (worldX: number, worldY: number) => void;

  constructor(view: TileMapView, parent: HTMLElement) {
    this.view = view;

    const w = view.grid_size.width * this.tileScale;
    const h = view.grid_size.height * this.tileScale;

    const wrapper = document.createElement('div');
    wrapper.id = 'minimap-wrapper';
    wrapper.style.cssText = `
      position: absolute;
      top: 12px;
      right: 12px;
      width: ${w + 6}px;
      padding: 3px;
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 4px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
      z-index: 100;
      font-family: 'JetBrains Mono', Consolas, monospace;
      font-size: 9px;
      color: #7d8590;
    `;

    const label = document.createElement('div');
    label.textContent = `MINIMAP · ${view.grid_size.width}×${view.grid_size.height}`;
    label.style.cssText = 'padding: 2px 4px; letter-spacing: 0.5px; text-transform: uppercase;';

    this.canvas = document.createElement('canvas');
    this.canvas.width = w;
    this.canvas.height = h;
    this.canvas.style.cssText = 'display: block; cursor: crosshair; image-rendering: pixelated;';

    wrapper.appendChild(label);
    wrapper.appendChild(this.canvas);
    parent.appendChild(wrapper);

    const ctx = this.canvas.getContext('2d');
    if (!ctx) throw new Error('Failed to get minimap canvas context');
    this.ctx = ctx;

    this.canvas.addEventListener('click', (e) => {
      if (!this.onJump) return;
      const rect = this.canvas.getBoundingClientRect();
      const minimapX = (e.clientX - rect.left) / this.tileScale;
      const minimapY = (e.clientY - rect.top) / this.tileScale;
      // Convert tile coords → world coords (16px per tile in main scene)
      this.onJump(minimapX * 16, minimapY * 16);
    });

    this.draw();
  }

  setOnJump(handler: (worldX: number, worldY: number) => void): void {
    this.onJump = handler;
  }

  rebuild(view: TileMapView): void {
    this.view = view;
    // Resize if grid changed
    const w = view.grid_size.width * this.tileScale;
    const h = view.grid_size.height * this.tileScale;
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    this.draw();
  }

  setViewportRect(worldX: number, worldY: number, worldW: number, worldH: number): void {
    // worldX/Y/W/H are in main-scene world pixels (16px per tile)
    const tileX = worldX / 16;
    const tileY = worldY / 16;
    const tileW = worldW / 16;
    const tileH = worldH / 16;
    this.viewportRect = {
      x: tileX * this.tileScale,
      y: tileY * this.tileScale,
      w: tileW * this.tileScale,
      h: tileH * this.tileScale,
    };
    this.drawViewport();
  }

  private draw(): void {
    const { width, height } = this.view.grid_size;
    const s = this.tileScale;

    // Base terrain
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const idx = y * width + x;
        const t = indexToTerrain(this.view.terrain_layer[idx]);
        const color = TERRAIN_COLOR[t];
        this.ctx.fillStyle = `#${color.toString(16).padStart(6, '0')}`;
        this.ctx.fillRect(x * s, y * s, s, s);
      }
    }

    // Roads — 1px lines
    this.ctx.strokeStyle = '#a68852';
    this.ctx.lineWidth = 1;
    for (const road of this.view.roads) {
      const wp = road.waypoints;
      if (wp.length < 2) continue;
      this.ctx.beginPath();
      this.ctx.moveTo(wp[0].x * s + s / 2, wp[0].y * s + s / 2);
      for (let i = 1; i < wp.length; i++) {
        this.ctx.lineTo(wp[i].x * s + s / 2, wp[i].y * s + s / 2);
      }
      this.ctx.stroke();
    }

    // Cell anchors — colored dots
    for (const cell of this.view.cell_placements) {
      const cx = cell.position.x * s + s / 2;
      const cy = cell.position.y * s + s / 2;
      const isCapital = cell.kind === 'capital';
      this.ctx.fillStyle = isCapital ? '#ffd700' : '#ffffff';
      this.ctx.beginPath();
      this.ctx.arc(cx, cy, isCapital ? 2.5 : 1.5, 0, Math.PI * 2);
      this.ctx.fill();
    }

    // Landmarks — smaller red dots
    for (const obj of this.view.object_placements) {
      const ox = obj.position.x * s + s / 2;
      const oy = obj.position.y * s + s / 2;
      this.ctx.fillStyle = '#f85149';
      this.ctx.fillRect(ox - 0.5, oy - 0.5, 1, 1);
    }

    this.drawViewport();
  }

  private drawViewport(): void {
    if (!this.viewportRect) return;
    const r = this.viewportRect;
    // Re-blit terrain underneath the rect by redrawing only that area? Simpler: draw rect on top.
    this.ctx.strokeStyle = '#58a6ff';
    this.ctx.lineWidth = 1;
    this.ctx.strokeRect(
      Math.max(0, r.x) + 0.5,
      Math.max(0, r.y) + 0.5,
      Math.min(this.canvas.width, r.w),
      Math.min(this.canvas.height, r.h),
    );
  }
}
