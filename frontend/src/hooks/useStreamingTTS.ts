/**
 * Streaming TTS hook — fetches audio from POST /v1/audio/speech and plays
 * it in real-time via AudioContext as chunks arrive.
 *
 * For use when ttsSource === 'ai_model' in voice mode preferences.
 */

import { useCallback, useRef, useState } from 'react';

export type StreamingTTSStatus = 'idle' | 'loading' | 'playing' | 'error';

export interface StreamingTTSControls {
  status: StreamingTTSStatus;
  /** Speak text via the backend TTS service. Resolves when playback finishes. */
  speak: (text: string, onEnd?: () => void) => void;
  /** Stop current playback */
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
  const onEndRef = useRef<(() => void) | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const getAudioContext = useCallback(() => {
    if (!audioCtxRef.current || audioCtxRef.current.state === 'closed') {
      audioCtxRef.current = new AudioContext({ sampleRate: 24000 });
    }
    return audioCtxRef.current;
  }, []);

  const speak = useCallback((text: string, onEnd?: () => void) => {
    // Abort any in-progress request
    abortRef.current?.abort();
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
        response_format: 'wav', // WAV is easiest to decode in chunks
        speed: opts.speed || 1.0,
      }),
      signal: controller.signal,
    })
      .then(async (resp) => {
        if (!resp.ok) {
          const detail = await resp.text().catch(() => resp.statusText);
          throw new Error(`TTS failed: ${resp.status} ${detail}`);
        }

        setStatus('playing');
        const audioCtx = getAudioContext();

        // Read the entire response as ArrayBuffer and decode
        // (For true streaming with partial decoding, we'd need raw PCM + manual scheduling,
        // but decodeAudioData works reliably across browsers for the MVP)
        const arrayBuffer = await resp.arrayBuffer();

        if (controller.signal.aborted) return;

        const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);

        if (controller.signal.aborted) return;

        const source = audioCtx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioCtx.destination);
        source.playbackRate.value = opts.speed || 1.0;

        source.onended = () => {
          setStatus('idle');
          onEndRef.current?.();
        };

        source.start();

        // Store source for stop()
        abortRef.current = controller;
        (controller as any)._source = source;
      })
      .catch((err) => {
        if ((err as Error).name === 'AbortError') {
          setStatus('idle');
          return;
        }
        setError((err as Error).message);
        setStatus('error');
        onEndRef.current?.();
      });
  }, [getAudioContext]);

  const stop = useCallback(() => {
    if (abortRef.current) {
      // Stop audio playback if source exists
      const source = (abortRef.current as any)?._source as AudioBufferSourceNode | undefined;
      if (source) {
        try { source.stop(); } catch { /* already stopped */ }
      }
      abortRef.current.abort();
      abortRef.current = null;
    }
    setStatus('idle');
  }, []);

  return { status, speak, stop, error };
}
