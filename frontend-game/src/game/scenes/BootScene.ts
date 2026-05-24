import Phaser from 'phaser';
import { EventBus } from '../EventBus';

// First scene in the chain. Configures global state (scale, input)
// and immediately advances to PreloaderScene where assets get loaded
// with a visible progress bar.

export class BootScene extends Phaser.Scene {
  constructor() {
    super({ key: 'BootScene' });
  }

  create(): void {
    EventBus.emit('scene-ready', { key: 'BootScene' });
    this.scene.start('PreloaderScene');
  }
}
