/**
 * useVoiceChat — V2 voice pipeline React hook.
 * Thin client: VAD captures audio → POST to server → receive SSE (text + audio).
 * Server handles STT → LLM → TTS. Client handles mic capture + audio playback.
 *
 * Design ref: VOICE_PIPELINE_V2.md §6.4
 */
import { useCallback, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { VoiceClient, type VoiceConfig, type AudioChunkEvent } from '@/lib/VoiceClient';
import { VadController } from '@/lib/VadController';
import { TTSPlaybackQueue } from '@/lib/TTSPlaybackQueue';
import { loadVoicePrefs, type VoicePrefs } from '../voicePrefs';
import { syncPrefsToServer } from '@/lib/syncPrefs';

export type VoiceChatState = 'inactive' | 'listening' | 'sending' | 'receiving' | 'error';

export interface VoiceChatResult {
  state: VoiceChatState;
  sttText: string;
  aiText: string;
  error: string | null;
  showConsent: boolean;
  activate: () => Promise<void>;
  acceptConsent: () => void;
  dismissConsent: () => void;
  deactivate: () => void;
  cancel: () => void;
}

const CONSENT_KEY = 'lw_voice_consent_at';

export function useVoiceChat(sessionId: string | null): VoiceChatResult {
  const { accessToken } = useAuth();
  const [state, setState] = useState<VoiceChatState>('inactive');
  const [sttText, setSttText] = useState('');
  const [aiText, setAiText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [showConsent, setShowConsent] = useState(false);

  const vadRef = useRef<VadController | null>(null);
  const playbackRef = useRef<TTSPlaybackQueue | null>(null);
  const clientRef = useRef<VoiceClient | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const activeRef = useRef(false);
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;
  const consecutiveFailsRef = useRef(0);
  const sentenceChunksRef = useRef<Map<number, Uint8Array[]>>(new Map());

  const doActivate = useCallback(async () => {
    if (!sessionId || !accessToken || activeRef.current) return;
    activeRef.current = true;

    // Create AudioContext in user gesture (iOS Safari requirement — CRA-14)
    const ctx = new AudioContext({ sampleRate: 24000 });
    ctx.resume().catch(() => {});
    audioCtxRef.current = ctx;

    // Create playback queue with shared AudioContext
    const playback = new TTSPlaybackQueue({
      audioContext: ctx,
      onAllPlayed: () => {
        // Audio done — resume listening if still active
        if (activeRef.current) {
          setState('listening');
          vadRef.current?.resume();
        }
      },
    });
    playbackRef.current = playback;

    // Create voice client
    const apiBase = import.meta.env.VITE_API_BASE || '';
    clientRef.current = new VoiceClient(apiBase, accessToken);

    // Use user's configured settings (presets or manual sliders)
    const prefs = loadVoicePrefs();

    const vad = new VadController({
      silenceFrames: prefs.vadSilenceFrames,
      minSpeechDurationMs: prefs.minSpeechDurationMs,
      onSpeechEnd: (audio) => {
        if (!activeRef.current) return;
        vad.pause();
        void handleSpeechEnd(audio);
      },
      onSpeechStart: () => {
        setError(null);
      },
      onError: (err) => {
        setError(`Microphone error: ${err.message}`);
        setState('error');
      },
    });
    vadRef.current = vad;

    await vad.activate();
    vad.resume();
    setState('listening');
    setSttText('');
    setAiText('');
    setError(null);
    consecutiveFailsRef.current = 0;
  }, [sessionId, accessToken]);

  const acceptConsent = useCallback(() => {
    const ts = new Date().toISOString();
    localStorage.setItem(CONSENT_KEY, ts);
    syncPrefsToServer('voice_consent_at', ts, accessToken);
    setShowConsent(false);
    void doActivate();
  }, [doActivate, accessToken]);

  const dismissConsent = useCallback(() => {
    setShowConsent(false);
  }, []);

  const activate = useCallback(async () => {
    if (!localStorage.getItem(CONSENT_KEY)) {
      setShowConsent(true);
      return;
    }
    await doActivate();
  }, [doActivate]);

  const handleSpeechEnd = useCallback(async (audio: Float32Array) => {
    const sid = sessionIdRef.current;
    if (!clientRef.current || !sid) return;
    setState('sending');

    // Convert Float32Array to WAV blob
    const blob = float32ToWavBlob(audio, 16000);
    const prefs = loadVoicePrefs();

    // V2 pipeline requires STT model configured
    if (!prefs.sttModelRef) {
      setError('STT model not configured. Open Voice Settings and select a Speech-to-Text model.');
      setState('listening');
      vadRef.current?.resume();
      return;
    }

    // Calculate speech duration from audio samples (16kHz mono)
    const speechDurationMs = Math.round((audio.length / 16000) * 1000);

    const voiceConfig: VoiceConfig = {
      stt_model_source: 'user_model',
      stt_model_ref: prefs.sttModelRef,
      tts_model_source: prefs.ttsModelRef ? 'user_model' : undefined,
      tts_model_ref: prefs.ttsModelRef || undefined,
      tts_voice: prefs.ttsVoiceId || 'af_heart',
      speech_duration_ms: speechDurationMs,
      vad_silence_frames: prefs.vadSilenceFrames,
      vad_min_duration_ms: prefs.minSpeechDurationMs,
    };

    setAiText('');

    await clientRef.current.sendVoiceMessage(sid, blob, voiceConfig, {
      onTranscript: (text) => {
        setSttText(text);
        setState('receiving');
        consecutiveFailsRef.current = 0; // Reset on successful transcript
      },
      onTextDelta: (delta) => {
        setAiText((prev) => prev + delta);
      },
      onAudioChunk: (event: AudioChunkEvent) => {
        if (event.data) {
          // Decode base64 to binary, accumulate per sentence
          const binary = Uint8Array.from(atob(event.data), (c) => c.charCodeAt(0));
          const key = event.sentenceIndex;
          if (!sentenceChunksRef.current.has(key)) sentenceChunksRef.current.set(key, []);
          sentenceChunksRef.current.get(key)!.push(binary);
        }
        if (event.final) {
          // Sentence complete — combine all binary chunks, decode as one complete MP3
          const chunks = sentenceChunksRef.current.get(event.sentenceIndex);
          sentenceChunksRef.current.delete(event.sentenceIndex);
          if (chunks && chunks.length > 0) {
            const totalLen = chunks.reduce((sum, c) => sum + c.length, 0);
            const combined = new Uint8Array(totalLen);
            let offset = 0;
            for (const chunk of chunks) {
              combined.set(chunk, offset);
              offset += chunk.length;
            }
            playbackRef.current?.enqueue(combined.buffer);
          }
        }
      },
      onFinish: () => {
        playbackRef.current?.close();
        // State will transition to 'listening' via onAllPlayed callback
        // If no audio was generated, resume listening now
        if (!playbackRef.current?.isPlaying) {
          if (activeRef.current) {
            setState('listening');
            vadRef.current?.resume();
          }
        }
      },
      onError: (errorText) => {
        consecutiveFailsRef.current++;
        if (consecutiveFailsRef.current >= 3) {
          setError('Multiple failures. Check your microphone and STT model settings.');
        } else {
          setError(errorText || "Didn't catch that — try again.");
        }
        // Resume listening after error
        if (activeRef.current) {
          setState('listening');
          vadRef.current?.resume();
        }
      },
    });
  }, []); // sessionId accessed via ref to avoid stale closure in VAD callback

  const deactivate = useCallback(() => {
    activeRef.current = false;
    clientRef.current?.abort();
    vadRef.current?.deactivate();
    vadRef.current = null;
    playbackRef.current?.dispose();
    playbackRef.current = null;
    if (audioCtxRef.current && audioCtxRef.current.state !== 'closed') {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    setState('inactive');
    setSttText('');
    setAiText('');
    setError(null);
    setShowConsent(false);
    sentenceChunksRef.current.clear();
  }, []);

  const cancel = useCallback(() => {
    clientRef.current?.abort();
    playbackRef.current?.cancelAll();
    // Resume listening
    if (activeRef.current) {
      setState('listening');
      vadRef.current?.resume();
    }
  }, []);

  return { state, sttText, aiText, error, showConsent, activate, acceptConsent, dismissConsent, deactivate, cancel };
}

/** Convert Float32Array (16kHz mono) to WAV blob. */
function float32ToWavBlob(samples: Float32Array, sampleRate: number): Blob {
  const numChannels = 1;
  const bitsPerSample = 16;
  const byteRate = sampleRate * numChannels * (bitsPerSample / 8);
  const blockAlign = numChannels * (bitsPerSample / 8);
  const dataSize = samples.length * (bitsPerSample / 8);
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  // WAV header
  const writeString = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };
  writeString(0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  writeString(36, 'data');
  view.setUint32(40, dataSize, true);

  // Write samples (float32 → int16)
  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: 'audio/wav' });
}
