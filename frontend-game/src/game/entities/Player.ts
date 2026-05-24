import Phaser from 'phaser';
import { tileToScreen, type WorldCoord } from '../../lib/world-math';
import { TILE_PX } from '../config/constants';

// Player sprite + walk-to-tile queue. V1 tilemap-viewer rescope: top-down
// orthogonal walking on the real server-provided grid_size from
// TilemapView. No iso projection; sprite is centered on its tile.

const WALK_MS_PER_TILE = 250;

export interface PlayerInit {
  scene: Phaser.Scene;
  startTile: WorldCoord;
  /** Scene render offset (matches WorldScene.offsetX/Y). */
  offsetX: number;
  offsetY: number;
  /** Zone bounds from server-provided grid_size. */
  zoneWidth: number;
  zoneHeight: number;
}

export class Player {
  readonly sprite: Phaser.GameObjects.Sprite;
  private readonly scene: Phaser.Scene;
  private readonly offsetX: number;
  private readonly offsetY: number;
  private readonly zoneWidth: number;
  private readonly zoneHeight: number;
  private tile: WorldCoord;
  private queue: WorldCoord[] = [];
  private walking = false;

  constructor(init: PlayerInit) {
    this.scene = init.scene;
    this.offsetX = init.offsetX;
    this.offsetY = init.offsetY;
    this.zoneWidth = init.zoneWidth;
    this.zoneHeight = init.zoneHeight;
    this.tile = init.startTile;
    const screen = tileToScreen(this.tile, TILE_PX);
    this.sprite = init.scene.add
      .sprite(
        init.offsetX + screen.x + TILE_PX / 2,
        init.offsetY + screen.y + TILE_PX / 2,
        'player-stub',
      )
      .setOrigin(0.5, 0.5)
      .setDepth(1000);
  }

  get currentTile(): WorldCoord {
    return { ...this.tile };
  }

  isInBounds(target: WorldCoord): boolean {
    return (
      target.x >= 0 &&
      target.x < this.zoneWidth &&
      target.y >= 0 &&
      target.y < this.zoneHeight
    );
  }

  walkTo(target: WorldCoord): void {
    if (!this.isInBounds(target)) {
      return;
    }
    const last = this.queue.length > 0 ? this.queue[this.queue.length - 1] : this.tile;
    if (last && last.x === target.x && last.y === target.y) {
      return;
    }
    this.queue.push(target);
    if (!this.walking) {
      this.stepNext();
    }
  }

  private stepNext(): void {
    const next = this.queue.shift();
    if (!next) {
      this.walking = false;
      return;
    }
    this.walking = true;
    const screen = tileToScreen(next, TILE_PX);
    this.scene.tweens.add({
      targets: this.sprite,
      x: this.offsetX + screen.x + TILE_PX / 2,
      y: this.offsetY + screen.y + TILE_PX / 2,
      duration: WALK_MS_PER_TILE,
      ease: 'Sine.easeInOut',
      onComplete: () => {
        this.tile = next;
        this.stepNext();
      },
    });
  }
}
