import Phaser from 'phaser';
import { EventBus } from '../EventBus';

// Loads game assets and shows a progress bar. V0 demo loads the Kenney
// CC0 isometric-tiles-landscape pack — specific tile filenames are
// documented in public/assets/PACKAGES.md.

const TILE_BASE = '/assets/tiles/kenney-isometric-landscape/PNG';

interface TileToLoad {
  key: string;
  file: string;
}

const TILES_TO_LOAD: readonly TileToLoad[] = [
  // V0 demo: grass only. Session E+ adds dirt/stone/water variants per
  // PACKAGES.md when biome bridge gates which tile is rendered per
  // WorldZoneSnapshot.biome.
  { key: 'tile-grass', file: `${TILE_BASE}/landscapeTiles_067.png` },
];

export class PreloaderScene extends Phaser.Scene {
  constructor() {
    super({ key: 'PreloaderScene' });
  }

  preload(): void {
    // Generate a quick Player placeholder sprite programmatically —
    // a yellow circle. Kenney character pack is V0+1 / V1 scope.
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

    // Real Kenney tile loads.
    for (const t of TILES_TO_LOAD) {
      this.load.image(t.key, t.file);
    }
  }

  create(): void {
    EventBus.emit('scene-ready', { key: 'PreloaderScene' });
    this.scene.start('MainMenuScene');
  }
}
