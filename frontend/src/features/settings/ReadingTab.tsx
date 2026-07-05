import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAppTheme, useReaderTheme, APP_THEMES, type AppTheme } from '@/providers/ThemeProvider';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';
import { cn } from '@/lib/utils';
import { syncPrefsToServer } from '@/lib/syncPrefs';

type MediaPrefs = {
  ttsModelId: string;
  imageModelId: string;
  videoModelId: string;
  defaultVoice: string;
  defaultImageSize: string;
};

const MEDIA_PREFS_KEY = 'loreweave:media-prefs';
const DEFAULT_MEDIA_PREFS: MediaPrefs = {
  ttsModelId: '',
  imageModelId: '',
  videoModelId: '',
  defaultVoice: 'alloy',
  defaultImageSize: '1024x1024',
};

function loadMediaPrefs(): MediaPrefs {
  try {
    return { ...DEFAULT_MEDIA_PREFS, ...JSON.parse(localStorage.getItem(MEDIA_PREFS_KEY) || '{}') };
  } catch { return DEFAULT_MEDIA_PREFS; }
}
function saveMediaPrefs(prefs: MediaPrefs, token?: string | null) {
  localStorage.setItem(MEDIA_PREFS_KEY, JSON.stringify(prefs));
  syncPrefsToServer('media_prefs', prefs, token);
}

const IMAGE_SIZE_OPTIONS = ['256x256', '512x512', '1024x1024', '1024x1792', '1792x1024'];

const READER_FONTS = [
  { value: "'Lora', Georgia, serif", label: 'Lora', cls: 'font-serif' },
  { value: "'Inter', sans-serif", label: 'Inter', cls: 'font-sans' },
  { value: "'Noto Serif JP', serif", label: 'Noto Serif JP', cls: 'font-serif' },
  { value: "'Noto Serif TC', serif", label: 'Noto Serif TC', cls: 'font-serif' },
  { value: "system-ui, sans-serif", label: 'System', cls: '' },
];

const APP_THEME_COLORS: Record<AppTheme, { bg: string; fg: string; accent: string }> = {
  dark:  { bg: '#181412', fg: '#f5efe8', accent: '#e8a832' },
  light: { bg: '#f7f4ef', fg: '#2a2320', accent: '#c4880a' },
  sepia: { bg: '#ebe0ca', fg: '#3d3020', accent: '#b8891a' },
  oled:  { bg: '#000000', fg: '#cccccc', accent: '#e8a832' },
};

const SPACING_OPTIONS = [
  { value: 0.8, key: 'compact' },
  { value: 1.2, key: 'normal' },
  { value: 1.6, key: 'relaxed' },
];

export function ReadingTab() {
  const { t } = useTranslation('settings');
  const { appTheme, setAppTheme } = useAppTheme();
  const {
    theme: readerTheme, presetName, presets, setPreset,
    setFontSize, setLineHeight, setMaxWidth, setFont,
    setCustomBg, setCustomFg, setSpacing,
    customPresets, saveCustomPreset, deleteCustomPreset, loadCustomPreset,
  } = useReaderTheme();
  const [newPresetName, setNewPresetName] = useState('');
  const { accessToken } = useAuth();

  // AI model prefs
  const [mediaPrefs, setMediaPrefs] = useState(loadMediaPrefs);
  const [ttsModels, setTtsModels] = useState<UserModel[]>([]);
  const [imageModels, setImageModels] = useState<UserModel[]>([]);
  const [videoModels, setVideoModels] = useState<UserModel[]>([]);

  useEffect(() => {
    if (!accessToken) return;
    aiModelsApi.listUserModels(accessToken, { capability: 'tts' }).then(r => setTtsModels(r.items)).catch(() => {});
    aiModelsApi.listUserModels(accessToken, { capability: 'image_gen' }).then(r => setImageModels(r.items)).catch(() => {});
    aiModelsApi.listUserModels(accessToken, { capability: 'video_gen' }).then(r => setVideoModels(r.items)).catch(() => {});
  }, [accessToken]);

  const updateMediaPref = (key: keyof MediaPrefs, value: string) => {
    const next = { ...mediaPrefs, [key]: value };
    setMediaPrefs(next);
    saveMediaPrefs(next, accessToken);
  };

  return (
    <div className="space-y-8">

      {/* ── App Theme ───────────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold">{t('reading.app_theme')}</h2>
        <p className="mb-4 text-xs text-muted-foreground">{t('reading.app_theme_desc')}</p>
        <div className="grid grid-cols-4 gap-3 max-w-lg">
          {APP_THEMES.map((th) => {
            const colors = APP_THEME_COLORS[th.value];
            return (
              <button
                key={th.value}
                onClick={() => setAppTheme(th.value)}
                className={cn(
                  'group flex flex-col items-center gap-2 rounded-lg border p-3 transition-all',
                  appTheme === th.value ? 'border-primary ring-2 ring-primary/30' : 'border-border hover:bg-secondary/50',
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
                <span className="text-[11px] font-medium">{th.label}</span>
              </button>
            );
          })}
        </div>
      </section>

      {/* ── Reader Theme Presets ─────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold">{t('reading.reader_theme')}</h2>
        <p className="mb-4 text-xs text-muted-foreground">{t('reading.reader_theme_desc')}</p>
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

        {/* Custom presets */}
        {customPresets.length > 0 && (
          <div className="mt-3">
            <p className="mb-2 text-[10px] font-medium text-muted-foreground uppercase tracking-wider">{t('reading.custom_presets')}</p>
            <div className="flex flex-wrap gap-2">
              {customPresets.map((cp) => (
                <div key={cp.name} className="group flex items-center gap-1 rounded-lg border px-2 py-1.5 hover:bg-secondary/50 transition-colors">
                  <button onClick={() => loadCustomPreset(cp)} className="flex items-center gap-2">
                    <span className="h-4 w-4 rounded" style={{ background: cp.bg, border: `1px solid ${cp.fg}30` }} />
                    <span className="text-[11px] font-medium">{cp.name}</span>
                  </button>
                  <button
                    onClick={() => deleteCustomPreset(cp.name)}
                    className="opacity-0 group-hover:opacity-100 max-md:opacity-100 ml-1 text-muted-foreground hover:text-destructive transition-all"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* ── Custom Colors ───────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold">{t('reading.custom_colors')}</h2>
        <p className="mb-4 text-xs text-muted-foreground">{t('reading.custom_colors_desc')}</p>
        <div className="flex gap-6 max-w-lg">
          <div className="flex-1">
            <label className="mb-2 block text-xs font-medium">{t('reading.background')}</label>
            <div className="flex items-center gap-3">
              <input
                type="color"
                value={readerTheme.bg}
                onChange={(e) => setCustomBg(e.target.value)}
                className="h-8 w-10 cursor-pointer rounded border bg-transparent"
              />
              <span className="font-mono text-[11px] text-muted-foreground">{readerTheme.bg}</span>
              {readerTheme.bg !== (presets[presetName]?.bg ?? '') && (
                <button onClick={() => setCustomBg('')} className="text-[10px] text-primary hover:underline">{t('reading.reset')}</button>
              )}
            </div>
          </div>
          <div className="flex-1">
            <label className="mb-2 block text-xs font-medium">{t('reading.text')}</label>
            <div className="flex items-center gap-3">
              <input
                type="color"
                value={readerTheme.fg}
                onChange={(e) => setCustomFg(e.target.value)}
                className="h-8 w-10 cursor-pointer rounded border bg-transparent"
              />
              <span className="font-mono text-[11px] text-muted-foreground">{readerTheme.fg}</span>
              {readerTheme.fg !== (presets[presetName]?.fg ?? '') && (
                <button onClick={() => setCustomFg('')} className="text-[10px] text-primary hover:underline">{t('reading.reset')}</button>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ── Reader Typography ───────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold">{t('reading.typography')}</h2>
        <p className="mb-4 text-xs text-muted-foreground">{t('reading.typography_desc')}</p>

        <div className="space-y-5 max-w-lg">
          {/* Font family */}
          <div>
            <label className="mb-2 block text-xs font-medium">{t('reading.font_family')}</label>
            <div className="flex flex-col gap-2">
              {READER_FONTS.map((f) => (
                <button
                  key={f.value}
                  onClick={() => setFont(f.value)}
                  className={cn(
                    'flex items-center justify-between rounded-md border px-4 py-2.5 transition-colors text-left',
                    readerTheme.fontFamily === f.value
                      ? 'border-primary bg-primary/10'
                      : 'hover:bg-secondary',
                  )}
                >
                  <div>
                    <p className={cn('text-[13px] font-medium', f.cls)}>{f.label}</p>
                    <p className={cn('text-[11px] text-muted-foreground mt-0.5', f.cls)} style={{ fontFamily: f.value }}>{t('reading.font_sample')}</p>
                  </div>
                  {readerTheme.fontFamily === f.value && (
                    <span className="h-4 w-4 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
                      <span className="h-1.5 w-1.5 rounded-full bg-primary-foreground" />
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Font size */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium">{t('reading.font_size')}</label>
              <span className="text-xs font-semibold text-primary">{readerTheme.fontSize}px</span>
            </div>
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
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium">{t('reading.line_height')}</label>
              <span className="text-xs font-semibold text-primary">{readerTheme.lineHeight.toFixed(1)}</span>
            </div>
            <input
              type="range" min={1.4} max={2.2} step={0.1}
              value={readerTheme.lineHeight}
              onChange={(e) => setLineHeight(Number(e.target.value))}
              className="w-full accent-primary"
            />
            <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
              <span>{t('reading.spacing_compact')}</span><span>{t('reading.spacing_normal')}</span><span>{t('reading.spacing_relaxed')}</span>
            </div>
          </div>

          {/* Max width */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium">{t('reading.text_width')}</label>
              <span className="text-xs font-semibold text-primary">{readerTheme.maxWidth}px</span>
            </div>
            <input
              type="range" min={480} max={960} step={40}
              value={readerTheme.maxWidth}
              onChange={(e) => setMaxWidth(Number(e.target.value))}
              className="w-full accent-primary"
            />
            <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
              <span>{t('reading.width_narrow')}</span><span>{t('reading.width_medium')}</span><span>{t('reading.width_wide')}</span>
            </div>
          </div>

          {/* Paragraph spacing */}
          <div>
            <label className="mb-2 block text-xs font-medium">{t('reading.paragraph_spacing')}</label>
            <div className="flex gap-1 rounded-md border bg-secondary/50 p-1">
              {SPACING_OPTIONS.map((s) => (
                <button
                  key={s.value}
                  onClick={() => setSpacing(s.value)}
                  className={cn(
                    'flex-1 rounded-md py-1.5 text-[11px] font-medium transition-colors',
                    readerTheme.spacing === s.value
                      ? 'bg-primary/15 text-primary'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {t(`reading.spacing_${s.key}`)}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── Save as Custom Preset ────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold">{t('reading.save_preset')}</h2>
        <p className="mb-3 text-xs text-muted-foreground">{t('reading.save_preset_desc')}</p>
        <div className="flex gap-2 max-w-sm">
          <input
            value={newPresetName}
            onChange={(e) => setNewPresetName(e.target.value)}
            placeholder={t('reading.preset_name_ph')}
            className="flex-1 rounded-md border bg-input px-3 py-1.5 text-xs focus:border-ring focus:outline-none placeholder:text-muted-foreground/50"
          />
          <button
            onClick={() => {
              if (!newPresetName.trim()) return;
              saveCustomPreset(newPresetName.trim());
              toast.success(t('reading.toast.preset_saved', { name: newPresetName.trim() }));
              setNewPresetName('');
            }}
            disabled={!newPresetName.trim()}
            className="rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {t('reading.save')}
          </button>
        </div>
      </section>

      {/* ── AI Models ─────────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold">{t('reading.ai_models')}</h2>
        <p className="mb-4 text-xs text-muted-foreground">
          {t('reading.ai_models_desc')}
        </p>
        <div className="space-y-4 max-w-lg">
          {/* Voice/TTS settings moved to the unified Chat & AI panel (M5 — these
              controls here were dead: nothing consumed media_prefs.ttsModelId /
              defaultVoice for playback). One home for voice now. */}
          <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-[11px] text-muted-foreground">
            {t('reading.voice_moved', { defaultValue: 'Voice & speech settings now live in Settings → Chat & AI → Voice.' })}
          </div>

          {/* Image model */}
          <div>
            <label className="mb-1.5 block text-xs font-medium">{t('reading.image_model')}</label>
            <select
              value={mediaPrefs.imageModelId}
              onChange={e => updateMediaPref('imageModelId', e.target.value)}
              className="w-full rounded-md border bg-input px-3 py-1.5 text-xs focus:border-ring focus:outline-none"
            >
              <option value="">{t('reading.auto_first')}</option>
              {imageModels.map(m => (
                <option key={m.user_model_id} value={m.user_model_id}>
                  {m.alias || m.provider_model_name} ({m.provider_kind})
                </option>
              ))}
            </select>
          </div>

          {/* Default image size */}
          <div>
            <label className="mb-1.5 block text-xs font-medium">{t('reading.default_image_size')}</label>
            <div className="flex flex-wrap gap-1.5">
              {IMAGE_SIZE_OPTIONS.map(s => (
                <button
                  key={s}
                  onClick={() => updateMediaPref('defaultImageSize', s)}
                  className={cn(
                    'rounded-md border px-3 py-1 text-[11px] font-medium transition-colors',
                    mediaPrefs.defaultImageSize === s
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'text-muted-foreground hover:bg-secondary',
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Video model */}
          <div>
            <label className="mb-1.5 block text-xs font-medium">{t('reading.video_model')}</label>
            <select
              value={mediaPrefs.videoModelId}
              onChange={e => updateMediaPref('videoModelId', e.target.value)}
              className="w-full rounded-md border bg-input px-3 py-1.5 text-xs focus:border-ring focus:outline-none"
            >
              <option value="">{t('reading.auto_first')}</option>
              {videoModels.map(m => (
                <option key={m.user_model_id} value={m.user_model_id}>
                  {m.alias || m.provider_model_name} ({m.provider_kind})
                </option>
              ))}
            </select>
          </div>

          {(ttsModels.length === 0 && imageModels.length === 0 && videoModels.length === 0) && (
            <p className="text-[11px] text-muted-foreground/70 italic">
              {t('reading.no_media_models')}
            </p>
          )}
        </div>
      </section>

      {/* ── Live Preview ────────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold">{t('reading.preview')}</h2>
        <p className="mb-3 text-xs text-muted-foreground">{t('reading.preview_desc')}</p>
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
          <p style={{ marginBottom: `${readerTheme.spacing}em` }}>
            {t('reading.preview_p1')}
          </p>
          <p style={{ marginBottom: `${readerTheme.spacing}em` }}>
            {t('reading.preview_p2')}
          </p>
          <p>
            {t('reading.preview_p3')}
          </p>
        </div>
      </section>

      <p className="text-[10px] text-muted-foreground">
        {t('reading.auto_saved')}
      </p>
    </div>
  );
}
