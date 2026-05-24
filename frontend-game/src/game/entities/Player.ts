// Player entity. Session D fills with real movement + state machine.
// Per spec §9 pattern #2 (composition over inheritance), extends Phaser
// Sprite and mixes in Movable + Damageable behaviors via systems/.

import Phaser from 'phaser';

export class Player extends Phaser.GameObjects.Sprite {
  constructor(scene: Phaser.Scene, x: number, y: number, texture: string) {
    super(scene, x, y, texture);
    scene.add.existing(this);
  }
}
