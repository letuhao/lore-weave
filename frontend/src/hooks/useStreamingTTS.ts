/**
 * Streaming TTS hook — fetches audio from POST /v1/audio/speech and plays
 * it via AudioContext.
 *
 * For use when ttsSource === 'ai_model' in voice mode preferences.
 */

import { useCallback, useRef, useState, useEffect } from 'react';

export type StreamingTTSStatus = 'idle' | 'loading' | 'playing' | 'error';

export interface StreamingTTSControls {
  status: StreamingTTSStatus;
  speak: (text: string, onEnd?: () => void) => void;
  stop: () => void;
  error: string | null;
}

export interface StreamingTTSOptions {
  model?: string;
  voice?: string;
  speed?: number;
  token?: string | null;
}

export function useStreamingTTS(options: StreamingTTSOptions = {}): StreamingTTSControls {
  const [status, setStatus] = useState<StreamingTTSStatus>('idle');
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<AudioBufferSourceNode | null>(null);
  const onEndRef = useRef<(() => void) | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const getAudioContext = useCallback(() => {
    if (!audioCtxRef.current || audioCtxRef.current.state === 'closed') {
      audioCtxRef.current = new AudioContext({ sampleRate: 24000 });
    }
    return audioCtxRef.current;
  }, []);

  const stopCurrentPlayback = useCallback(() => {
    // Stop audio source if playing (#10)
    if (sourceRef.current) {
      try { sourceRef.current.stop(); } catch { /* already stopped */ }
      sourceRef.current = null;
    }
    // Abort in-flight fetch
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
  }, []);

  const speak = useCallback((text: string, onEnd?: () => void) => {
    // Stop any in-progress playback first (#10)
    stopCurrentPlayback();

    const controller = new AbortController();
    abortRef.current = controller;
    onEndRef.current = onEnd ?? null;

    setStatus('loading');
    setError(null);

    const opts = optionsRef.current;
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (opts.token) {
      headers.Authorization = `Bearer ${opts.token}`;
    }

    fetch('/v1/audio/speech', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        model: opts.model || 'tts-1',
        voice: opts.voice || 'alloy',
        input: text,
        response_format: 'wav',
        speed: opts.speed || 1.0,
      }),
      signal: controller.signal,
    })
      .then(async (resp) => {
        if (!resp.ok) {
          const detail = await resp.text().catch(() => resp.statusText);
          throw new Error(`TTS failed: ${resp.status} ${detail}`);
        }

        const audioCtx = getAudioContext();
        // Resume if suspended — browsers auto-suspend before user gesture (#12)
        if (audioCtx.state === 'suspended') {
          await audioCtx.resume();
        }

        setStatus('playing');

        const arrayBuffer = await resp.arrayBuffer();
        if (controller.signal.aborted) return;

        const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
        if (controller.signal.aborted) return;

        const source = audioCtx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioCtx.destination);
        // Speed is already applied server-side — don't double-apply (#11)
        sourceRef.current = source;

        source.onended = () => {
          // Only fire callback if this source is still the current one (#10)
          if (sourceRef.current === source) {
            sourceRef.current = null;
            setStatus('idle');
            onEndRef.current?.();
          }
        };

        source.start();
      })
      .catch((err) => {
        if ((err as Error).name === 'AbortError') {
          setStatus('idle');
          return;
        }
        setError((err as Error).message);
        setStatus('error');
        // Don't call onEnd on error — let orchestrator see error state (#13)
      });
  }, [getAudioContext, stopCurrentPlayback]);

  const stop = useCallback(() => {
    stopCurrentPlayback();
    setStatus('idle');
  }, [stopCurrentPlayback]);

  // Cleanup on unmount (#9)
  useEffect(() => {
    return () => {
      stopCurrentPlayback();
      if (audioCtxRef.current) {
        audioCtxRef.current.close().catch(() => {});
        audioCtxRef.current = null;
      }
    };
  }, [stopCurrentPlayback]);

  return { status, speak, stop, error };
}
