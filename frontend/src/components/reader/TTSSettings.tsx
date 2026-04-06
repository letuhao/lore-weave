import { useState, useEffect } from 'react';
import { X, Settings } from 'lucide-react';
import { useTTSState, useTTSControls } from '@/hooks/useTTS';
import { BrowserTTSEngine } from '@/hooks/engines/BrowserTTSEngine';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';
import { useAuth } from '@/auth';
import { cn } from '@/lib/utils';

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];
const LS_KEY = 'lw_tts_prefs';

export interface TTSPrefs {
  speed: number;
  voiceURI: string | null;
  autoScroll: boolean;
  highlight: boolean;
  /** User model ID for AI TTS generation */
  ttsModelId: string | null;
  /** Voice name for AI TTS (e.g. 'alloy', 'nova') */
  ttsVoice: string;
}

function loadPrefs(): TTSPrefs {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) return { ...defaultPrefs, ...JSON.parse(raw) };
  } catch { /* ignore */ }
  return defaultPrefs;
}

function savePrefs(prefs: TTSPrefs) {
  localStorage.setItem(LS_KEY, JSON.stringify(prefs));
}

const defaultPrefs: TTSPrefs = {
  speed: 1,
  voiceURI: null,
  autoScroll: true,
  highlight: true,
  ttsModelId: null,
  ttsVoice: 'alloy',
};

interface TTSSettingsProps {
  open: boolean;
  onClose: () => void;
}

export function TTSSettings({ open, onClose }: TTSSettingsProps) {
  const state = useTTSState();
  const controls = useTTSControls();
  const { accessToken } = useAuth();
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [models, setModels] = useState<UserModel[]>([]);
  const [prefs, setPrefs] = useState<TTSPrefs>(loadPrefs);

  // Load AI models
  useEffect(() => {
    if (!accessToken) return;
    aiModelsApi.listUserModels(accessToken).then((r) => setModels(r.items)).catch(() => {});
  }, [accessToken]);

  // Load browser voices
  useEffect(() => {
    BrowserTTSEngine.waitForVoices().then(setVoices);
  }, []);

  // Apply saved prefs once on first open
  const [prefsApplied, setPrefsApplied] = useState(false);
  useEffect(() => {
    if (prefsApplied || !open) return;
    setPrefsApplied(true);
    // Defer to avoid triggering store update during render cycle
    const timer = setTimeout(() => {
      const p = loadPrefs();
      controls.setSpeed(p.speed);
      if (p.voiceURI && voices.length > 0) {
        const voice = voices.find((v) => v.voiceURI === p.voiceURI) || null;
        controls.setVoice(voice);
      }
    }, 0);
    return () => clearTimeout(timer);
  }, [open, prefsApplied, voices, controls]);

  const updatePref = <K extends keyof TTSPrefs>(key: K, value: TTSPrefs[K]) => {
    const next = { ...prefs, [key]: value };
    setPrefs(next);
    savePrefs(next);

    if (key === 'speed') controls.setSpeed(value as number);
    if (key === 'voiceURI') {
      const voice = voices.find((v) => v.voiceURI === value) || null;
      controls.setVoice(voice);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-40 flex w-72 flex-col border-l bg-card shadow-xl">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Settings className="h-4 w-4" />
          TTS Settings
        </div>
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {/* Speed */}
        <div>
          <label className="mb-2 block text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Speed
          </label>
          <div className="flex gap-1">
            {SPEEDS.map((s) => (
              <button
                key={s}
                onClick={() => updatePref('speed', s)}
                className={cn(
                  'flex-1 rounded-md py-1.5 text-[11px] font-medium transition',
                  prefs.speed === s
                    ? 'bg-primary/15 text-primary'
                    : 'bg-secondary text-muted-foreground hover:text-foreground',
                )}
              >
                {s}x
              </button>
            ))}
          </div>
        </div>

        {/* Browser Voice */}
        <div>
          <label className="mb-2 block text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Browser Voice
          </label>
          <select
            value={prefs.voiceURI || ''}
            onChange={(e) => updatePref('voiceURI', e.target.value || null)}
            className="w-full rounded-md border bg-background px-2 py-1.5 text-xs text-foreground outline-none"
          >
            <option value="">Default</option>
            {voices.map((v) => (
              <option key={v.voiceURI} value={v.voiceURI}>
                {v.name} ({v.lang})
              </option>
            ))}
          </select>
          {voices.length === 0 && (
            <p className="mt-1 text-[9px] text-muted-foreground">
              No voices available. Your browser may not support Web Speech API.
            </p>
          )}
        </div>

        {/* AI TTS Model */}
        <div>
          <label className="mb-2 block text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            AI TTS Model
          </label>
          <select
            value={prefs.ttsModelId || ''}
            onChange={(e) => updatePref('ttsModelId', e.target.value || null)}
            className="w-full rounded-md border bg-background px-2 py-1.5 text-xs text-foreground outline-none"
          >
            <option value="">None (browser TTS only)</option>
            {models.filter((m) => m.is_active).map((m) => (
              <option key={m.user_model_id} value={m.user_model_id}>
                {m.alias || m.provider_model_name} ({m.provider_kind})
              </option>
            ))}
          </select>
          {models.length === 0 && accessToken && (
            <p className="mt-1 text-[9px] text-muted-foreground">
              No models configured. Add a provider in Settings &gt; Providers.
            </p>
          )}
        </div>

        {/* AI TTS Voice */}
        {prefs.ttsModelId && (
          <div>
            <label className="mb-2 block text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              AI Voice
            </label>
            <input
              type="text"
              value={prefs.ttsVoice}
              onChange={(e) => updatePref('ttsVoice', e.target.value)}
              placeholder="alloy"
              className="w-full rounded-md border bg-background px-2 py-1.5 text-xs text-foreground outline-none"
            />
            <p className="mt-1 text-[9px] text-muted-foreground">
              OpenAI voices: alloy, echo, fable, onyx, nova, shimmer
            </p>
          </div>
        )}

        {/* Behavior toggles */}
        <div>
          <label className="mb-2 block text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Behavior
          </label>
          <div className="space-y-2">
            <ToggleRow
              label="Auto-scroll to active block"
              checked={prefs.autoScroll}
              onChange={(v) => updatePref('autoScroll', v)}
            />
            <ToggleRow
              label="Highlight active block"
              checked={prefs.highlight}
              onChange={(v) => updatePref('highlight', v)}
            />
          </div>
        </div>

        {/* Current status */}
        {state.status !== 'idle' && (
          <div>
            <label className="mb-2 block text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Now Playing
            </label>
            <div className="rounded-md border bg-secondary p-2 text-[11px]">
              <div className="flex items-center gap-2">
                <span className={cn(
                  'h-2 w-2 rounded-full',
                  state.status === 'playing' ? 'bg-green-500 animate-pulse' : 'bg-yellow-500',
                )} />
                <span className="capitalize text-foreground">{state.status}</span>
                <span className="text-muted-foreground">·</span>
                <span className="text-muted-foreground">{state.source}</span>
              </div>
              {state.activeBlockId && (
                <div className="mt-1 truncate text-muted-foreground">
                  Block: {state.activeBlockId}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ToggleRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center justify-between">
      <span className="text-xs text-foreground">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative h-5 w-9 rounded-full transition-colors',
          checked ? 'bg-primary' : 'bg-border',
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform',
            checked ? 'translate-x-4' : 'translate-x-0.5',
          )}
        />
      </button>
    </label>
  );
}

/** Export prefs loader for use by other components */
export { loadPrefs };
