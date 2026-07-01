import { useState, useCallback } from 'react';

/**
 * The chapter workspace's primary MODE — the single, obvious "what am I doing to this
 * chapter" switch that replaces the old scatter of Pen/Sparkles, Co-write bridge, and
 * one-off Translate buttons.
 *
 * - write     — the manuscript editor (Tiptap). The classic/AI sub-toggle lives *under*
 *               this mode (it only affects the editor surface).
 * - translate — the in-editor translation workspace (versions, compare, set-active, jobs).
 * - compose   — the AI co-writer studio (the 24-panel LOOM workspace). Left as-is for now;
 *               a dedicated redesign is tracked separately (out of scope here).
 *
 * NOTE: "read" is deliberately NOT a Workmode value. Reading opens the existing full
 * ReaderPage (`/read`) as a route, so it's a navigation action in the switcher, not a
 * persisted in-editor pane. Persisting only the in-page modes keeps reload behaviour sane
 * (you never reload "into" a mode that isn't actually the editor).
 */
export type Workmode = 'write' | 'translate' | 'compose';

const STORAGE_KEY = 'lw_editor_workmode';
const VALID: readonly Workmode[] = ['write', 'translate', 'compose'];

/** Persisted (per-device UI state) chapter workmode. Defaults to `write`. */
export function useWorkmode() {
  const [mode, setModeState] = useState<Workmode>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY) as Workmode | null;
      return stored && VALID.includes(stored) ? stored : 'write';
    } catch {
      return 'write';
    }
  });

  const setMode = useCallback((m: Workmode) => {
    setModeState(m);
    try { localStorage.setItem(STORAGE_KEY, m); } catch { /* ignore */ }
  }, []);

  return [mode, setMode] as const;
}
