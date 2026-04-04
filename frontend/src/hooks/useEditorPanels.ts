import { useState, useCallback } from 'react';

type PanelState = { left: boolean; right: boolean; leftWidth: number; rightWidth: number };

const STORAGE_KEY = 'lw_editor_panels';

function readState(): PanelState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : { left: false, right: true, leftWidth: 300, rightWidth: 320 };
  } catch {
    return { left: false, right: true, leftWidth: 300, rightWidth: 320 };
  }
}

export function useEditorPanels() {
  const [state, setState] = useState<PanelState>(readState);

  const save = (s: PanelState) => {
    setState(s);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  };

  const toggleLeft = useCallback(() => save({ ...state, left: !state.left }), [state]);
  const toggleRight = useCallback(() => save({ ...state, right: !state.right }), [state]);

  return { ...state, toggleLeft, toggleRight };
}
