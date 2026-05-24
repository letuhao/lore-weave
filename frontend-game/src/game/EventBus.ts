import Phaser from 'phaser';

// Shared event bus — one Phaser.Events.EventEmitter instance bridging
// Phaser scenes ↔ React components. Per spec §1 #4 pattern "EventBus
// for discrete events" and §9 pattern #4 (event-driven Observer).
//
// Typed event payloads live here so both sides agree on shape.
// Add new event kinds here, NOT inline at emit/listen sites.

export type SceneReadyEvent = {
  key: 'BootScene' | 'PreloaderScene' | 'MainMenuScene' | 'WorldScene' | 'HudScene';
};

export type PlayerActionEvent = {
  kind: 'move' | 'attack' | 'use-item';
  target?: { x: number; y: number };
};

export const EventBus = new Phaser.Events.EventEmitter();
