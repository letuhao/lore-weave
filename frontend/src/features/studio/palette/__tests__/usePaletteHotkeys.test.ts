import { describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { usePaletteHotkeys } from '../usePaletteHotkeys';

function press(init: KeyboardEventInit) {
  window.dispatchEvent(new KeyboardEvent('keydown', { ...init, bubbles: true, cancelable: true }));
}

describe('usePaletteHotkeys', () => {
  it('Ctrl/⌘+P opens Quick Open; +Shift opens Command Palette', () => {
    const onOpen = vi.fn();
    renderHook(() => usePaletteHotkeys(onOpen));
    press({ key: 'p', ctrlKey: true });
    expect(onOpen).toHaveBeenLastCalledWith('quick');
    press({ key: 'P', metaKey: true, shiftKey: true });
    expect(onOpen).toHaveBeenLastCalledWith('command');
  });

  it('ignores plain P and modifier combos with Alt', () => {
    const onOpen = vi.fn();
    renderHook(() => usePaletteHotkeys(onOpen));
    press({ key: 'p' });                    // no modifier
    press({ key: 'p', ctrlKey: true, altKey: true }); // alt excluded
    expect(onOpen).not.toHaveBeenCalled();
  });

  it('unsubscribes on unmount', () => {
    const onOpen = vi.fn();
    const { unmount } = renderHook(() => usePaletteHotkeys(onOpen));
    unmount();
    press({ key: 'p', ctrlKey: true });
    expect(onOpen).not.toHaveBeenCalled();
  });
});
