import { createContext, useContext, useState, useCallback, useMemo, useEffect, type ReactNode } from 'react';
import { apiJson } from '@/api';

// ── App themes (switch entire UI via data-theme on <html>) ──────────────────

export type AppTheme = 'dark' | 'light' | 'sepia' | 'oled';
export const APP_THEMES: { value: AppTheme; label: string }[] = [
  { value: 'dark', label: 'Dark' },
  { value: 'light', label: 'Light' },
  { value: 'sepia', label: 'Sepia' },
  { value: 'oled', label: 'OLED' },
];

// ── Reader presets (independent from app theme) ─────────────────────────────

export type ReaderTheme = {
  name: string;
  bg: string;
  fg: string;
  fontFamily: string;
  fontSize: number;
  lineHeight: number;
  maxWidth: number;
};

export const READER_PRESETS: Record<string, ReaderTheme> = {
  dark:      { name: 'Dark',      bg: '#181412', fg: '#f5efe8', fontFamily: "'Lora', Georgia, serif", fontSize: 17, lineHeight: 1.85, maxWidth: 680 },
  sepia:     { name: 'Sepia',     bg: '#f4ecd8', fg: '#5b4636', fontFamily: "'Lora', Georgia, serif", fontSize: 17, lineHeight: 1.85, maxWidth: 680 },
  light:     { name: 'Light',     bg: '#ffffff', fg: '#1a1a1a', fontFamily: "'Inter', sans-serif",     fontSize: 16, lineHeight: 1.75, maxWidth: 680 },
  oled:      { name: 'OLED',      bg: '#000000', fg: '#cccccc', fontFamily: "system-ui, sans-serif",   fontSize: 16, lineHeight: 1.8,  maxWidth: 680 },
  parchment: { name: 'Parchment', bg: '#e8dcc8', fg: '#3d3020', fontFamily: "'Noto Serif JP', serif",  fontSize: 17, lineHeight: 1.9,  maxWidth: 680 },
  forest:    { name: 'Forest',    bg: '#1a2418', fg: '#c8d8c0', fontFamily: "'Lora', Georgia, serif",  fontSize: 17, lineHeight: 1.85, maxWidth: 680 },
};

// ── Preferences shape (matches BE user_preferences.prefs JSONB) ─────────────

export type CustomPreset = {
  name: string;
  bg: string;
  fg: string;
  fontFamily: string;
  fontSize: number;
  lineHeight: number;
  maxWidth: number;
  spacing: number;
};

type ThemePrefs = {
  app_theme: AppTheme;
  reader_preset: string;
  reader_font: string;
  reader_font_size: number;
  reader_line_height: number;
  reader_max_width: number;
  reader_bg_custom: string;
  reader_fg_custom: string;
  reader_spacing: number;
  custom_presets: CustomPreset[];
};

const DEFAULTS: ThemePrefs = {
  app_theme: 'dark',
  reader_preset: 'dark',
  reader_font: "'Lora', Georgia, serif",
  reader_font_size: 17,
  reader_line_height: 1.85,
  reader_max_width: 680,
  reader_bg_custom: '',
  reader_fg_custom: '',
  reader_spacing: 1.2,
  custom_presets: [],
};

const LOCAL_KEY = 'lw_theme_prefs';

// ── Context ─────────────────────────────────────────────────────────────────

type ThemeCtx = {
  // App theme
  appTheme: AppTheme;
  setAppTheme: (t: AppTheme) => void;
  // Reader theme
  readerTheme: ReaderTheme & { spacing: number };
  readerPresetName: string;
  readerPresets: typeof READER_PRESETS;
  setReaderPreset: (name: string) => void;
  setReaderFontSize: (s: number) => void;
  setReaderLineHeight: (lh: number) => void;
  setReaderMaxWidth: (w: number) => void;
  setReaderFont: (f: string) => void;
  setReaderCustomBg: (c: string) => void;
  setReaderCustomFg: (c: string) => void;
  setReaderSpacing: (s: number) => void;
  readerCssVars: Record<string, string>;
  // Custom presets
  customPresets: CustomPreset[];
  saveCustomPreset: (name: string) => void;
  deleteCustomPreset: (name: string) => void;
  loadCustomPreset: (preset: CustomPreset) => void;
};

const Ctx = createContext<ThemeCtx | null>(null);

// ── Load from localStorage (fast, synchronous) ─────────────────────────────

function loadLocal(): ThemePrefs {
  try {
    const raw = localStorage.getItem(LOCAL_KEY);
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) };

    // Migration: read old keys
    const oldReader = localStorage.getItem('lw_reader_theme');
    const oldReading = localStorage.getItem('lw_reading_prefs');
    const migrated = { ...DEFAULTS };
    if (oldReader) {
      try {
        const r = JSON.parse(oldReader);
        if (r.presetName) migrated.reader_preset = r.presetName;
      } catch { /* ignore */ }
    }
    if (oldReading) {
      try {
        const r = JSON.parse(oldReading);
        if (r.fontSize) migrated.reader_font_size = r.fontSize;
        if (r.lineSpacing) migrated.reader_line_height = r.lineSpacing;
        if (r.theme === 'sepia') migrated.app_theme = 'sepia';
      } catch { /* ignore */ }
    }
    return migrated;
  } catch {
    return DEFAULTS;
  }
}

function saveLocal(prefs: ThemePrefs) {
  localStorage.setItem(LOCAL_KEY, JSON.stringify(prefs));
}

// ── Provider ────────────────────────────────────────────────────────────────

export function ThemeProvider({ children, accessToken }: { children: ReactNode; accessToken?: string | null }) {
  const [prefs, setPrefs] = useState<ThemePrefs>(loadLocal);
  const [apiLoaded, setApiLoaded] = useState(false);

  // Apply app theme to <html> element
  useEffect(() => {
    if (prefs.app_theme === 'dark') {
      document.documentElement.removeAttribute('data-theme');
    } else {
      document.documentElement.setAttribute('data-theme', prefs.app_theme);
    }
  }, [prefs.app_theme]);

  // Load from API on mount (if authenticated)
  useEffect(() => {
    if (!accessToken || apiLoaded) return;
    apiJson<{ prefs: Partial<ThemePrefs> }>('/v1/me/preferences', { token: accessToken })
      .then((res) => {
        if (res.prefs && Object.keys(res.prefs).length > 0) {
          const merged = { ...prefs, ...res.prefs };
          setPrefs(merged);
          saveLocal(merged);
        }
        setApiLoaded(true);
      })
      .catch(() => setApiLoaded(true));
  }, [accessToken]);

  // Persist to API (debounced via effect)
  const saveToApi = useCallback((next: ThemePrefs) => {
    saveLocal(next);
    if (accessToken) {
      apiJson('/v1/me/preferences', {
        method: 'PATCH',
        token: accessToken,
        body: JSON.stringify({ prefs: next }),
      }).catch(() => { /* silent — localStorage is fallback */ });
    }
  }, [accessToken]);

  const update = useCallback((partial: Partial<ThemePrefs>) => {
    setPrefs((prev) => {
      const next = { ...prev, ...partial };
      saveToApi(next);
      return next;
    });
  }, [saveToApi]);

  // Reader theme computed from preset + overrides + custom colors
  const readerTheme = useMemo(() => {
    const base = READER_PRESETS[prefs.reader_preset] ?? READER_PRESETS.dark;
    return {
      ...base,
      bg: prefs.reader_bg_custom || base.bg,
      fg: prefs.reader_fg_custom || base.fg,
      fontFamily: prefs.reader_font || base.fontFamily,
      fontSize: prefs.reader_font_size || base.fontSize,
      lineHeight: prefs.reader_line_height || base.lineHeight,
      maxWidth: prefs.reader_max_width || base.maxWidth,
      spacing: prefs.reader_spacing || 1.2,
    };
  }, [prefs.reader_preset, prefs.reader_font, prefs.reader_font_size, prefs.reader_line_height, prefs.reader_max_width, prefs.reader_bg_custom, prefs.reader_fg_custom, prefs.reader_spacing]);

  const readerCssVars = useMemo(() => ({
    '--reader-bg': readerTheme.bg,
    '--reader-fg': readerTheme.fg,
    '--reader-font': readerTheme.fontFamily,
    '--reader-size': `${readerTheme.fontSize}px`,
    '--reader-line': `${readerTheme.lineHeight}`,
    '--reader-width': `${readerTheme.maxWidth}px`,
    '--reader-spacing': `${readerTheme.spacing}em`,
  }), [readerTheme]);

  const value = useMemo<ThemeCtx>(() => ({
    appTheme: prefs.app_theme,
    setAppTheme: (t) => update({ app_theme: t }),
    readerTheme,
    readerPresetName: prefs.reader_preset,
    readerPresets: READER_PRESETS,
    setReaderPreset: (name) => {
      const p = READER_PRESETS[name];
      if (p) update({ reader_preset: name, reader_font: p.fontFamily, reader_font_size: p.fontSize, reader_line_height: p.lineHeight, reader_max_width: p.maxWidth, reader_bg_custom: '', reader_fg_custom: '' });
    },
    setReaderFontSize: (s) => update({ reader_font_size: s }),
    setReaderLineHeight: (lh) => update({ reader_line_height: lh }),
    setReaderMaxWidth: (w) => update({ reader_max_width: w }),
    setReaderFont: (f) => update({ reader_font: f }),
    setReaderCustomBg: (c) => update({ reader_bg_custom: c }),
    setReaderCustomFg: (c) => update({ reader_fg_custom: c }),
    setReaderSpacing: (s) => update({ reader_spacing: s }),
    readerCssVars,
    customPresets: prefs.custom_presets || [],
    saveCustomPreset: (name) => {
      const preset: CustomPreset = { name, bg: readerTheme.bg, fg: readerTheme.fg, fontFamily: readerTheme.fontFamily, fontSize: readerTheme.fontSize, lineHeight: readerTheme.lineHeight, maxWidth: readerTheme.maxWidth, spacing: readerTheme.spacing };
      const existing = (prefs.custom_presets || []).filter((p) => p.name !== name);
      update({ custom_presets: [...existing, preset] });
    },
    deleteCustomPreset: (name) => {
      update({ custom_presets: (prefs.custom_presets || []).filter((p) => p.name !== name) });
    },
    loadCustomPreset: (preset) => {
      update({ reader_bg_custom: preset.bg, reader_fg_custom: preset.fg, reader_font: preset.fontFamily, reader_font_size: preset.fontSize, reader_line_height: preset.lineHeight, reader_max_width: preset.maxWidth, reader_spacing: preset.spacing });
    },
  }), [prefs, readerTheme, readerCssVars, update]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

// ── Hooks ───────────────────────────────────────────────────────────────────

export function useAppTheme() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useAppTheme outside ThemeProvider');
  return { appTheme: ctx.appTheme, setAppTheme: ctx.setAppTheme, themes: APP_THEMES };
}

export function useReaderTheme() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useReaderTheme outside ThemeProvider');
  return {
    theme: ctx.readerTheme,
    presetName: ctx.readerPresetName,
    presets: ctx.readerPresets,
    setPreset: ctx.setReaderPreset,
    setFontSize: ctx.setReaderFontSize,
    setLineHeight: ctx.setReaderLineHeight,
    setMaxWidth: ctx.setReaderMaxWidth,
    setFont: ctx.setReaderFont,
    setCustomBg: ctx.setReaderCustomBg,
    setCustomFg: ctx.setReaderCustomFg,
    setSpacing: ctx.setReaderSpacing,
    cssVars: ctx.readerCssVars,
    customPresets: ctx.customPresets,
    saveCustomPreset: ctx.saveCustomPreset,
    deleteCustomPreset: ctx.deleteCustomPreset,
    loadCustomPreset: ctx.loadCustomPreset,
  };
}
