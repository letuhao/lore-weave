/**
 * Backend STT hook — uses Silero VAD for speech detection, then sends
 * the speech segment to POST /v1/audio/transcriptions via provider-registry.
 *
 * Flow:
 * 1. Silero VAD runs locally in the browser (ONNX/WASM, ~1ms per frame)
 * 2. onSpeechEnd fires with Float32Array of speech audio (16kHz)
 * 3. Convert to WAV blob → send to STT service
 * 4. Return transcript via onSilenceDetected callback
 *
 * No more noise loops — VAD only fires for real speech.
 */

import { useState, useCallback, useRef, useEffect } from 'react';

export interface BackendSTTState {
  isListening: boolean;
  transcript: string;
  interimTranscript: string;
  error: string | null;
  supported: boolean;
}

export interface BackendSTTOptions {
  lang?: string;
  model?: string;
  modelRef?: string;
  silenceThresholdMs?: number;
  onSilenceDetected?: (text: string) => void;
  onMetrics?: (audioKB: number, durationMs: number) => void;
  token?: string | null;
}

export const MEDIA_RECORDER_SUPPORTED =
  typeof window !== 'undefined' && typeof MediaRecorder !== 'undefined';

/** Convert Float32Array (16kHz mono) to WAV blob */
function float32ToWav(samples: Float32Array, sampleRate = 16000): Blob {
  const numSamples = samples.length;
  const dataSize = numSamples * 2; // 16-bit = 2 bytes per sample
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  // WAV header
  const writeStr = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };
  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeStr(36, 'data');
  view.setUint32(40, dataSize, true);

  // Convert float32 [-1,1] to int16
  for (let i = 0; i < numSamples; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }

  return new Blob([buffer], { type: 'audio/wav' });
}

export function useBackendSTT(options: BackendSTTOptions = {}) {
  const [state, setState] = useState<BackendSTTState>({
    isListening: false,
    transcript: '',
    interimTranscript: '',
    error: null,
    supported: MEDIA_RECORDER_SUPPORTED,
  });

  const vadRef = useRef<any>(null); // MicVAD instance
  const transcribingRef = useRef(false);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  /** Send speech audio to STT service */
  const transcribe = useCallback(async (audio: Float32Array) => {
    if (transcribingRef.current) return;
    transcribingRef.current = true;

    // Convert to WAV
    const blob = float32ToWav(audio);
    const audioSizeKB = blob.size / 1024;

    // Skip very short audio (< 0.3s at 16kHz = 4800 samples)
    if (audio.length < 4800) {
      console.log(`[STT] Skipping short speech (${audio.length} samples)`);
      transcribingRef.current = false;
      return;
    }

    const t0 = performance.now();
    console.log(`[STT] Speech detected: ${audio.length} samples (${(audio.length / 16000).toFixed(1)}s), ${audioSizeKB.toFixed(1)}KB WAV`);

    setState((prev) => ({ ...prev, interimTranscript: `Transcribing (${audioSizeKB.toFixed(0)}KB)...` }));

    try {
      const formData = new FormData();
      formData.append('file', blob, 'speech.wav');
      formData.append('model', optionsRef.current.model || 'whisper-1');
      if (optionsRef.current.lang) {
        formData.append('language', optionsRef.current.lang.split('-')[0]);
      }

      const headers: Record<string, string> = {};
      if (optionsRef.current.token) {
        headers.Authorization = `Bearer ${optionsRef.current.token}`;
      }

      const params = new URLSearchParams({ model_source: 'user_model' });
      if (optionsRef.current.modelRef) {
        params.set('model_ref', optionsRef.current.modelRef);
      }
      const proxyUrl = `/v1/model-registry/proxy/v1/audio/transcriptions?${params}`;

      const t1 = performance.now();
      const resp = await fetch(proxyUrl, { method: 'POST', headers, body: formData });
      const t2 = performance.now();

      if (!resp.ok) {
        const detail = await resp.text().catch(() => resp.statusText);
        throw new Error(`STT failed: ${resp.status} ${detail}`);
      }

      const data = await resp.json();
      const text = data.text || '';
      const totalMs = performance.now() - t0;
      console.log(`[STT] Done — total ${totalMs.toFixed(0)}ms (fetch ${(t2 - t1).toFixed(0)}ms) — "${text.slice(0, 80)}"`);
      optionsRef.current.onMetrics?.(audioSizeKB, totalMs);

      setState((prev) => ({ ...prev, transcript: text, interimTranscript: '' }));

      // Fire callback for meaningful transcripts only
      const cleaned = text.trim();
      if (cleaned && cleaned.length > 1) {
        optionsRef.current.onSilenceDetected?.(cleaned);
      }
    } catch (err) {
      console.error('[STT] Error:', (err as Error).message);
      setState((prev) => ({ ...prev, error: (err as Error).message, interimTranscript: '' }));
    }

    transcribingRef.current = false;
  }, []);

  const start = useCallback(async () => {
    setState((prev) => ({
      ...prev,
      isListening: true,
      transcript: '',
      interimTranscript: '',
      error: null,
    }));

    try {
      // Dynamic import to avoid bundling ONNX runtime when not using backend STT
      const { MicVAD } = await import('@ricky0123/vad-web');

      const vad = await MicVAD.new({
        // Self-hosted model and worklet files
        baseAssetPath: '/vad/',
        onnxWASMBasePath: '/vad/',
        onSpeechStart: () => {
          console.log('[VAD] Speech started');
          setState((prev) => ({ ...prev, interimTranscript: '🎤 Listening...' }));
        },
        onSpeechEnd: (audio: Float32Array) => {
          console.log(`[VAD] Speech ended: ${audio.length} samples (${(audio.length / 16000).toFixed(1)}s)`);
          void transcribe(audio);
        },
      });

      vad.start();
      vadRef.current = vad;
      console.log('[VAD] Started — Silero VAD active');
    } catch (err) {
      console.error('[VAD] Failed to initialize:', (err as Error).message);
      setState((prev) => ({
        ...prev,
        error: `VAD init failed: ${(err as Error).message}`,
        isListening: false,
      }));
    }
  }, [transcribe]);

  const stop = useCallback(() => {
    if (vadRef.current) {
      vadRef.current.pause();
      vadRef.current.destroy?.();
      vadRef.current = null;
    }
    transcribingRef.current = false;
    setState((prev) => ({ ...prev, isListening: false, interimTranscript: '' }));
  }, []);

  const resetTranscript = useCallback(() => {
    setState((prev) => ({ ...prev, transcript: '', interimTranscript: '' }));
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (vadRef.current) {
        vadRef.current.pause();
        vadRef.current.destroy?.();
        vadRef.current = null;
      }
    };
  }, []);

  return {
    ...state,
    start,
    stop,
    resetTranscript,
  };
}
