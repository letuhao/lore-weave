/**
 * Backend STT hook — records audio via MediaRecorder, sends to
 * POST /v1/audio/transcriptions, returns transcript.
 *
 * Same interface as useSpeechRecognition so the voice mode orchestrator
 * can swap between browser STT and backend STT transparently.
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
  /** user_model_id for provider-registry credential resolution */
  modelRef?: string;
  silenceThresholdMs?: number;
  onSilenceDetected?: (text: string) => void;
  /** Called with STT performance metrics (audioKB, durationMs) */
  onMetrics?: (audioKB: number, durationMs: number) => void;
  token?: string | null;
}

/** Check if MediaRecorder is available */
export const MEDIA_RECORDER_SUPPORTED =
  typeof window !== 'undefined' && typeof MediaRecorder !== 'undefined';

/** Detect best supported mimeType for audio recording */
function getBestMimeType(): string {
  if (typeof MediaRecorder === 'undefined') return 'audio/webm';
  for (const mime of ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg']) {
    if (MediaRecorder.isTypeSupported(mime)) return mime;
  }
  return 'audio/webm';
}

export function useBackendSTT(options: BackendSTTOptions = {}) {
  const [state, setState] = useState<BackendSTTState>({
    isListening: false,
    transcript: '',
    interimTranscript: '',
    error: null,
    supported: MEDIA_RECORDER_SUPPORTED,
  });

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const isListeningRef = useRef(false);
  const transcribingRef = useRef(false);
  const mimeTypeRef = useRef('audio/webm');
  const optionsRef = useRef(options);
  optionsRef.current = options;

  // Keep isListeningRef in sync
  useEffect(() => {
    isListeningRef.current = state.isListening;
  }, [state.isListening]);

  const stopSilenceDetection = useCallback(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    analyserRef.current = null;
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
  }, []);

  const stopAndTranscribe = useCallback(async () => {
    // Guard against concurrent transcription (#3)
    if (transcribingRef.current) return;
    transcribingRef.current = true;

    // Stop silence detection during transcription
    stopSilenceDetection();

    // Stop recorder and wait for final data via onstop event (#4)
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state === 'recording') {
      await new Promise<void>((resolve) => {
        recorder.onstop = () => resolve();
        recorder.stop();
      });
    }

    const chunks = chunksRef.current;
    chunksRef.current = [];
    if (chunks.length === 0) {
      transcribingRef.current = false;
      if (isListeningRef.current) void startRecording();
      return;
    }

    // Use actual mimeType from recorder (#6)
    const blob = new Blob(chunks, { type: mimeTypeRef.current });

    // Skip tiny recordings (likely just noise/silence — prevent Whisper hallucinations)
    const MIN_AUDIO_BYTES = 5000; // ~0.3s of webm audio
    if (blob.size < MIN_AUDIO_BYTES) {
      console.log(`[STT] Skipping tiny audio (${blob.size} bytes < ${MIN_AUDIO_BYTES})`);
      transcribingRef.current = false;
      if (isListeningRef.current) void startRecording();
      return;
    }

    const ext = mimeTypeRef.current.includes('mp4') ? '.mp4'
      : mimeTypeRef.current.includes('ogg') ? '.ogg'
      : '.webm';

    const audioSizeKB = (blob.size / 1024).toFixed(1);
    const t0 = performance.now();
    let t1 = t0;

    setState((prev) => ({ ...prev, interimTranscript: `Transcribing (${audioSizeKB}KB)...` }));

    try {
      const formData = new FormData();
      formData.append('file', blob, `recording${ext}`);
      formData.append('model', optionsRef.current.model || 'whisper-1');
      if (optionsRef.current.lang) {
        const lang = optionsRef.current.lang.split('-')[0];
        formData.append('language', lang);
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

      t1 = performance.now();
      console.log(`[STT] Sending ${audioSizeKB}KB audio — prep took ${(t1 - t0).toFixed(0)}ms`);

      const resp = await fetch(proxyUrl, {
        method: 'POST',
        headers,
        body: formData,
      });
      const t2 = performance.now();
      console.log(`[STT] Fetch completed in ${(t2 - t1).toFixed(0)}ms (HTTP ${resp.status})`);

      if (!resp.ok) {
        const detail = await resp.text().catch(() => resp.statusText);
        throw new Error(`STT failed: ${resp.status} ${detail}`);
      }

      const t3 = performance.now();
      const data = await resp.json();
      const text = data.text || '';
      const totalMs = t3 - t0;
      const fetchMs = t3 - t1;
      console.log(`[STT] Done — total ${totalMs.toFixed(0)}ms (fetch ${fetchMs.toFixed(0)}ms) — "${text.slice(0, 80)}${text.length > 80 ? '...' : ''}"`);
      optionsRef.current.onMetrics?.(blob.size / 1024, totalMs);

      setState((prev) => ({
        ...prev,
        transcript: text,
        interimTranscript: '',
      }));

      // Only fire callback for meaningful transcripts (skip Whisper hallucinations)
      const cleaned = text.trim();
      if (cleaned && cleaned.length > 1) {
        optionsRef.current.onSilenceDetected?.(cleaned);
      }
    } catch (err) {
      setState((prev) => ({
        ...prev,
        error: (err as Error).message,
        interimTranscript: '',
      }));
    }

    transcribingRef.current = false;

    // Do NOT auto-restart — let the voice mode orchestrator control STT lifecycle.
    // The orchestrator calls start() again when it's ready for the next turn
    // (e.g., after TTS finishes playing via onAllPlayed callback).
    console.log('[STT] Transcription complete — waiting for orchestrator to restart');
  }, [stopSilenceDetection]); // eslint-disable-line react-hooks/exhaustive-deps

  const startSilenceDetection = useCallback((stream: MediaStream) => {
    try {
      // Close previous AudioContext if any (#1)
      if (audioCtxRef.current) {
        audioCtxRef.current.close().catch(() => {});
      }

      const audioCtx = new AudioContext();
      audioCtxRef.current = audioCtx;
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      analyserRef.current = analyser;

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      let lastSpeechTime = Date.now();

      const check = () => {
        if (!analyserRef.current) return;
        analyser.getByteFrequencyData(dataArray);

        const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
        const threshold = 10;

        if (avg > threshold) {
          lastSpeechTime = Date.now();
          setState((prev) => ({ ...prev, interimTranscript: '🎤 Recording...' }));
        }

        const silenceMs = optionsRef.current.silenceThresholdMs ?? 1500;
        if (silenceMs > 0 && Date.now() - lastSpeechTime > silenceMs && chunksRef.current.length > 0) {
          void stopAndTranscribe();
          return;
        }

        animFrameRef.current = requestAnimationFrame(check);
      };

      animFrameRef.current = requestAnimationFrame(check);
    } catch {
      // AudioContext not available — skip silence detection
    }
  }, [stopAndTranscribe]);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mimeType = getBestMimeType();
      mimeTypeRef.current = mimeType;

      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      recorder.start(250);
      startSilenceDetection(stream);
    } catch (err) {
      setState((prev) => ({
        ...prev,
        error: (err as Error).message,
        isListening: false,
      }));
    }
  }, [startSilenceDetection]);

  const start = useCallback(() => {
    setState((prev) => ({
      ...prev,
      isListening: true,
      transcript: '',
      interimTranscript: '',
      error: null,
    }));
    void startRecording();
  }, [startRecording]);

  const stop = useCallback(() => {
    stopSilenceDetection();

    // Stop recorder (#8 — clear handler before nulling)
    if (mediaRecorderRef.current) {
      if (mediaRecorderRef.current.state === 'recording') {
        mediaRecorderRef.current.stop();
      }
      mediaRecorderRef.current.ondataavailable = null;
      mediaRecorderRef.current = null;
    }

    // Stop media stream tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }

    chunksRef.current = [];
    transcribingRef.current = false;
    isListeningRef.current = false; // Set ref immediately (don't wait for React effect)
    setState((prev) => ({ ...prev, isListening: false, interimTranscript: '' }));
  }, [stopSilenceDetection]);

  const resetTranscript = useCallback(() => {
    setState((prev) => ({ ...prev, transcript: '', interimTranscript: '' }));
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  return {
    ...state,
    start,
    stop,
    resetTranscript,
  };
}
