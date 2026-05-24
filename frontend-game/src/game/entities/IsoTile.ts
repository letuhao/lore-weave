// IsoTile entity stub. Wraps a single iso tile sprite with extra
// metadata (biome, traversable, decoration). Session D fills.

import Phaser from 'phaser';

export class IsoTile extends Phaser.GameObjects.Image {
  constructor(scene: Phaser.Scene, x: number, y: number, texture: string) {
    super(scene, x, y, texture);
    scene.add.existing(this);
  }
}
