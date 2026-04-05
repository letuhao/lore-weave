import { X } from 'lucide-react';
import { useReaderTheme } from '@/providers/ThemeProvider';
import { cn } from '@/lib/utils';

interface ThemeCustomizerProps {
  open: boolean;
  onClose: () => void;
  showIndices: boolean;
  onShowIndicesChange: (v: boolean) => void;
}

const PRESET_DESCRIPTIONS: Record<string, string> = {
  dark: 'Warm dark background',
  light: 'Clean white background',
  sepia: 'Warm paper tone',
  oled: 'True black for OLED screens',
  parchment: 'Classic parchment feel',
  forest: 'Easy on the eyes at night',
};

const FONT_OPTIONS: { family: string; label: string; sample: string }[] = [
  { family: "'Lora', Georgia, serif", label: 'Lora', sample: 'The quick brown fox' },
  { family: "'Merriweather', serif", label: 'Merriweather', sample: 'The quick brown fox' },
  { family: "'Source Serif 4', Georgia, serif", label: 'Source Serif 4', sample: 'The quick brown fox' },
  { family: "'Inter', sans-serif", label: 'Inter', sample: 'The quick brown fox' },
  { family: "'Noto Serif JP', serif", label: 'Noto Serif JP', sample: '素早い茶色の狐' },
];

export function ThemeCustomizer({ open, onClose, showIndices, onShowIndicesChange }: ThemeCustomizerProps) {
  const {
    theme, presetName, presets, setPreset,
    setFont, setFontSize, setLineHeight, setMaxWidth, setSpacing,
  } = useReaderTheme();

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-30" onClick={onClose} />

      {/* Panel */}
      <div className="fixed top-0 right-0 bottom-0 z-[31] w-[340px] border-l bg-card shadow-xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-4 py-3">
          <span className="text-sm font-semibold">Reading Theme</span>
          <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">

          {/* Theme presets */}
          <section>
            <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Theme Presets</h3>
            <div className="flex flex-col gap-1">
              {Object.entries(presets).map(([key, preset]) => (
                <button
                  key={key}
                  onClick={() => setPreset(key)}
                  className={cn(
                    'flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-all',
                    presetName === key
                      ? 'border border-primary bg-primary/10'
                      : 'border border-transparent hover:bg-secondary',
                  )}
                >
                  <div
                    className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md border text-[9px] font-semibold"
                    style={{ background: preset.bg, color: preset.fg }}
                  >
                    Aa
                  </div>
                  <div>
                    <div className="text-xs font-medium">{preset.name}</div>
                    <div className="text-[10px] text-muted-foreground">{PRESET_DESCRIPTIONS[key] ?? ''}</div>
                  </div>
                </button>
              ))}
            </div>
          </section>

          {/* Font */}
          <section>
            <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Font</h3>
            <div className="flex flex-col gap-0.5">
              {FONT_OPTIONS.map((opt) => (
                <button
                  key={opt.label}
                  onClick={() => setFont(opt.family)}
                  className={cn(
                    'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left transition-all',
                    theme.fontFamily === opt.family
                      ? 'border border-primary bg-primary/10'
                      : 'border border-transparent hover:bg-secondary',
                  )}
                >
                  <span className="w-[120px] text-sm" style={{ fontFamily: opt.family }}>{opt.sample}</span>
                  <span className="text-[10px] text-muted-foreground">{opt.label}</span>
                </button>
              ))}
            </div>
          </section>

          {/* Typography sliders */}
          <section>
            <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Typography</h3>
            <div className="space-y-2">
              <SliderRow
                label="Font size"
                min={12} max={28} step={1}
                value={theme.fontSize}
                display={`${theme.fontSize}px`}
                onChange={setFontSize}
              />
              <SliderRow
                label="Line height"
                min={1.4} max={2.2} step={0.05}
                value={theme.lineHeight}
                display={theme.lineHeight.toFixed(2)}
                onChange={setLineHeight}
              />
              <SliderRow
                label="Text width"
                min={480} max={960} step={20}
                value={theme.maxWidth}
                display={`${theme.maxWidth}px`}
                onChange={setMaxWidth}
              />
              <SliderRow
                label="Spacing"
                min={0.8} max={2.0} step={0.1}
                value={theme.spacing ?? 1.2}
                display={`${(theme.spacing ?? 1.2).toFixed(1)}em`}
                onChange={setSpacing}
              />
            </div>
          </section>

          {/* Reading mode */}
          <section>
            <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Reading Mode</h3>
            <div className="flex flex-col gap-2">
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  checked={showIndices}
                  onChange={(e) => onShowIndicesChange(e.target.checked)}
                  className="accent-primary"
                />
                Show block indices (translator mode)
              </label>
              <label className="flex items-center gap-2 text-xs cursor-pointer opacity-50">
                <input type="checkbox" disabled className="accent-primary" />
                Auto-load next chapter (coming soon)
              </label>
              <label className="flex items-center gap-2 text-xs cursor-pointer opacity-50">
                <input type="checkbox" disabled className="accent-primary" />
                Auto-scroll with TTS (coming soon)
              </label>
            </div>
          </section>
        </div>
      </div>
    </>
  );
}

function SliderRow({
  label, min, max, step, value, display, onChange,
}: {
  label: string; min: number; max: number; step: number;
  value: number; display: string; onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="w-[76px] flex-shrink-0 text-[11px] text-muted-foreground">{label}</span>
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-secondary accent-primary"
      />
      <span className="w-[44px] flex-shrink-0 text-right font-mono text-[10px] text-muted-foreground">{display}</span>
    </div>
  );
}
