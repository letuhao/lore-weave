/**
 * useVoiceAssistMic — push-to-talk mic for Voice Assist mode.
 * Same capture pipeline as Voice Mode (VadController + Silero VAD), but STT-only:
 * captures speech → WAV → backend STT → returns transcript text.
 * Does NOT send to LLM or trigger TTS — caller inserts text into the input box.
 */
import { useCallback, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { VadController } from '@/lib/VadController';
import { float32ToWavBlob, transcribeAudio } from '@/lib/audioUtils';
import { loadVoicePrefs } from '../voicePrefs';

export type MicState = 'idle' | 'activating' | 'listening' | 'transcribing' | 'error';

export interface VoiceAssistMicResult {
  micState: MicState;
  /** Start or stop the mic toggle. */
  toggleMic: () => void;
}

export function useVoiceAssistMic(
  onTranscript: (text: string) => void,
): VoiceAssistMicResult {
  const { accessToken } = useAuth();
  const [micState, setMicState] = useState<MicState>('idle');
  const vadRef = useRef<VadController | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    vadRef.current?.deactivate();
    vadRef.current = null;
    abortRef.current?.abort();
    abortRef.current = null;
    setMicState('idle');
  }, []);

  const start = useCallback(async () => {
    if (!accessToken) return;
    const prefs = loadVoicePrefs();

    if (!prefs.sttModelRef) {
      setMicState('error');
      setTimeout(() => setMicState('idle'), 2000);
      return;
    }

    setMicState('activating');

    const vad = new VadController({
      silenceFrames: prefs.vadSilenceFrames,
      minSpeechDurationMs: prefs.minSpeechDurationMs,
      onSpeechStart: () => {
        setMicState('listening');
      },
      onSpeechEnd: async (audio: Float32Array) => {
        // Pause VAD while transcribing (single-turn push-to-talk)
        vad.pause();
        setMicState('transcribing');

        try {
          const blob = float32ToWavBlob(audio, 16000);
          abortRef.current?.abort();
          const abort = new AbortController();
          abortRef.current = abort;

          const text = await transcribeAudio(blob, prefs.sttModelRef, prefs.sttModelName, accessToken, abort.signal);
          if (text) {
            onTranscript(text);
          }
        } catch (err) {
          if ((err as Error).name === 'AbortError') return;
          setMicState('error');
          setTimeout(() => setMicState('idle'), 2000);
          return;
        }

        // Done — stop mic (push-to-talk: one utterance per press)
        vad.deactivate();
        vadRef.current = null;
        setMicState('idle');
      },
      onError: () => {
        setMicState('error');
        setTimeout(() => setMicState('idle'), 2000);
      },
    });

    vadRef.current = vad;
    await vad.activate();
    vad.resume();
    setMicState('listening');
  }, [accessToken, onTranscript]);

  const toggleMic = useCallback(() => {
    if (micState === 'idle' || micState === 'error') {
      void start();
    } else {
      stop();
    }
  }, [micState, start, stop]);

  return { micState, toggleMic };
}
