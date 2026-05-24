import Phaser from 'phaser';
import { EventBus } from '../EventBus';

// Loads critical assets for V1 tilemap viewer.
//
// Batch 2.0 (render-strategy spec): foundation now uses one stitched
// `terrain-tileset.png` strip (10 × 256 px tiles) consumed directly by
// Phaser 4 `TilemapGPULayer`. This replaces 10 individual `terrain-*.png`
// loads from Batch 1, and replaces per-tile `add.image()` calls in
// WorldScene with a single GPU-shader-rendered quad layer.
//
// Per-tile PNGs are kept on disk (the generator outputs both) so debug
// tooling and asset-review workflows can inspect tiles individually
// without slicing the strip back open.

const TILE_BASE = '/assets/tiles/homm3-placeholder';
const TERRAIN_TILESET_KEY = 'terrain-tileset';

export class PreloaderScene extends Phaser.Scene {
  constructor() {
    super({ key: 'PreloaderScene' });
  }

  preload(): void {
    // Programmatic Player placeholder — yellow circle 32×32.
    // (Will be replaced by a programmatic warrior sprite at 384×384 in
    // Batch 2.1 per the tier table; the stub is fine for Batch 2.0.)
    const playerGfx = this.add.graphics();
    playerGfx.fillStyle(0xfbbf24, 1);
    playerGfx.fillCircle(16, 16, 14);
    playerGfx.lineStyle(2, 0x78350f, 1);
    playerGfx.strokeCircle(16, 16, 14);
    playerGfx.generateTexture('player-stub', 32, 32);
    playerGfx.destroy();

    // Progress bar UI.
    const cam = this.cameras.main;
    const cx = cam.midPoint.x;
    const cy = cam.midPoint.y;
    const barBg = this.add.rectangle(cx, cy, 320, 16, 0x334155);
    const bar = this.add.rectangle(cx - 160, cy, 0, 16, 0x4f46e5).setOrigin(0, 0.5);
    this.load.on('progress', (value: number) => {
      bar.width = 320 * value;
    });
    this.load.on('complete', () => {
      bar.destroy();
      barBg.destroy();
    });

    // Critical-path: the stitched tileset strip used by TilemapGPULayer
    // for the foundation layer. Frame size 64×64 matches TILE_PX so the
    // tilemap renders at 1:1 source → screen ratio at zoom 1.0.
    this.load.spritesheet(TERRAIN_TILESET_KEY, `${TILE_BASE}/terrain-tileset.png`, {
      frameWidth: 64,
      frameHeight: 64,
    });
  }

  create(): void {
    EventBus.emit('scene-ready', { key: 'PreloaderScene' });
    this.scene.start('MainMenuScene');
  }
}

export { TERRAIN_TILESET_KEY };
