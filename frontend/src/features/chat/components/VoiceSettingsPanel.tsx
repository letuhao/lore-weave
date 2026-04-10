import { useState, useEffect } from 'react';
import { X, Settings2, Mic, Volume2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';
import { BrowserTTSEngine } from '@/hooks/engines/BrowserTTSEngine';
import { type VoicePrefs, loadVoicePrefs, saveVoicePrefs, DEFAULT_VOICE_PREFS } from '../voicePrefs';
import { cn } from '@/lib/utils';

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];

const LANGUAGES = [
  { code: 'en-US', label: 'English (US)' },
  { code: 'en-GB', label: 'English (UK)' },
  { code: 'ja', label: '日本語' },
  { code: 'zh-TW', label: '繁體中文' },
  { code: 'vi', label: 'Tiếng Việt' },
  { code: 'ko', label: '한국어' },
  { code: 'fr', label: 'Français' },
  { code: 'de', label: 'Deutsch' },
  { code: 'es', label: 'Español' },
];

const SILENCE_MIN = 500;
const SILENCE_MAX = 3000;
const SILENCE_STEP = 100;

interface VoiceSettingsPanelProps {
  open: boolean;
  onClose: () => void;
}

export function VoiceSettingsPanel({ open, onClose }: VoiceSettingsPanelProps) {
  const { t } = useTranslation('common');
  const { accessToken } = useAuth();
  const [prefs, setPrefs] = useState<VoicePrefs>(loadVoicePrefs);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [sttModels, setSttModels] = useState<UserModel[]>([]);
  const [ttsModels, setTtsModels] = useState<UserModel[]>([]);

  // Load browser voices
  useEffect(() => {
    const loadVoices = () => setVoices(BrowserTTSEngine.getVoices());
    loadVoices();
    speechSynthesis?.addEventListener('voiceschanged', loadVoices);
    return () => speechSynthesis?.removeEventListener('voiceschanged', loadVoices);
  }, []);

  // Load AI models
  useEffect(() => {
    if (!accessToken) return;
    aiModelsApi.listUserModels(accessToken, { capability: 'stt' })
      .then((r) => setSttModels(r.items.filter((m) => m.is_active)))
      .catch(() => setSttModels([]));
    aiModelsApi.listUserModels(accessToken, { capability: 'tts' })
      .then((r) => setTtsModels(r.items.filter((m) => m.is_active)))
      .catch(() => setTtsModels([]));
  }, [accessToken]);

  const update = <K extends keyof VoicePrefs>(key: K, value: VoicePrefs[K]) => {
    setPrefs((prev) => {
      const next = { ...prev, [key]: value };
      saveVoicePrefs(next);
      return next;
    });
  };

  if (!open) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-40 flex w-72 flex-col border-l bg-card shadow-xl">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Settings2 className="h-4 w-4" />
          {t('voice.settingsTitle', 'Voice Settings')}
        </div>
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {/* ── Speech Recognition Section ── */}
        <SectionHeader icon={<Mic className="h-3.5 w-3.5" />} label={t('voice.sttSection', 'Speech Recognition')} />

        {/* STT Source */}
        <FieldGroup label={t('voice.sttSource', 'STT Source')}>
          <select
            value={prefs.sttSource}
            onChange={(e) => update('sttSource', e.target.value as 'browser' | 'ai_model')}
            className="h-8 w-full rounded-md border bg-background px-2 text-xs focus:border-ring focus:outline-none"
          >
            <option value="browser">{t('voice.browser', 'Browser (free)')}</option>
            <option value="ai_model">{t('voice.aiModel', 'AI Model')}</option>
          </select>
        </FieldGroup>

        {/* STT Model (when ai_model) */}
        {prefs.sttSource === 'ai_model' && (
          <FieldGroup label={t('voice.sttModel', 'STT Model')}>
            {sttModels.length === 0 ? (
              <p className="text-[10px] text-muted-foreground">{t('voice.noModels', 'No STT models configured')}</p>
            ) : (
              <select
                value={prefs.sttModelRef}
                onChange={(e) => update('sttModelRef', e.target.value)}
                className="h-8 w-full rounded-md border bg-background px-2 text-xs focus:border-ring focus:outline-none"
              >
                <option value="">{t('voice.selectModel', 'Select model...')}</option>
                {sttModels.map((m) => (
                  <option key={m.user_model_id} value={m.user_model_id}>
                    {m.alias || m.provider_model_name}
                  </option>
                ))}
              </select>
            )}
          </FieldGroup>
        )}

        {/* Language */}
        <FieldGroup label={t('voice.language', 'Language')}>
          <select
            value={prefs.speechLang}
            onChange={(e) => update('speechLang', e.target.value)}
            className="h-8 w-full rounded-md border bg-background px-2 text-xs focus:border-ring focus:outline-none"
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>{l.label} ({l.code})</option>
            ))}
          </select>
        </FieldGroup>

        {/* Silence Threshold */}
        <FieldGroup label={`${t('voice.silenceThreshold', 'Silence threshold')} — ${(prefs.silenceThresholdMs / 1000).toFixed(1)}s`}>
          <input
            type="range"
            min={SILENCE_MIN}
            max={SILENCE_MAX}
            step={SILENCE_STEP}
            value={prefs.silenceThresholdMs}
            onChange={(e) => update('silenceThresholdMs', +e.target.value)}
            className="w-full h-1 rounded-full appearance-none bg-border accent-primary"
          />
          <div className="flex justify-between text-[9px] text-muted-foreground mt-0.5">
            <span>0.5s</span>
            <span>3.0s</span>
          </div>
        </FieldGroup>

        {/* Toggles */}
        <ToggleRow
          label={t('voice.autoSend', 'Auto-send on silence')}
          checked={prefs.autoSendOnSilence}
          onChange={(v) => update('autoSendOnSilence', v)}
        />
        <ToggleRow
          label={t('voice.showInterim', 'Show interim results')}
          checked={prefs.showInterimResults}
          onChange={(v) => update('showInterimResults', v)}
        />

        <div className="border-t pt-4" />

        {/* ── Text-to-Speech Section ── */}
        <SectionHeader icon={<Volume2 className="h-3.5 w-3.5" />} label={t('voice.ttsSection', 'Text-to-Speech')} />

        {/* TTS Source */}
        <FieldGroup label={t('voice.ttsSource', 'TTS Source')}>
          <select
            value={prefs.ttsSource}
            onChange={(e) => update('ttsSource', e.target.value as 'browser' | 'ai_model')}
            className="h-8 w-full rounded-md border bg-background px-2 text-xs focus:border-ring focus:outline-none"
          >
            <option value="browser">{t('voice.browser', 'Browser (free)')}</option>
            <option value="ai_model">{t('voice.aiModel', 'AI Model')}</option>
          </select>
        </FieldGroup>

        {/* TTS Model (when ai_model) */}
        {prefs.ttsSource === 'ai_model' && (
          <FieldGroup label={t('voice.ttsModel', 'TTS Model')}>
            {ttsModels.length === 0 ? (
              <p className="text-[10px] text-muted-foreground">{t('voice.noModels', 'No TTS models configured')}</p>
            ) : (
              <select
                value={prefs.ttsModelRef}
                onChange={(e) => update('ttsModelRef', e.target.value)}
                className="h-8 w-full rounded-md border bg-background px-2 text-xs focus:border-ring focus:outline-none"
              >
                <option value="">{t('voice.selectModel', 'Select model...')}</option>
                {ttsModels.map((m) => (
                  <option key={m.user_model_id} value={m.user_model_id}>
                    {m.alias || m.provider_model_name}
                  </option>
                ))}
              </select>
            )}
          </FieldGroup>
        )}

        {/* Browser Voice (when browser) */}
        {prefs.ttsSource === 'browser' && voices.length > 0 && (
          <FieldGroup label={t('voice.browserVoice', 'Browser Voice')}>
            <select
              value={prefs.ttsVoiceURI}
              onChange={(e) => update('ttsVoiceURI', e.target.value)}
              className="h-8 w-full rounded-md border bg-background px-2 text-xs focus:border-ring focus:outline-none"
            >
              <option value="">{t('voice.defaultVoice', 'Default')}</option>
              {voices.map((v) => (
                <option key={v.voiceURI} value={v.voiceURI}>
                  {v.name} ({v.lang})
                </option>
              ))}
            </select>
          </FieldGroup>
        )}

        {/* TTS Speed */}
        <FieldGroup label={t('voice.speed', 'Speed')}>
          <div className="flex gap-1">
            {SPEEDS.map((s) => (
              <button
                key={s}
                onClick={() => update('ttsSpeed', s)}
                className={cn(
                  'flex-1 rounded-md py-1.5 text-[11px] font-medium transition',
                  prefs.ttsSpeed === s
                    ? 'bg-primary/15 text-primary'
                    : 'bg-secondary text-muted-foreground hover:text-foreground',
                )}
              >
                {s}x
              </button>
            ))}
          </div>
        </FieldGroup>

        <ToggleRow
          label={t('voice.autoTTS', 'Auto-play AI responses')}
          checked={prefs.autoTTSResponses}
          onChange={(v) => update('autoTTSResponses', v)}
        />

        <div className="border-t pt-4" />

        {/* ── Behavior Section ── */}
        <ToggleRow
          label={t('voice.pauseMic', 'Pause mic during TTS')}
          checked={prefs.pauseMicDuringTTS}
          onChange={(v) => update('pauseMicDuringTTS', v)}
        />

        {/* Reset */}
        <button
          onClick={() => {
            setPrefs({ ...DEFAULT_VOICE_PREFS });
            saveVoicePrefs(DEFAULT_VOICE_PREFS);
          }}
          className="w-full rounded-md border py-1.5 text-[11px] text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
        >
          {t('voice.resetDefaults', 'Reset to defaults')}
        </button>
      </div>
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────────────────

function SectionHeader({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
      {icon}
      {label}
    </div>
  );
}

function FieldGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-[11px] text-muted-foreground">{label}</label>
      {children}
    </div>
  );
}

function ToggleRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between cursor-pointer group">
      <span className="text-[11px] text-muted-foreground group-hover:text-foreground transition-colors">{label}</span>
      <button
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
            'absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform',
            checked && 'translate-x-4',
          )}
        />
      </button>
    </label>
  );
}
