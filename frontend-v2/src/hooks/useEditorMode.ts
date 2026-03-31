import { useState, useCallback } from 'react';

export type EditorMode = 'classic' | 'ai';

const STORAGE_KEY = 'lw_editor_mode';

/**
 * Persisted editor mode toggle.
 * - Classic: text-only editing, media blocks locked, minimal slash menu
 * - AI Assistant: full features, all block types, AI prompts on media
 */
export function useEditorMode() {
  const [mode, setModeState] = useState<EditorMode>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === 'ai' ? 'ai' : 'classic';
  });

  const setMode = useCallback((m: EditorMode) => {
    setModeState(m);
    localStorage.setItem(STORAGE_KEY, m);
  }, []);

  return [mode, setMode] as const;
}
