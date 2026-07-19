import Phaser from 'phaser';
import { EventBus, getLatestTilemap, type PlayerActionEvent } from '../EventBus';
import { TILE_PX } from '../config/constants';
import { Player } from '../entities/Player';
import { InputSystem } from '../systems/input-system';
import { TERRAIN_TILESET_KEY } from './PreloaderScene';
import { applyBlendFilterV2 } from '../render/foundation-blend';
import { buildObjectOverlay, type ObjectOverlayHandle } from '../render/object-overlay';
import { buildOverlayRt, type OverlayRtHandle } from '../render/overlay-rt';
import { buildZoneBoundaryOverlay, type ZoneBoundaryHandle } from '../render/zone-boundary-overlay';
import { useViewerStore } from '@/store/viewer-store';
import type { TilemapView } from '@/types/tilemap';

// V1 tilemap-viewer World scene — Batch 2.0 render strategy.
//
// Foundation (L0) uses Phaser 4 `TilemapGPULayer`: tile indices are
// packed into a GPU texture and the entire grid renders as a single
// shader-driven quad → O(1) draw calls regardless of grid size
// (Town 64² and Continent 256² both cost the same).
//
// Tile index in `TilemapView.terrain_layer` is 1-based (TerrainKind
// enum, 1..10). The tileset spritesheet has 10 frames in TerrainKind
// order; we subtract 1 when calling `putTileAt` so frame 0 = grass.
//
// Data delivery: React side emits `tilemap-updated` via EventBus when
// `useZoneTilemap` data settles. `getLatestTilemap()` cache handles
// the case where data arrived before scene boot.

const FALLBACK_GRID_WIDTH = 8;
const FALLBACK_GRID_HEIGHT = 8;
const FALLBACK_TERRAIN_TILE_INDEX = 0; // grass

export class WorldScene extends Phaser.Scene {
  private player: Player | null = null;
  private moveHandler: ((event: PlayerActionEvent) => void) | null = null;
  private tilemapHandler: ((view: TilemapView) => void) | null = null;
  private foundationMap: Phaser.Tilemaps.Tilemap | null = null;
  private objectOverlay: ObjectOverlayHandle | null = null;
  private overlayRt: OverlayRtHandle | null = null;
  private zoneBoundary: ZoneBoundaryHandle | null = null;
  private foundationDisplay: Phaser.GameObjects.GameObject | null = null;
  private viewerStoreUnsubscribe: (() => void) | null = null;

  constructor() {
    super({ key: 'WorldScene' });
  }

  create(): void {
    EventBus.emit('scene-ready', { key: 'WorldScene' });

    this.tilemapHandler = (next: TilemapView) => {
      this.clearAndRerender(next);
    };
    EventBus.on('tilemap-updated', this.tilemapHandler);

    const cached = getLatestTilemap();
    if (cached) {
      this.renderTilemap(cached);
    } else {
      this.renderFallback();
    }

    this.scene.launch('HudScene');
  }

  /**
   * Build a Phaser Tilemap + GPU-rendered foundation layer from the
   * server's `terrain_layer` flat array. Falls back to standard
   * `TilemapLayer` if `TilemapGPULayer` is unavailable.
   */
  private buildFoundationLayer(
    terrainLayer: number[],
    gridWidth: number,
    gridHeight: number,
  ): void {
    // Convert flat u8 (1..10) → 2D matrix of zero-based tile indices.
    // Out-of-range u8 values fall back to grass (index 0).
    const data: number[][] = [];
    for (let y = 0; y < gridHeight; y++) {
      const row: number[] = [];
      for (let x = 0; x < gridWidth; x++) {
        const u8 = terrainLayer[y * gridWidth + x];
        const idx = u8 !== undefined && u8 >= 1 && u8 <= 10 ? u8 - 1 : FALLBACK_TERRAIN_TILE_INDEX;
        row.push(idx);
      }
      data.push(row);
    }

    this.foundationMap = this.make.tilemap({
      data,
      tileWidth: TILE_PX,
      tileHeight: TILE_PX,
    });

    const tileset = this.foundationMap.addTilesetImage(
      TERRAIN_TILESET_KEY,
      TERRAIN_TILESET_KEY,
      TILE_PX,
      TILE_PX,
    );
    if (!tileset) {
      throw new Error(`failed to add tileset image ${TERRAIN_TILESET_KEY}`);
    }

    // Try GPU layer first (single-quad shader render); fall back to the
    // standard tilemap layer if the GPU layer fails (e.g. WebGL context
    // lost or extension missing).
    try {
      const gpu = new Phaser.Tilemaps.TilemapGPULayer(this, this.foundationMap, 0, tileset, 0, 0);
      this.add.existing(gpu);
      gpu.generateLayerDataTexture();
      this.foundationDisplay = gpu;
    } catch (err) {
      console.warn('TilemapGPULayer unavailable, falling back to TilemapLayer', err);
      const std = this.foundationMap.createLayer(0, tileset, 0, 0);
      if (!std) {
        throw new Error('foundation tilemap layer creation failed', { cause: err });
      }
      this.foundationDisplay = std;
    }

    // TMP-Q3 chunk A — Stage-1 smooth-blend polish. Reads viewer-store
    // `blendEnabled` flag (default true). Wraps in try/catch so a
    // Phaser-version skew or missing WebGL extension falls back to the
    // V0 hard-pixel rendering without breaking the scene.
    this.applyBlendFilter();
  }

  /** TMP-Q3 chunk A — apply / remove the Stage-1 Blur filter on the
   *  foundation display based on the viewer-store `blendEnabled` flag.
   *  Delegates the actual filter mutation to the pure helper in
   *  `foundation-blend.ts` so the logic is unit-testable without
   *  mounting Phaser. */
  private applyBlendFilter(): void {
    const enabled = useViewerStore.getState().blendEnabled;
    // Phaser types declare `filters: FiltersInternalExternal | null` —
    // narrower than our duck-typed surface. Cast via unknown because
    // we only call the optional members the helper actually invokes.
    const target = this.foundationDisplay as unknown as Parameters<typeof applyBlendFilterV2>[0];
    // TMP-Q3 chunk C — read the currently-cached TilemapView so the
    // V2 helper can pick per-kind blend hints from the vocabulary.
    // Cached view may be undefined during the initial fallback render;
    // that's fine — V2 helper just uses STAGE2_BLEND_DEFAULTS.
    const view = getLatestTilemap() ?? undefined;
    // Try Stage 2 custom shader first. The V2 helper internally falls
    // back to Stage 1 Blur on shader-register / controller-add failure,
    // and to V0 hard edges if Stage 1 also fails.
    const result = applyBlendFilterV2(target, enabled, this, view);
    if (!result.ok) {
      console.warn('Blend filter pipeline unavailable; rendering V0 hard edges', result.error);
      return;
    }
    if (result.stage === 1) {
      console.info('Stage-2 cross-tile blend unavailable; using Stage-1 Blur fallback');
    }
  }

  private renderTilemap(view: TilemapView): void {
    const w = view.grid_size.width;
    const h = view.grid_size.height;
    const renderedW = w * TILE_PX;
    const renderedH = h * TILE_PX;

    this.buildFoundationLayer(view.terrain_layer, w, h);
    // L1/L2/L2.5/L6 (roads, rivers, crossings, zone centers) baked first
    // so prop sprites depth-sort above them; L4 props next.
    this.overlayRt = buildOverlayRt(this, view);
    // L5 zone-boundary outline — RT at depth 60 between paths RT (50)
    // and props (100). Default hidden; viewer-store toggle controls.
    this.zoneBoundary = buildZoneBoundaryOverlay(this, view);
    this.objectOverlay = buildObjectOverlay(this, view);

    const viewW = this.scale.gameSize.width;
    const viewH = this.scale.gameSize.height;
    const fitZoom = Math.min(viewW / renderedW, viewH / renderedH);
    const viewerZoom = Math.max(fitZoom * 4, 1.0);
    this.cameras.main.setBounds(0, 0, renderedW, renderedH);
    this.cameras.main.setZoom(viewerZoom);
    this.cameras.main.centerOn(renderedW / 2, renderedH / 2);
    this.attachCameraControls();

    const hubZone = view.zones.find((z) => z.zone_role === 'hub');
    const startTile = hubZone
      ? hubZone.center_position
      : { x: Math.floor(w / 2), y: Math.floor(h / 2) };

    this.player = new Player({
      scene: this,
      startTile,
      offsetX: 0,
      offsetY: 0,
      zoneWidth: w,
      zoneHeight: h,
    });

    InputSystem.attach({ scene: this, offsetX: 0, offsetY: 0 });
    this.moveHandler = (event: PlayerActionEvent) => {
      if (event.kind === 'move' && event.target && this.player) {
        this.player.walkTo(event.target);
      }
    };
    EventBus.on('player-action', this.moveHandler);

    this.applyViewerStoreVisibility();
    this.subscribeViewerStore();
  }

  /** Apply the current viewer-store visibility flags to all live layers. */
  private applyViewerStoreVisibility(): void {
    const state = useViewerStore.getState();
    const v = state.visibleLayers;
    if (this.foundationDisplay && 'visible' in this.foundationDisplay) {
      (this.foundationDisplay as unknown as { visible: boolean }).visible = v.foundation;
    }
    this.overlayRt?.setRtVisible(v.paths);
    this.overlayRt?.setZoneCentersVisible(v.zone_centers);
    // TMP-Q4 chunk C — zone-tier treasure-band overlay is independent
    // of L0..L7 layer toggles; route the dedicated `showTreasureBands`
    // flag straight through to the overlay-rt handle.
    this.overlayRt?.setTreasureBandsVisible(state.showTreasureBands);
    this.zoneBoundary?.setVisible(v.zone_boundaries);
    this.objectOverlay?.setEnabled(v.objects);
    if (this.player) {
      this.player.sprite.visible = v.player;
    }
  }

  private subscribeViewerStore(): void {
    if (this.viewerStoreUnsubscribe) {
      this.viewerStoreUnsubscribe();
    }
    // Track previous flag so we only re-apply the (potentially expensive)
    // blend filter when the toggle changes — visibility-only updates skip
    // the filter rebuild.
    let prevBlendEnabled = useViewerStore.getState().blendEnabled;
    this.viewerStoreUnsubscribe = useViewerStore.subscribe(() => {
      this.applyViewerStoreVisibility();
      const nextBlend = useViewerStore.getState().blendEnabled;
      if (nextBlend !== prevBlendEnabled) {
        prevBlendEnabled = nextBlend;
        this.applyBlendFilter();
      }
    });
  }

  private renderFallback(): void {
    const w = FALLBACK_GRID_WIDTH;
    const h = FALLBACK_GRID_HEIGHT;
    const renderedW = w * TILE_PX;
    const renderedH = h * TILE_PX;

    // Build an all-grass fallback so we exercise the same layer path
    // when the scene boots before any TilemapView arrives.
    const fallbackTerrain = new Array<number>(w * h).fill(1);
    this.buildFoundationLayer(fallbackTerrain, w, h);

    const viewW = this.scale.gameSize.width;
    const viewH = this.scale.gameSize.height;
    const fitZoom = Math.min(viewW / renderedW, viewH / renderedH, 1.0);
    this.cameras.main.setBounds(0, 0, renderedW, renderedH);
    this.cameras.main.setZoom(fitZoom);
    this.cameras.main.centerOn(renderedW / 2, renderedH / 2);
    this.attachCameraControls();

    this.player = new Player({
      scene: this,
      startTile: { x: Math.floor(w / 2), y: Math.floor(h / 2) },
      offsetX: 0,
      offsetY: 0,
      zoneWidth: w,
      zoneHeight: h,
    });
    InputSystem.attach({ scene: this, offsetX: 0, offsetY: 0 });
    this.moveHandler = (event: PlayerActionEvent) => {
      if (event.kind === 'move' && event.target && this.player) {
        this.player.walkTo(event.target);
      }
    };
    EventBus.on('player-action', this.moveHandler);

    // TMP-Q3 chunk A LOW-1 fix: even on the fallback all-grass path,
    // wire the same viewer-store visibility + toggle subscription as
    // renderTilemap so the "Smooth blend" checkbox works when the
    // backend stays unreachable. The fallback is shortlived (replaced
    // when tilemap-updated fires) but the toggle should still respond
    // for the offline-preview workflow.
    this.applyViewerStoreVisibility();
    this.subscribeViewerStore();
  }

  /**
   * Mouse-wheel zoom + arrow-key pan. Wheel up = zoom in. Clamp keeps
   * zoom in [0.05, 4.0]. Drag-to-pan deferred to a follow-up.
   */
  private attachCameraControls(): void {
    const cam = this.cameras.main;
    this.input.on(
      Phaser.Input.Events.POINTER_WHEEL,
      (
        _pointer: Phaser.Input.Pointer,
        _objects: Phaser.GameObjects.GameObject[],
        _dx: number,
        dy: number,
      ) => {
        const factor = dy < 0 ? 1.15 : 1 / 1.15;
        const next = Phaser.Math.Clamp(cam.zoom * factor, 0.05, 4.0);
        cam.setZoom(next);
      },
    );

    const cursors = this.input.keyboard?.createCursorKeys();
    this.events.on(Phaser.Scenes.Events.UPDATE, () => {
      if (cursors) {
        const speed = 12 / cam.zoom;
        if (cursors.left?.isDown) cam.scrollX -= speed;
        if (cursors.right?.isDown) cam.scrollX += speed;
        if (cursors.up?.isDown) cam.scrollY -= speed;
        if (cursors.down?.isDown) cam.scrollY += speed;
      }
      // Chunk culling + LOD update each frame.
      this.objectOverlay?.update();
    });
  }

  private clearAndRerender(view: TilemapView): void {
    if (this.moveHandler) {
      EventBus.off('player-action', this.moveHandler);
      this.moveHandler = null;
    }
    InputSystem.detach({ scene: this });
    if (this.viewerStoreUnsubscribe) {
      this.viewerStoreUnsubscribe();
      this.viewerStoreUnsubscribe = null;
    }
    if (this.objectOverlay) {
      this.objectOverlay.destroy();
      this.objectOverlay = null;
    }
    if (this.zoneBoundary) {
      this.zoneBoundary.destroy();
      this.zoneBoundary = null;
    }
    if (this.overlayRt) {
      this.overlayRt.destroy();
      this.overlayRt = null;
    }
    this.children.removeAll(true);
    if (this.foundationMap) {
      this.foundationMap.destroy();
      this.foundationMap = null;
    }
    this.foundationDisplay = null;
    this.player = null;
    this.renderTilemap(view);
  }

  shutdown(): void {
    if (this.moveHandler) {
      EventBus.off('player-action', this.moveHandler);
      this.moveHandler = null;
    }
    if (this.tilemapHandler) {
      EventBus.off('tilemap-updated', this.tilemapHandler);
      this.tilemapHandler = null;
    }
    InputSystem.detach({ scene: this });
    if (this.viewerStoreUnsubscribe) {
      this.viewerStoreUnsubscribe();
      this.viewerStoreUnsubscribe = null;
    }
    if (this.objectOverlay) {
      this.objectOverlay.destroy();
      this.objectOverlay = null;
    }
    if (this.zoneBoundary) {
      this.zoneBoundary.destroy();
      this.zoneBoundary = null;
    }
    if (this.overlayRt) {
      this.overlayRt.destroy();
      this.overlayRt = null;
    }
    if (this.foundationMap) {
      this.foundationMap.destroy();
      this.foundationMap = null;
    }
    this.foundationDisplay = null;
  }
}
