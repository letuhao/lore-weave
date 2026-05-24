import Phaser from 'phaser';
import { EventBus } from '../EventBus';

// Loads all game assets and shows a progress bar. V0 has no real assets
// yet — Session D wires Kenney CC0 packs. For now we generate a stub
// tile texture programmatically (no asset file) and immediately advance.

export class PreloaderScene extends Phaser.Scene {
  constructor() {
    super({ key: 'PreloaderScene' });
  }

  preload(): void {
    // Generate a stub iso diamond tile texture (128×64 with diamond mask).
    const diamond = [
      new Phaser.Math.Vector2(64, 0),
      new Phaser.Math.Vector2(128, 32),
      new Phaser.Math.Vector2(64, 64),
      new Phaser.Math.Vector2(0, 32),
    ];
    const g = this.add.graphics();
    g.fillStyle(0x4f46e5, 1);
    g.fillPoints(diamond, true);
    g.lineStyle(2, 0x1e1b4b, 1);
    g.strokePoints(diamond, true);
    g.generateTexture('stub-iso-tile', 128, 64);
    g.destroy();
  }

  create(): void {
    EventBus.emit('scene-ready', { key: 'PreloaderScene' });
    this.scene.start('MainMenuScene');
  }
}
