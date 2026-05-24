import Phaser from 'phaser';
import type { TilemapView } from '@/types/tilemap';

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

/** V1 tilemap-viewer: emitted by React when a new TilemapView arrives so
 *  the running WorldScene can re-render without a full scene restart. */
export type TilemapUpdatedEvent = TilemapView;

export const EventBus = new Phaser.Events.EventEmitter();

// Latest TilemapView seen on the bus. React side may emit
// `tilemap-updated` before WorldScene.create() runs (the Phaser boot
// chain takes 2-3 s for asset load). WorldScene reads this on mount as
// a fall-back so the very first render shows real data, not fallback.
let lastTilemap: TilemapView | null = null;
EventBus.on('tilemap-updated', (view: TilemapView) => {
  lastTilemap = view;
});
export function getLatestTilemap(): TilemapView | null {
  return lastTilemap;
}
