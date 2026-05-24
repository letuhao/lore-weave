import Phaser from 'phaser';
import { EventBus, getLatestTilemap, type PlayerActionEvent } from '../EventBus';
import { tileToScreen } from '../../lib/world-math';
import { TILE_PX } from '../config/constants';
import { Player } from '../entities/Player';
import { InputSystem } from '../systems/input-system';
import { terrainKindTag, type TilemapView } from '@/types/tilemap';

// V1 tilemap-viewer World scene.
//
// Renders the real `TilemapView.terrain_layer` (flat array, index =
// y*width + x, value = TerrainKind u8) as a top-down orthogonal grid
// using HoMM3-placeholder textures keyed by `terrain-<tag>`. Spec:
// `docs/specs/2026-05-24-v1-tilemap-viewer-rescope.md` §5.
//
// Data delivery: the React side passes a TilemapView in via
// `scene.data.set('tilemap', view)` before `scene.start('WorldScene')`.
// If no tilemap is present at create() time, the scene renders a small
// placeholder grid + waits for `tilemap-updated` events.

const FALLBACK_GRID_WIDTH = 8;
const FALLBACK_GRID_HEIGHT = 8;

export class WorldScene extends Phaser.Scene {
  private player: Player | null = null;
  private moveHandler: ((event: PlayerActionEvent) => void) | null = null;
  private tilemapHandler: ((view: TilemapView) => void) | null = null;

  constructor() {
    super({ key: 'WorldScene' });
  }

  create(): void {
    EventBus.emit('scene-ready', { key: 'WorldScene' });

    // The React side passes the current TilemapView via EventBus
    // `tilemap-updated` whenever useZoneTilemap data settles. On scene
    // boot the React fetch may have already finished before WorldScene
    // was created (Phaser boot chain takes 2-3s for asset load) — so
    // check the cached last-emitted view first.
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

    // Launch the optional Phaser-side HUD scene running in parallel.
    this.scene.launch('HudScene');
  }

  private renderTilemap(view: TilemapView): void {
    const w = view.grid_size.width;
    const h = view.grid_size.height;
    const renderedW = w * TILE_PX;
    const renderedH = h * TILE_PX;

    // Render at world (0,0); camera zoom + centerOn position the visible
    // viewport, no extra offset needed.

    // Render each tile in terrain_layer.
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const idx = y * w + x;
        const u8 = view.terrain_layer[idx];
        if (u8 === undefined || u8 < 1 || u8 > 10) {
          // Unknown TerrainKind — render magenta debug rect.
          this.add
            .rectangle(x * TILE_PX, y * TILE_PX, TILE_PX, TILE_PX, 0xff00ff)
            .setOrigin(0, 0);
          continue;
        }
        const tag = terrainKindTag(u8);
        const s = tileToScreen({ x, y }, TILE_PX);
        this.add
          .image(s.x, s.y, `terrain-${tag}`)
          .setDisplaySize(TILE_PX, TILE_PX)
          .setOrigin(0, 0);
      }
    }

    // Viewer zoom: default = 4× fit-to-viewport, so tiles are visible at
    // readable size (~50 px each on a 64² grid) instead of getting
    // shrunk to ~13 px. User pans / wheel-zooms to explore the rest.
    // Wheel-zoom handler attached in `attachCameraControls` below.
    const viewW = this.scale.gameSize.width;
    const viewH = this.scale.gameSize.height;
    const fitZoom = Math.min(viewW / renderedW, viewH / renderedH);
    const viewerZoom = Math.max(fitZoom * 4, 1.0);
    this.cameras.main.setBounds(0, 0, renderedW, renderedH);
    this.cameras.main.setZoom(viewerZoom);
    this.cameras.main.centerOn(renderedW / 2, renderedH / 2);
    this.attachCameraControls();

    // Spawn the Player at the first Hub-zone center if present, else
    // at the grid center.
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

    // Attach input + move handler.
    InputSystem.attach({ scene: this, offsetX: 0, offsetY: 0 });
    this.moveHandler = (event: PlayerActionEvent) => {
      if (event.kind === 'move' && event.target && this.player) {
        this.player.walkTo(event.target);
      }
    };
    EventBus.on('player-action', this.moveHandler);
  }

  private renderFallback(): void {
    const w = FALLBACK_GRID_WIDTH;
    const h = FALLBACK_GRID_HEIGHT;
    const renderedW = w * TILE_PX;
    const renderedH = h * TILE_PX;

    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const s = tileToScreen({ x, y }, TILE_PX);
        this.add
          .image(s.x, s.y, 'terrain-grass')
          .setDisplaySize(TILE_PX, TILE_PX)
          .setOrigin(0, 0);
      }
    }

    const viewW = this.scale.gameSize.width;
    const viewH = this.scale.gameSize.height;
    const fitZoom = Math.min(viewW / renderedW, viewH / renderedH, 1.0);
    this.cameras.main.setBounds(0, 0, renderedW, renderedH);
    this.cameras.main.setZoom(fitZoom);
    this.cameras.main.centerOn(renderedW / 2, renderedH / 2);

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
  }

  /**
   * Mouse-wheel zoom (V1 viewer ergonomics). Wheel up = zoom in, wheel
   * down = zoom out. Zoom is clamped so the user can't zoom past the
   * tile pixel grid (max 4×) or shrink below the fit-to-viewport limit.
   * Pan is handled by Phaser's default camera scroll on cursor keys via
   * keyboard; drag-to-pan deferred to V2.
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

    // Arrow-key panning — Phaser doesn't ship this out of the box, but
    // adding a quick handler is cheap. Drag-pan deferred to V2.
    const cursors = this.input.keyboard?.createCursorKeys();
    if (cursors) {
      this.events.on(Phaser.Scenes.Events.UPDATE, () => {
        const speed = 12 / cam.zoom;
        if (cursors.left?.isDown) cam.scrollX -= speed;
        if (cursors.right?.isDown) cam.scrollX += speed;
        if (cursors.up?.isDown) cam.scrollY -= speed;
        if (cursors.down?.isDown) cam.scrollY += speed;
      });
    }
  }

  private clearAndRerender(view: TilemapView): void {
    // Tear down current handlers + display list, then re-render with the
    // new tilemap. Phaser's scene.restart() would also work but skips our
    // event-handler cleanup — manual is cheap + explicit.
    if (this.moveHandler) {
      EventBus.off('player-action', this.moveHandler);
      this.moveHandler = null;
    }
    InputSystem.detach({ scene: this });
    this.children.removeAll(true);
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
  }
}
