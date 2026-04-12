import { syncPrefsToServer, loadPrefFromServer } from '@/lib/syncPrefs';

const STORAGE_KEY = 'lw_voice_prefs';
const SERVER_KEY = 'voice_prefs';

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
  ttsVoiceURI: string;       // browser voice URI (when ttsSource='browser')
  ttsVoiceId: string;        // provider voice ID (when ttsSource='ai_model', e.g. 'af_heart')
  ttsSpeed: number;
  autoTTSResponses: boolean;

  // Behavior
  pauseMicDuringTTS: boolean;

  // Advanced VAD settings
  minSpeechDurationMs: number;  // Discard audio shorter than this (noise filter)
  vadSilenceFrames: number;     // Silero VAD redemptionFrames (frames × ~96ms = silence before speech-end)

  // Voice Assist mode
  voiceAssistEnabled: boolean;  // Always-on VAD mic in input bar (dictation mode)
  voiceAssistAppend: boolean;   // true = append to textarea, false = replace
  voiceAssistAutoTTS: boolean;  // Auto-play TTS on new AI responses

  // Debug
  showVoiceMetrics: boolean;    // Show STT/TTS timing on messages
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
  ttsVoiceId: '',
  ttsSpeed: 1,
  autoTTSResponses: true,

  pauseMicDuringTTS: true,

  minSpeechDurationMs: 500,  // 500ms default — discard very short audio
  vadSilenceFrames: 8,       // ~768ms silence before speech-end (Silero default)

  voiceAssistEnabled: false,
  voiceAssistAppend: true,   // Append by default (safer — doesn't discard existing text)
  voiceAssistAutoTTS: true,

  showVoiceMetrics: false,
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

export function saveVoicePrefs(prefs: VoicePrefs, token?: string | null): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  syncPrefsToServer(SERVER_KEY, prefs, token);
}

export async function loadVoicePrefsFromServer(token: string | null | undefined): Promise<VoicePrefs> {
  const server = await loadPrefFromServer<Partial<VoicePrefs>>(SERVER_KEY, token);
  if (server) {
    const merged = { ...DEFAULT_VOICE_PREFS, ...server };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
    return merged;
  }
  return loadVoicePrefs();
}
