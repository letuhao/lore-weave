import { useAppTheme, useReaderTheme, APP_THEMES, type AppTheme } from '@/providers/ThemeProvider';
import { cn } from '@/lib/utils';

const READER_FONTS = [
  { value: "'Lora', Georgia, serif", label: 'Lora', cls: 'font-serif' },
  { value: "'Inter', sans-serif", label: 'Inter', cls: 'font-sans' },
  { value: "'Noto Serif JP', serif", label: 'Noto Serif JP', cls: 'font-serif' },
  { value: "system-ui, sans-serif", label: 'System', cls: '' },
];

const APP_THEME_COLORS: Record<AppTheme, { bg: string; fg: string; accent: string }> = {
  dark:  { bg: '#181412', fg: '#f5efe8', accent: '#e8a832' },
  light: { bg: '#f7f4ef', fg: '#2a2320', accent: '#c4880a' },
  sepia: { bg: '#ebe0ca', fg: '#3d3020', accent: '#b8891a' },
  oled:  { bg: '#000000', fg: '#cccccc', accent: '#e8a832' },
};

export function ReadingTab() {
  const { appTheme, setAppTheme } = useAppTheme();
  const {
    theme: readerTheme, presetName, presets, setPreset,
    setFontSize, setLineHeight, setMaxWidth, setFont,
  } = useReaderTheme();

  return (
    <div className="space-y-8">

      {/* ── App Theme ───────────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold">App Theme</h2>
        <p className="mb-4 text-xs text-muted-foreground">Changes the appearance of the entire interface.</p>
        <div className="grid grid-cols-4 gap-3 max-w-lg">
          {APP_THEMES.map((t) => {
            const colors = APP_THEME_COLORS[t.value];
            return (
              <button
                key={t.value}
                onClick={() => setAppTheme(t.value)}
                className={cn(
                  'group flex flex-col items-center gap-2 rounded-lg border p-3 transition-all',
                  appTheme === t.value ? 'border-primary ring-2 ring-primary/30' : 'border-border hover:border-border hover:bg-secondary/50',
                )}
              >
                <div
                  className="h-12 w-full rounded-md border"
                  style={{ background: colors.bg, borderColor: colors.fg + '20' }}
                >
                  <div className="flex h-full items-end p-1.5 gap-1">
                    <div className="h-1 w-6 rounded-full" style={{ background: colors.fg + '60' }} />
                    <div className="h-1 w-3 rounded-full" style={{ background: colors.accent }} />
                  </div>
                </div>
                <span className="text-[11px] font-medium">{t.label}</span>
              </button>
            );
          })}
        </div>
      </section>

      {/* ── Reader Theme ────────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold">Reader Theme</h2>
        <p className="mb-4 text-xs text-muted-foreground">Independent theme for the reading view. Can differ from the app theme.</p>
        <div className="grid grid-cols-3 gap-3 max-w-lg sm:grid-cols-6">
          {Object.entries(presets).map(([key, preset]) => (
            <button
              key={key}
              onClick={() => setPreset(key)}
              className={cn(
                'flex flex-col items-center gap-1.5 rounded-lg border p-2 transition-all',
                presetName === key ? 'border-primary ring-2 ring-primary/30' : 'border-border hover:bg-secondary/50',
              )}
            >
              <div
                className="h-8 w-full rounded border"
                style={{ background: preset.bg, borderColor: preset.fg + '20' }}
              >
                <div className="flex h-full items-center justify-center">
                  <span style={{ color: preset.fg, fontSize: 9, fontFamily: preset.fontFamily }}>Aa</span>
                </div>
              </div>
              <span className="text-[9px] font-medium truncate w-full text-center">{preset.name}</span>
            </button>
          ))}
        </div>
      </section>

      {/* ── Reader Typography ───────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold">Reader Typography</h2>
        <p className="mb-4 text-xs text-muted-foreground">Fine-tune the reading experience.</p>

        <div className="space-y-5 max-w-lg">
          {/* Font family */}
          <div>
            <label className="mb-2 block text-xs font-medium">Font Family</label>
            <div className="flex flex-wrap gap-2">
              {READER_FONTS.map((f) => (
                <button
                  key={f.value}
                  onClick={() => setFont(f.value)}
                  className={cn(
                    'rounded-md border px-4 py-2 text-[13px] transition-colors',
                    f.cls,
                    readerTheme.fontFamily === f.value
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'hover:bg-secondary',
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {/* Font size */}
          <div>
            <label className="mb-2 block text-xs font-medium">Font Size: {readerTheme.fontSize}px</label>
            <input
              type="range" min={12} max={28} step={1}
              value={readerTheme.fontSize}
              onChange={(e) => setFontSize(Number(e.target.value))}
              className="w-full accent-primary"
            />
            <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
              <span>12px</span><span>20px</span><span>28px</span>
            </div>
          </div>

          {/* Line height */}
          <div>
            <label className="mb-2 block text-xs font-medium">Line Height: {readerTheme.lineHeight.toFixed(1)}</label>
            <input
              type="range" min={1.4} max={2.2} step={0.1}
              value={readerTheme.lineHeight}
              onChange={(e) => setLineHeight(Number(e.target.value))}
              className="w-full accent-primary"
            />
            <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
              <span>Compact</span><span>Normal</span><span>Relaxed</span>
            </div>
          </div>

          {/* Max width */}
          <div>
            <label className="mb-2 block text-xs font-medium">Text Width: {readerTheme.maxWidth}px</label>
            <input
              type="range" min={480} max={960} step={40}
              value={readerTheme.maxWidth}
              onChange={(e) => setMaxWidth(Number(e.target.value))}
              className="w-full accent-primary"
            />
            <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
              <span>Narrow</span><span>Medium</span><span>Wide</span>
            </div>
          </div>
        </div>
      </section>

      {/* ── Live Preview ────────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold">Preview</h2>
        <p className="mb-3 text-xs text-muted-foreground">How your reader content will look.</p>
        <div
          className="overflow-hidden rounded-lg border"
          style={{
            background: readerTheme.bg,
            color: readerTheme.fg,
            fontFamily: readerTheme.fontFamily,
            fontSize: readerTheme.fontSize,
            lineHeight: readerTheme.lineHeight,
            maxWidth: readerTheme.maxWidth,
            padding: '24px 28px',
          }}
        >
          <p style={{ marginBottom: '0.8em' }}>
            The throne room was silent save for the quiet crackling of magical torches. The Demon Lord sat cross-legged, examining a scroll detailing the latest territorial dispute with the neighboring kingdom of Aerolia.
          </p>
          <p>
            "Your Majesty," the aide said, bowing deeply. "The envoy from the Eastern Province has arrived. They bring... unusual terms."
          </p>
        </div>
      </section>

      <p className="text-[10px] text-muted-foreground">
        Changes are saved automatically.
      </p>
    </div>
  );
}
