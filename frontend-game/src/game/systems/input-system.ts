import Phaser from 'phaser';
import { EventBus } from '../EventBus';
import { screenToTile } from '../../lib/world-math';
import { TILE_PX } from '../config/constants';

// Pointer input → canonical PlayerActionEvent emit via EventBus.
//
// V1 tilemap-viewer rescope: identity (top-down) screen-to-tile per
// `lib/world-math.ts`. Pointer worldX/worldY are already camera-adjusted
// by Phaser, so we subtract the rendered scene offset (configured by
// the scene's `offsetX/Y`) before flooring by TILE_PX.

export interface InputSystemConfig {
  scene: Phaser.Scene;
  offsetX: number;
  offsetY: number;
}

interface DetachConfig {
  scene: Phaser.Scene;
}

// Per-scene handler registry so detach knows which fn to remove.
const handlers = new Map<string, (pointer: Phaser.Input.Pointer) => void>();

export const InputSystem = {
  attach(config: InputSystemConfig): void {
    const key = config.scene.scene.key;
    InputSystem.detach({ scene: config.scene });

    const handler = (pointer: Phaser.Input.Pointer): void => {
      const sx = pointer.worldX - config.offsetX;
      const sy = pointer.worldY - config.offsetY;
      const target = screenToTile({ x: sx, y: sy }, TILE_PX);
      // Shift-click → inspector; plain click → walk.
      const eventShift =
        pointer.event instanceof MouseEvent ? pointer.event.shiftKey : false;
      if (eventShift) {
        EventBus.emit('inspect-tile', target);
      } else {
        EventBus.emit('player-action', { kind: 'move', target });
      }
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
