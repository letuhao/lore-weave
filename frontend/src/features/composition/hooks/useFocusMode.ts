// LOOM Composition (T5.1) — focus/typewriter mode toggle. Per-device UI state
// (localStorage, allowed by CLAUDE.md for per-device prefs); survives chapter
// navigation + reload. The visual behavior (hide panels, dim non-current
// paragraphs, typewriter scroll) is driven by the boolean + CSS in the consumers.
import { useCallback, useState } from 'react';

const KEY = 'loreweave.editor.focusMode';

function read(): boolean {
  try { return localStorage.getItem(KEY) === '1'; } catch { return false; }
}

export function useFocusMode() {
  const [focusMode, setFocus] = useState<boolean>(read);

  const setFocusMode = useCallback((on: boolean) => {
    setFocus(on);
    try { localStorage.setItem(KEY, on ? '1' : '0'); } catch { /* private mode */ }
  }, []);

  const toggle = useCallback(() => setFocusMode(!read()), [setFocusMode]);

  return { focusMode, setFocusMode, toggle };
}
