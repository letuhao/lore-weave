import Phaser from 'phaser';
import { EventBus } from '../EventBus';

// Placeholder main menu scene. Session D wires a real "Press to start"
// flow with title art. For now this scene immediately advances to
// WorldScene so the scaffold smoke can verify gameplay rendering.

export class MainMenuScene extends Phaser.Scene {
  constructor() {
    super({ key: 'MainMenuScene' });
  }

  create(): void {
    EventBus.emit('scene-ready', { key: 'MainMenuScene' });

    const center = this.cameras.main.midPoint;
    this.add
      .text(center.x, center.y, 'LoreWeave — Main Menu (placeholder)', {
        color: '#cbd5e1',
        fontSize: '20px',
        fontFamily: 'monospace',
      })
      .setOrigin(0.5);

    // Auto-advance after 800 ms so the V0 smoke flow lands in WorldScene
    // without manual interaction. Session D replaces with a click handler.
    this.time.delayedCall(800, () => this.scene.start('WorldScene'));
  }
}
