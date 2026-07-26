import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useReaderTheme } from '@/providers/ThemeProvider';
import { cn } from '@/lib/utils';

interface ThemeCustomizerProps {
  open: boolean;
  onClose: () => void;
  showIndices: boolean;
  onShowIndicesChange: (v: boolean) => void;
  autoNext: boolean;
  onAutoNextChange: (v: boolean) => void;
  autoScrollTTS: boolean;
  onAutoScrollTTSChange: (v: boolean) => void;
}

const FONT_OPTIONS: { family: string; label: string; sample: string }[] = [
  { family: "'Lora', Georgia, serif", label: 'Lora', sample: 'The quick brown fox' },
  { family: "'Merriweather', serif", label: 'Merriweather', sample: 'The quick brown fox' },
  { family: "'Source Serif 4', Georgia, serif", label: 'Source Serif 4', sample: 'The quick brown fox' },
  { family: "'Inter', sans-serif", label: 'Inter', sample: 'The quick brown fox' },
  { family: "'Noto Serif JP', serif", label: 'Noto Serif JP', sample: '素早い茶色の狐' },
];

export function ThemeCustomizer({
  open, onClose, showIndices, onShowIndicesChange,
  autoNext, onAutoNextChange, autoScrollTTS, onAutoScrollTTSChange,
}: ThemeCustomizerProps) {
  const { t } = useTranslation('reader');
  const {
    theme, presetName, presets, setPreset,
    setFont, setFontSize, setLineHeight, setMaxWidth, setSpacing,
  } = useReaderTheme();

  if (!open) return null;

  return (
    <>
      {/* Backdrop — D-READER-RESPONSIVE: `absolute`, see TOCSidebar for why (panel-scoped,
          not window-scoped, when reused inside BookReaderPanel's dock panel). */}
      <div className="absolute inset-0 z-30" onClick={onClose} />

      {/* Panel */}
      <div className="absolute top-0 right-0 bottom-0 z-[31] w-[340px] max-w-full border-l bg-card shadow-xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-4 py-3">
          <span className="text-sm font-semibold">{t('theme.title')}</span>
          <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">

          {/* Theme presets */}
          <section>
            <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t('theme.presets')}</h3>
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
                    <div className="text-xs font-medium">{t(`theme.preset.${key}.name`, { defaultValue: preset.name })}</div>
                    <div className="text-[10px] text-muted-foreground">{t(`theme.preset.${key}.desc`, { defaultValue: '' })}</div>
                  </div>
                </button>
              ))}
            </div>
          </section>

          {/* Font */}
          <section>
            <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t('theme.font')}</h3>
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
            <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t('theme.typography')}</h3>
            <div className="space-y-2">
              <SliderRow
                label={t('theme.font_size')}
                min={12} max={28} step={1}
                value={theme.fontSize}
                display={`${theme.fontSize}px`}
                onChange={setFontSize}
              />
              <SliderRow
                label={t('theme.line_height')}
                min={1.4} max={2.2} step={0.05}
                value={theme.lineHeight}
                display={theme.lineHeight.toFixed(2)}
                onChange={setLineHeight}
              />
              <SliderRow
                label={t('theme.text_width')}
                min={480} max={960} step={20}
                value={theme.maxWidth}
                display={`${theme.maxWidth}px`}
                onChange={setMaxWidth}
              />
              <SliderRow
                label={t('theme.spacing')}
                min={0.8} max={2.0} step={0.1}
                value={theme.spacing ?? 1.2}
                display={`${(theme.spacing ?? 1.2).toFixed(1)}em`}
                onChange={setSpacing}
              />
            </div>
          </section>

          {/* Reading mode */}
          <section>
            <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t('theme.reading_mode')}</h3>
            <div className="flex flex-col gap-2">
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  checked={showIndices}
                  onChange={(e) => onShowIndicesChange(e.target.checked)}
                  className="accent-primary"
                />
                {t('theme.show_indices')}
              </label>
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoNext}
                  onChange={(e) => onAutoNextChange(e.target.checked)}
                  className="accent-primary"
                />
                {t('theme.auto_next')}
              </label>
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoScrollTTS}
                  onChange={(e) => onAutoScrollTTSChange(e.target.checked)}
                  className="accent-primary"
                />
                {t('theme.auto_scroll')}
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
