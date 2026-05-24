import Phaser from 'phaser';

// Shared event bus — one Phaser.Events.EventEmitter instance bridging
// Phaser scenes ↔ React components. Per spec §1 #4 pattern "EventBus
// for discrete events" and §9 pattern #4 (event-driven Observer).
//
// Typed event payloads live here so both sides agree on shape.

export type ValidationStatusEvent =
  | { kind: 'webgl'; ok: boolean }
  | { kind: 'tilemap'; ok: boolean }
  | { kind: 'sprite'; ok: boolean }
  | { kind: 'fps'; value: number }
  | { kind: 'error'; message: string };

export const EventBus = new Phaser.Events.EventEmitter();
