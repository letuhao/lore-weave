import Phaser from 'phaser';
import { EventBus } from '../EventBus';

// Optional Phaser-side HUD scene running in parallel with WorldScene.
// Per spec §1 #3, the primary HUD is React DOM overlay (HpBar/ManaBar
// components). This scene is reserved for canvas-anchored UI that
// MUST live inside Phaser (nameplates above NPCs, damage numbers,
// minimap that wants to share the GL context). V0: placeholder.

export class HudScene extends Phaser.Scene {
  constructor() {
    super({ key: 'HudScene' });
  }

  create(): void {
    EventBus.emit('scene-ready', { key: 'HudScene' });
  }
}
