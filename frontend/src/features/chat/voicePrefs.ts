const STORAGE_KEY = 'lw_voice_prefs';

export type STTSource = 'browser' | 'ai_model';
export type TTSSource = 'browser' | 'ai_model';

export interface VoicePrefs {
  // Speech Recognition
  sttSource: STTSource;
  sttModelRef: string;       // user_model_id when sttSource='ai_model'
  speechLang: string;
  silenceThresholdMs: number;
  autoSendOnSilence: boolean;
  showInterimResults: boolean;

  // Text-to-Speech
  ttsSource: TTSSource;
  ttsModelRef: string;       // user_model_id when ttsSource='ai_model'
  ttsVoiceURI: string;       // browser voice URI
  ttsSpeed: number;
  autoTTSResponses: boolean;

  // Behavior
  pauseMicDuringTTS: boolean;
}

export const DEFAULT_VOICE_PREFS: VoicePrefs = {
  sttSource: 'browser',
  sttModelRef: '',
  speechLang: 'en-US',
  silenceThresholdMs: 1500,
  autoSendOnSilence: true,
  showInterimResults: true,

  ttsSource: 'browser',
  ttsModelRef: '',
  ttsVoiceURI: '',
  ttsSpeed: 1,
  autoTTSResponses: true,

  pauseMicDuringTTS: true,
};

export function loadVoicePrefs(): VoicePrefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_VOICE_PREFS };
    return { ...DEFAULT_VOICE_PREFS, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_VOICE_PREFS };
  }
}

export function saveVoicePrefs(prefs: VoicePrefs): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
}
