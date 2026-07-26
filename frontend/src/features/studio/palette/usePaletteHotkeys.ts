import { useEffect } from 'react';

export type PaletteKind = 'quick' | 'command';

/**
 * Global ⌘P / Ctrl+P → Quick Open, ⌘⇧P / Ctrl+Shift+P → Command Palette. Registered on window
 * in the CAPTURE phase so a focused dock panel (editor, etc.) can't swallow the shortcut before
 * the studio sees it. `onOpen` is called with the palette to open; the caller toggles state.
 */
export function usePaletteHotkeys(onOpen: (kind: PaletteKind) => void): void {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod || e.altKey) return;
      if (e.key.toLowerCase() === 'p') {
        e.preventDefault();
        e.stopPropagation();
        onOpen(e.shiftKey ? 'command' : 'quick');
      }
    };
    window.addEventListener('keydown', handler, true);
    return () => window.removeEventListener('keydown', handler, true);
  }, [onOpen]);
}
