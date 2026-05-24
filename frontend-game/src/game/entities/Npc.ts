// NPC entity stub. Session D+ fills with dialog tree + behavior FSM.

import Phaser from 'phaser';

export class Npc extends Phaser.GameObjects.Sprite {
  constructor(scene: Phaser.Scene, x: number, y: number, texture: string) {
    super(scene, x, y, texture);
    scene.add.existing(this);
  }
}
