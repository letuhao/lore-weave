import Phaser from 'phaser';
import { EventBus } from '../EventBus';
import { screenToTile } from '../../lib/iso-math';

// Pointer input → canonical PlayerActionEvent emit via EventBus.
//
// Per spec §1 #6 turn-based + idle MMO: no input buffering past one
// queued click. Spam-clicking just updates the destination, not stacks
// fast-fire actions.

export interface InputSystemConfig {
  scene: Phaser.Scene;
  offsetX: number;
  offsetY: number;
}

export const InputSystem = {
  attach(config: InputSystemConfig): void {
    config.scene.input.on(
      Phaser.Input.Events.POINTER_DOWN,
      (pointer: Phaser.Input.Pointer) => {
        // Translate browser pixel → world coords (account for our
        // worldToScreen offset that centers the zone in the viewport).
        const wx = pointer.worldX - config.offsetX;
        const wy = pointer.worldY - config.offsetY;
        const target = screenToTile({ x: wx, y: wy });
        EventBus.emit('player-action', {
          kind: 'move',
          target,
        });
      },
    );
  },
};
