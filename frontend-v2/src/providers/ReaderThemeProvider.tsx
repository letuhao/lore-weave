import { createContext, useContext, useState, useCallback, useMemo, type ReactNode } from 'react';

export type ReaderTheme = {
  name: string;
  bg: string;
  fg: string;
  fontFamily: string;
  fontSize: number;
  lineHeight: number;
  maxWidth: number;
};

const PRESETS: Record<string, ReaderTheme> = {
  dark:      { name: 'Dark',      bg: '#181412', fg: '#f5efe8', fontFamily: "'Lora', Georgia, serif", fontSize: 17, lineHeight: 1.85, maxWidth: 680 },
  sepia:     { name: 'Sepia',     bg: '#f4ecd8', fg: '#5b4636', fontFamily: "'Lora', Georgia, serif", fontSize: 17, lineHeight: 1.85, maxWidth: 680 },
  light:     { name: 'Light',     bg: '#ffffff', fg: '#1a1a1a', fontFamily: "'Inter', sans-serif",     fontSize: 16, lineHeight: 1.75, maxWidth: 680 },
  oled:      { name: 'OLED',      bg: '#000000', fg: '#cccccc', fontFamily: "system-ui, sans-serif",   fontSize: 16, lineHeight: 1.8,  maxWidth: 680 },
  parchment: { name: 'Parchment', bg: '#e8dcc8', fg: '#3d3020', fontFamily: "'Noto Serif JP', serif",  fontSize: 17, lineHeight: 1.9,  maxWidth: 680 },
  forest:    { name: 'Forest',    bg: '#1a2418', fg: '#c8d8c0', fontFamily: "'Lora', Georgia, serif",  fontSize: 17, lineHeight: 1.85, maxWidth: 680 },
};

const STORAGE_KEY = 'lw_reader_theme';

type ReaderThemeCtx = {
  theme: ReaderTheme;
  presetName: string;
  presets: typeof PRESETS;
  setPreset: (name: string) => void;
  setFontSize: (size: number) => void;
  setLineHeight: (lh: number) => void;
  setMaxWidth: (w: number) => void;
  cssVars: Record<string, string>;
};

const Ctx = createContext<ReaderThemeCtx | null>(null);

function loadTheme(): { presetName: string; overrides: Partial<ReaderTheme> } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : { presetName: 'dark', overrides: {} };
  } catch {
    return { presetName: 'dark', overrides: {} };
  }
}

export function ReaderThemeProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(loadTheme);

  const save = (s: typeof state) => {
    setState(s);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  };

  const theme: ReaderTheme = { ...(PRESETS[state.presetName] ?? PRESETS.dark), ...state.overrides };

  const setPreset = useCallback((name: string) => save({ presetName: name, overrides: {} }), []);
  const setFontSize = useCallback((fontSize: number) => save({ ...state, overrides: { ...state.overrides, fontSize } }), [state]);
  const setLineHeight = useCallback((lineHeight: number) => save({ ...state, overrides: { ...state.overrides, lineHeight } }), [state]);
  const setMaxWidth = useCallback((maxWidth: number) => save({ ...state, overrides: { ...state.overrides, maxWidth } }), [state]);

  const cssVars = useMemo(() => ({
    '--reader-bg': theme.bg,
    '--reader-fg': theme.fg,
    '--reader-font': theme.fontFamily,
    '--reader-size': `${theme.fontSize}px`,
    '--reader-line': `${theme.lineHeight}`,
    '--reader-width': `${theme.maxWidth}px`,
  }), [theme]);

  const value = useMemo(() => ({
    theme, presetName: state.presetName, presets: PRESETS, setPreset, setFontSize, setLineHeight, setMaxWidth, cssVars,
  }), [theme, state.presetName, cssVars]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useReaderTheme() {
  const x = useContext(Ctx);
  if (!x) throw new Error('useReaderTheme outside provider');
  return x;
}

export { PRESETS as READER_PRESETS };
