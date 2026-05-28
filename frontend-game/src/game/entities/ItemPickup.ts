// World-placed item pickup stub. Session E+ fills with WS-driven spawn
// + click-to-pickup interaction.

import Phaser from 'phaser';

export class ItemPickup extends Phaser.GameObjects.Sprite {
  constructor(scene: Phaser.Scene, x: number, y: number, texture: string) {
    super(scene, x, y, texture);
    scene.add.existing(this);
  }
}
