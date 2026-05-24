import Phaser from 'phaser';
import { EventBus } from '../EventBus';
import { terrainKindTag, TerrainKind } from '@/types/tilemap';

// Loads game assets and shows a progress bar.
//
// V1 tilemap-viewer rescope: loads 10 HoMM3-placeholder terrain tiles
// keyed by `terrain-<tag>` (one per TerrainKind variant 1-10). See
// `public/assets/tiles/homm3-placeholder/LICENSES.md` for source +
// license caveat (NON-COMMERCIAL placeholder only).

const TILE_BASE = '/assets/tiles/homm3-placeholder';

const TILES_TO_LOAD: ReadonlyArray<{ key: string; file: string }> = (
  [
    TerrainKind.Grass,
    TerrainKind.Forest,
    TerrainKind.Mountain,
    TerrainKind.Water,
    TerrainKind.Sand,
    TerrainKind.Snow,
    TerrainKind.Swamp,
    TerrainKind.Road,
    TerrainKind.Rough,
    TerrainKind.Subterranean,
  ] as const
).map((k) => {
  const tag = terrainKindTag(k);
  return { key: `terrain-${tag}`, file: `${TILE_BASE}/${tag}.png` };
});

export class PreloaderScene extends Phaser.Scene {
  constructor() {
    super({ key: 'PreloaderScene' });
  }

  preload(): void {
    // Generate a Player placeholder sprite programmatically — a yellow
    // circle. Per-book character art lands in a separate branch (see
    // SESSION_HANDOFF + DEFERRED #037).
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

    for (const t of TILES_TO_LOAD) {
      this.load.image(t.key, t.file);
    }
  }

  create(): void {
    EventBus.emit('scene-ready', { key: 'PreloaderScene' });
    this.scene.start('MainMenuScene');
  }
}
