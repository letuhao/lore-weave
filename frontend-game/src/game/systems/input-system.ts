import Phaser from 'phaser';
import { EventBus } from '../EventBus';
import { screenToTile } from '../../lib/iso-math';

// Pointer input → canonical PlayerActionEvent emit via EventBus.
//
// Per spec §1 #6 turn-based + idle MMO: no input buffering past one
// queued click. Spam-clicking just updates the destination, not stacks
// fast-fire actions.
//
// Lifecycle: attach() registers a pointerdown listener on the scene's
// input plugin; detach() removes it. WorldScene.shutdown() calls detach
// so Vite HMR + Phaser scene transitions don't leak handlers.

export interface InputSystemConfig {
  scene: Phaser.Scene;
  offsetX: number;
  offsetY: number;
}

interface DetachConfig {
  scene: Phaser.Scene;
}

// Per-scene handler registry so detach knows which fn to remove.
// Keyed by scene's unique key.
const handlers = new Map<string, (pointer: Phaser.Input.Pointer) => void>();

export const InputSystem = {
  attach(config: InputSystemConfig): void {
    const key = config.scene.scene.key;
    // Idempotent: detach prior handler if attach is called twice (HMR
    // can trigger this when the scene file changes).
    InputSystem.detach({ scene: config.scene });

    const handler = (pointer: Phaser.Input.Pointer): void => {
      const wx = pointer.worldX - config.offsetX;
      const wy = pointer.worldY - config.offsetY;
      const target = screenToTile({ x: wx, y: wy });
      EventBus.emit('player-action', { kind: 'move', target });
    };

    handlers.set(key, handler);
    config.scene.input.on(Phaser.Input.Events.POINTER_DOWN, handler);
  },

  detach(config: DetachConfig): void {
    const key = config.scene.scene.key;
    const handler = handlers.get(key);
    if (handler) {
      config.scene.input.off(Phaser.Input.Events.POINTER_DOWN, handler);
      handlers.delete(key);
    }
  },
};
