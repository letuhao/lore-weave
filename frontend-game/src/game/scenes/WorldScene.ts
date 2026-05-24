import Phaser from 'phaser';
import { EventBus } from '../EventBus';
import { worldToScreen } from '../../lib/iso-math';
import { DEFAULT_ZONE_HEIGHT, DEFAULT_ZONE_WIDTH } from '../config/constants';

// Minimal V0 World scene: renders a stub iso tilemap so visual smoke
// confirms the scaffold + iso-math pipeline works end-to-end.
// Session D replaces the stub with real Kenney CC0 tiles + a Player
// entity that walks tile-by-tile.

export class WorldScene extends Phaser.Scene {
  constructor() {
    super({ key: 'WorldScene' });
  }

  create(): void {
    EventBus.emit('scene-ready', { key: 'WorldScene' });

    // Render a small iso tilemap centered on the camera.
    const cam = this.cameras.main;
    const centerScreen = { x: cam.midPoint.x, y: cam.midPoint.y };

    // Compute the world-origin offset so the (0,0) tile lands at screen center.
    const halfW = DEFAULT_ZONE_WIDTH / 2;
    const halfH = DEFAULT_ZONE_HEIGHT / 2;
    const originOffset = worldToScreen({ x: halfW, y: halfH });
    const offsetX = centerScreen.x - originOffset.x;
    const offsetY = centerScreen.y - originOffset.y;

    for (let y = 0; y < DEFAULT_ZONE_HEIGHT; y++) {
      for (let x = 0; x < DEFAULT_ZONE_WIDTH; x++) {
        const s = worldToScreen({ x, y });
        this.add
          .image(offsetX + s.x, offsetY + s.y, 'stub-iso-tile')
          .setOrigin(0.5, 0.5);
      }
    }

    // Launch the optional Phaser-side HUD scene running in parallel.
    this.scene.launch('HudScene');
  }
}
