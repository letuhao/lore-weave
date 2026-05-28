import { describe, expect, it, vi } from 'vitest';
import { EventBus, type PlayerActionEvent } from '@/game/EventBus';

// Contract test for EventBus — the single React↔Phaser event channel.
// Per spec §1 #4 + §17.1 abstraction, the bus is a Phaser.Events.EventEmitter
// instance shared via module singleton.

describe('EventBus', () => {
  it('delivers emitted events to listeners', () => {
    const handler = vi.fn();
    EventBus.on('player-action', handler);

    const event: PlayerActionEvent = { kind: 'move', target: { x: 3, y: 4 } };
    EventBus.emit('player-action', event);

    expect(handler).toHaveBeenCalledWith(event);
    EventBus.off('player-action', handler);
  });

  it('off() removes the listener — subsequent emits are not delivered', () => {
    const handler = vi.fn();
    EventBus.on('player-action', handler);
    EventBus.off('player-action', handler);

    EventBus.emit('player-action', { kind: 'attack' });
    expect(handler).not.toHaveBeenCalled();
  });

  it('multiple listeners on the same event all receive the payload', () => {
    const a = vi.fn();
    const b = vi.fn();
    EventBus.on('scene-ready', a);
    EventBus.on('scene-ready', b);

    EventBus.emit('scene-ready', { key: 'WorldScene' });

    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(1);
    EventBus.off('scene-ready', a);
    EventBus.off('scene-ready', b);
  });
});
