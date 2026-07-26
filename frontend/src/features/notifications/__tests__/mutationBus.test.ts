import { describe, it, expect, vi } from 'vitest';
import { emitNotificationsMutated, onNotificationsMutated } from '../mutationBus';

// N7/N8 — the cross-surface "unread changed" signal that keeps the nav bell, studio
// status badge, and center page from drifting after a mark-read on any one surface.
describe('notifications mutationBus', () => {
  it('delivers the signal to subscribers', () => {
    const cb = vi.fn();
    const off = onNotificationsMutated(cb);
    emitNotificationsMutated();
    emitNotificationsMutated();
    expect(cb).toHaveBeenCalledTimes(2);
    off();
  });

  it('stops delivering after unsubscribe (no leak between surfaces)', () => {
    const cb = vi.fn();
    const off = onNotificationsMutated(cb);
    off();
    emitNotificationsMutated();
    expect(cb).not.toHaveBeenCalled();
  });

  it('fans out to multiple independent badge consumers', () => {
    const bell = vi.fn();
    const statusItem = vi.fn();
    const offA = onNotificationsMutated(bell);
    const offB = onNotificationsMutated(statusItem);
    emitNotificationsMutated();
    expect(bell).toHaveBeenCalledOnce();
    expect(statusItem).toHaveBeenCalledOnce();
    offA(); offB();
  });
});
