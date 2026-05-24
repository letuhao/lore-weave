import Phaser from 'phaser';
import { worldToScreen, type WorldCoord } from '../../lib/iso-math';

// Player sprite + walk-to-tile queue. Per spec §1 #6 (turn-based + idle
// MMO model): no client prediction, no input buffer past 1-2 queued
// targets, no interpolation between server snapshots. V0 is single-
// player local; Session E+ wires server-validated movement.

const WALK_MS_PER_TILE = 250;

export interface PlayerInit {
  scene: Phaser.Scene;
  startTile: WorldCoord;
  offsetX: number;
  offsetY: number;
  /**
   * Zone bounds for client-side boundary check. V0 has no server-side
   * collision; the Player would otherwise tween off the visible grid.
   * V1 server validates movement and rejects out-of-bounds — this check
   * becomes a UX hint rather than the only guard.
   */
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
    const screen = worldToScreen(this.tile);
    this.sprite = init.scene.add
      .sprite(init.offsetX + screen.x, init.offsetY + screen.y - 32, 'player-stub')
      .setOrigin(0.5, 0.5)
      .setDepth(1000);
  }

  get currentTile(): WorldCoord {
    return { ...this.tile };
  }

  /**
   * Returns true if the given tile is within zone bounds. Exposed for
   * tests + callers that want to validate before queueing.
   */
  isInBounds(target: WorldCoord): boolean {
    return (
      target.x >= 0 &&
      target.x < this.zoneWidth &&
      target.y >= 0 &&
      target.y < this.zoneHeight
    );
  }

  walkTo(target: WorldCoord): void {
    // Boundary check (V0 cleanup): silently drop out-of-zone clicks so
    // the Player doesn't tween into the void. V1 server-validated
    // movement makes this a UX hint, but for V0 demo it's the only guard.
    if (!this.isInBounds(target)) {
      return;
    }
    // If already heading there (or queued there), no-op so spam-clicking
    // the same tile doesn't stack tweens.
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
    const screen = worldToScreen(next);
    this.scene.tweens.add({
      targets: this.sprite,
      x: this.offsetX + screen.x,
      y: this.offsetY + screen.y - 32,
      duration: WALK_MS_PER_TILE,
      ease: 'Sine.easeInOut',
      onComplete: () => {
        this.tile = next;
        this.stepNext();
      },
    });
  }
}
