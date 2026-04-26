import Phaser from 'phaser';
import type { TileCoord, TileMapView } from '../data/types';
import { indexToTerrain } from '../data/types';
import {
  MOUNTAIN_RIDGE_COLOR,
  OBJECT_EMOJI,
  ROAD_COLOR,
  SHORELINE_COLOR,
  TERRAIN_COLOR,
  variantColor,
} from '../render/colors';
import { hash2D } from '../generators/prng';
import { generateDecorations } from '../render/decorations';
import {
  CELL_SPRITES,
  KENNEY,
  LANDMARK_SPRITES,
  frameOf,
  type TileIndex,
} from '../render/kenney_atlas';

const TILE_SIZE = 16;

export interface SelectInfo {
  kind: string;
  name: string;
  channel_id: string;
  position: TileCoord;
  category: 'cell' | 'landmark';
}

export interface SceneInitData {
  view: TileMapView;
  onSelect: (info: SelectInfo) => void;
}

export class TilemapScene extends Phaser.Scene {
  private view!: TileMapView;
  private onSelect!: (info: SelectInfo) => void;

  // Render layers (z-order)
  private tilesGraphics?: Phaser.GameObjects.Graphics;
  private bordersGraphics?: Phaser.GameObjects.Graphics;
  private decorationsLayer?: Phaser.GameObjects.Container;
  private roadsGraphics?: Phaser.GameObjects.Graphics;
  private objectsLayer?: Phaser.GameObjects.Container;

  private spritesLoaded = false;

  private dragState = {
    dragging: false,
    startX: 0,
    startY: 0,
    scrollX: 0,
    scrollY: 0,
    moved: false,
  };

  constructor() {
    super({ key: 'TilemapScene' });
  }

  init(data: SceneInitData): void {
    this.view = data.view;
    this.onSelect = data.onSelect;
  }

  preload(): void {
    // Try to load Kenney spritesheet. If not present, asset_loader_failed event fires
    // and renderer falls back to colored squares + emoji.
    this.load.spritesheet(KENNEY.sheetKey, KENNEY.sheetPath, {
      frameWidth: KENNEY.frameWidth,
      frameHeight: KENNEY.frameHeight,
      margin: KENNEY.margin,
      spacing: KENNEY.spacing,
    });

    this.load.on('complete', () => {
      this.spritesLoaded = this.textures.exists(KENNEY.sheetKey);
    });

    this.load.on('loaderror', (_file: Phaser.Loader.File) => {
      this.spritesLoaded = false;
    });
  }

  create(): void {
    const { width, height } = this.view.grid_size;
    const worldW = width * TILE_SIZE;
    const worldH = height * TILE_SIZE;

    // Layers in z-order (bottom → top)
    this.tilesGraphics = this.add.graphics();
    this.bordersGraphics = this.add.graphics();
    this.decorationsLayer = this.add.container();
    this.roadsGraphics = this.add.graphics();
    this.objectsLayer = this.add.container();

    this.renderTiles();
    this.renderBiomeBorders();
    this.renderDecorations();
    this.renderRoads();
    this.renderObjects();

    // Camera setup
    this.cameras.main.setBounds(0, 0, worldW, worldH);
    this.cameras.main.setZoom(1.5);
    this.cameras.main.centerOn(worldW / 2, worldH / 2);
    this.cameras.main.setBackgroundColor('#0d1117');

    this.bindInputHandlers();
  }

  // ─── Input / camera ─────────────────────────────────────────────────────

  private bindInputHandlers(): void {
    this.input.on('pointerdown', (pointer: Phaser.Input.Pointer) => {
      this.dragState.dragging = true;
      this.dragState.moved = false;
      this.dragState.startX = pointer.x;
      this.dragState.startY = pointer.y;
      this.dragState.scrollX = this.cameras.main.scrollX;
      this.dragState.scrollY = this.cameras.main.scrollY;
    });
    this.input.on('pointerup', () => {
      this.dragState.dragging = false;
    });
    this.input.on('pointermove', (pointer: Phaser.Input.Pointer) => {
      if (!this.dragState.dragging) return;
      const dx = (pointer.x - this.dragState.startX) / this.cameras.main.zoom;
      const dy = (pointer.y - this.dragState.startY) / this.cameras.main.zoom;
      if (Math.abs(dx) + Math.abs(dy) > 3) this.dragState.moved = true;
      this.cameras.main.setScroll(this.dragState.scrollX - dx, this.dragState.scrollY - dy);
    });

    // Scroll-toward-pointer zoom
    this.input.on(
      'wheel',
      (
        pointer: Phaser.Input.Pointer,
        _objects: unknown,
        _dx: number,
        deltaY: number,
      ) => {
        const oldZoom = this.cameras.main.zoom;
        const newZoom = Phaser.Math.Clamp(oldZoom - deltaY * 0.0015, 0.5, 4);
        if (newZoom === oldZoom) return;
        const cam = this.cameras.main;
        const worldPoint = cam.getWorldPoint(pointer.x, pointer.y);
        cam.setZoom(newZoom);
        const newWorld = cam.getWorldPoint(pointer.x, pointer.y);
        cam.setScroll(
          cam.scrollX + (worldPoint.x - newWorld.x),
          cam.scrollY + (worldPoint.y - newWorld.y),
        );
      },
    );
  }

  setZoom(z: number): void {
    this.cameras.main.setZoom(Phaser.Math.Clamp(z, 0.5, 4));
  }

  zoomBy(delta: number): void {
    this.setZoom(this.cameras.main.zoom + delta);
  }

  rebuild(view: TileMapView): void {
    this.view = view;
    this.renderTiles();
    this.renderBiomeBorders();
    if (this.decorationsLayer) this.decorationsLayer.removeAll(true);
    this.renderDecorations();
    this.renderRoads();
    if (this.objectsLayer) this.objectsLayer.removeAll(true);
    this.renderObjects();
  }

  // ─── Render: terrain base ───────────────────────────────────────────────

  private renderTiles(): void {
    if (!this.tilesGraphics) return;
    const g = this.tilesGraphics;
    g.clear();
    const { width, height } = this.view.grid_size;
    const seed = this.view.procedural_seed;

    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const idx = y * width + x;
        const terrain = indexToTerrain(this.view.terrain_layer[idx]);
        const baseColor = TERRAIN_COLOR[terrain];
        const variant = hash2D(x, y, seed);
        const color = variantColor(baseColor, variant);
        g.fillStyle(color, 1);
        g.fillRect(x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE);
      }
    }
  }

  // ─── Render: biome borders (Water shoreline + Mountain ridge) ──────────

  private renderBiomeBorders(): void {
    if (!this.bordersGraphics) return;
    const g = this.bordersGraphics;
    g.clear();
    const { width, height } = this.view.grid_size;

    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const idx = y * width + x;
        const t = indexToTerrain(this.view.terrain_layer[idx]);
        if (t !== 'Water' && t !== 'Mountain') continue;

        // Check 4-neighbors for type change → draw border on that side
        const neighbors = [
          { dx: 0, dy: -1, side: 'top' },
          { dx: 1, dy: 0, side: 'right' },
          { dx: 0, dy: 1, side: 'bottom' },
          { dx: -1, dy: 0, side: 'left' },
        ];
        for (const n of neighbors) {
          const nx = x + n.dx;
          const ny = y + n.dy;
          if (nx < 0 || nx >= width || ny < 0 || ny >= height) continue;
          const nt = indexToTerrain(this.view.terrain_layer[ny * width + nx]);
          if (nt === t) continue;
          // Different terrain → draw border on this side
          const color = t === 'Water' ? SHORELINE_COLOR : MOUNTAIN_RIDGE_COLOR;
          g.lineStyle(2, color, 0.6);
          const px = x * TILE_SIZE;
          const py = y * TILE_SIZE;
          g.beginPath();
          if (n.side === 'top') {
            g.moveTo(px, py);
            g.lineTo(px + TILE_SIZE, py);
          } else if (n.side === 'right') {
            g.moveTo(px + TILE_SIZE, py);
            g.lineTo(px + TILE_SIZE, py + TILE_SIZE);
          } else if (n.side === 'bottom') {
            g.moveTo(px, py + TILE_SIZE);
            g.lineTo(px + TILE_SIZE, py + TILE_SIZE);
          } else if (n.side === 'left') {
            g.moveTo(px, py);
            g.lineTo(px, py + TILE_SIZE);
          }
          g.strokePath();
        }
      }
    }
  }

  // ─── Render: decorations (Kenney sprites scattered procedurally) ───────

  private renderDecorations(): void {
    if (!this.decorationsLayer) return;
    if (!this.spritesLoaded) return; // graceful fallback — no decorations without sprites

    const placements = generateDecorations(this.view);

    for (const p of placements) {
      const px = p.x * TILE_SIZE + TILE_SIZE / 2;
      const py = p.y * TILE_SIZE + TILE_SIZE / 2;
      const frame = frameOf(p.sprite);
      const img = this.add.image(px, py, KENNEY.sheetKey, frame).setOrigin(0.5);
      img.setScale(1);
      this.decorationsLayer.add(img);
    }
  }

  // ─── Render: roads ──────────────────────────────────────────────────────

  private renderRoads(): void {
    if (!this.roadsGraphics) return;
    const g = this.roadsGraphics;
    g.clear();
    for (const road of this.view.roads) {
      const color = ROAD_COLOR[road.road_kind];
      const lineWidth = road.road_kind === 'Highway' ? 5 : road.road_kind === 'Trade' ? 4 : 3;
      // Draw underlay first (slightly darker, wider) for shadow effect
      g.lineStyle(lineWidth + 2, 0x000000, 0.25);
      this.tracePolyline(g, road.waypoints);
      g.strokePath();
      // Main road color
      g.lineStyle(lineWidth, color, 0.95);
      this.tracePolyline(g, road.waypoints);
      g.strokePath();
    }
  }

  private tracePolyline(g: Phaser.GameObjects.Graphics, wp: TileCoord[]): void {
    if (wp.length < 2) return;
    g.beginPath();
    g.moveTo(wp[0].x * TILE_SIZE + TILE_SIZE / 2, wp[0].y * TILE_SIZE + TILE_SIZE / 2);
    for (let i = 1; i < wp.length; i++) {
      g.lineTo(wp[i].x * TILE_SIZE + TILE_SIZE / 2, wp[i].y * TILE_SIZE + TILE_SIZE / 2);
    }
  }

  // ─── Render: objects (cells + landmarks) ────────────────────────────────

  private renderObjects(): void {
    if (!this.objectsLayer) return;

    // Cells
    for (const cell of this.view.cell_placements) {
      const px = cell.position.x * TILE_SIZE + TILE_SIZE / 2;
      const py = cell.position.y * TILE_SIZE + TILE_SIZE / 2;
      const isCapital = cell.kind === 'capital';

      // Drop shadow circle for visual weight
      const shadow = this.add
        .circle(px, py + 3, isCapital ? 12 : 9, 0x000000, 0.35)
        .setOrigin(0.5);
      this.objectsLayer.add(shadow);

      // Sprite or emoji fallback
      const spriteIdx: TileIndex | undefined = (CELL_SPRITES as Record<string, TileIndex>)[cell.kind];
      const visual = this.makeCellVisual(px, py, cell.kind, spriteIdx, isCapital);
      this.objectsLayer.add(visual);
      visual.setInteractive({ useHandCursor: true });
      visual.on('pointerover', () => visual.setScale(visual.scale * 1.15));
      visual.on('pointerout', () => visual.setScale(visual.scale / 1.15));
      visual.on('pointerup', () => {
        if (this.dragState.moved) return;
        this.onSelect({
          kind: `cell:${cell.kind}`,
          name: cell.display_name,
          channel_id: cell.channel_id,
          position: cell.position,
          category: 'cell',
        });
      });

      // Label
      const labelOffsetY = isCapital ? 18 : 14;
      const label = this.add
        .text(px, py + labelOffsetY, cell.display_name, {
          fontSize: '10px',
          color: '#ffffff',
          backgroundColor: '#000000c0',
          padding: { left: 4, right: 4, top: 1, bottom: 1 },
          fontStyle: isCapital ? 'bold' : 'normal',
        })
        .setOrigin(0.5, 0);
      this.objectsLayer.add(label);
    }

    // Landmarks
    for (const obj of this.view.object_placements) {
      const px = obj.position.x * TILE_SIZE + TILE_SIZE / 2;
      const py = obj.position.y * TILE_SIZE + TILE_SIZE / 2;

      // Smaller shadow
      const shadow = this.add.circle(px, py + 2, 7, 0x000000, 0.25).setOrigin(0.5);
      this.objectsLayer.add(shadow);

      const spriteIdx: TileIndex | undefined = (LANDMARK_SPRITES as Record<string, TileIndex>)[
        obj.kind
      ];
      const visual = this.makeLandmarkVisual(px, py, obj.kind, spriteIdx);
      this.objectsLayer.add(visual);
      visual.setInteractive({ useHandCursor: true });
      visual.on('pointerover', () => visual.setScale(visual.scale * 1.15));
      visual.on('pointerout', () => visual.setScale(visual.scale / 1.15));
      visual.on('pointerup', () => {
        if (this.dragState.moved) return;
        this.onSelect({
          kind: obj.kind,
          name: obj.display_name,
          channel_id: obj.object_id,
          position: obj.position,
          category: 'landmark',
        });
      });
    }
  }

  private makeCellVisual(
    px: number,
    py: number,
    kind: string,
    spriteIdx: TileIndex | undefined,
    isCapital: boolean,
  ): Phaser.GameObjects.Image | Phaser.GameObjects.Text {
    if (this.spritesLoaded && spriteIdx) {
      const img = this.add
        .image(px, py - 2, KENNEY.sheetKey, frameOf(spriteIdx))
        .setOrigin(0.5);
      img.setScale(isCapital ? 1.6 : 1.3);
      return img;
    }
    // Emoji fallback
    const emoji = OBJECT_EMOJI[kind as keyof typeof OBJECT_EMOJI] ?? '🏠';
    const fontSize = isCapital ? 26 : 20;
    return this.add
      .text(px, py, emoji, { fontSize: `${fontSize}px` })
      .setOrigin(0.5);
  }

  private makeLandmarkVisual(
    px: number,
    py: number,
    kind: string,
    spriteIdx: TileIndex | undefined,
  ): Phaser.GameObjects.Image | Phaser.GameObjects.Text {
    if (this.spritesLoaded && spriteIdx) {
      const img = this.add
        .image(px, py - 1, KENNEY.sheetKey, frameOf(spriteIdx))
        .setOrigin(0.5);
      img.setScale(1.15);
      return img;
    }
    const emoji = OBJECT_EMOJI[kind as keyof typeof OBJECT_EMOJI] ?? '❓';
    return this.add.text(px, py, emoji, { fontSize: '16px' }).setOrigin(0.5);
  }
}
