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
  silenceThresholdMs?: number;
  onSilenceDetected?: (text: string) => void;
  onFinalTranscript?: (text: string) => void;
  token?: string | null;
}

/** Check if MediaRecorder is available */
export const MEDIA_RECORDER_SUPPORTED =
  typeof window !== 'undefined' && typeof MediaRecorder !== 'undefined';

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
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  // Silence detection via AudioAnalyser — monitors audio level
  const startSilenceDetection = useCallback((stream: MediaStream) => {
    try {
      const audioCtx = new AudioContext();
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

        // Average volume level
        const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
        const threshold = 10; // Below this = silence

        if (avg > threshold) {
          lastSpeechTime = Date.now();
          // Show "recording" as interim while speaking
          setState((prev) => ({ ...prev, interimTranscript: '🎤 Recording...' }));
        }

        const silenceMs = optionsRef.current.silenceThresholdMs ?? 1500;
        if (silenceMs > 0 && Date.now() - lastSpeechTime > silenceMs && chunksRef.current.length > 0) {
          // Silence detected — stop recording and transcribe
          stopAndTranscribe();
          return;
        }

        animFrameRef.current = requestAnimationFrame(check);
      };

      animFrameRef.current = requestAnimationFrame(check);
    } catch {
      // AudioContext not available — skip silence detection
    }
  }, []);

  const stopAndTranscribe = useCallback(async () => {
    // Stop the recorder
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }

    // Wait a tick for final 'dataavailable' event
    await new Promise((r) => setTimeout(r, 100));

    const chunks = chunksRef.current;
    if (chunks.length === 0) return;

    const blob = new Blob(chunks, { type: 'audio/webm;codecs=opus' });
    chunksRef.current = [];

    setState((prev) => ({ ...prev, interimTranscript: 'Transcribing...' }));

    try {
      const formData = new FormData();
      formData.append('file', blob, 'recording.webm');
      formData.append('model', optionsRef.current.model || 'whisper-1');
      if (optionsRef.current.lang) {
        formData.append('language', optionsRef.current.lang);
      }

      const headers: Record<string, string> = {};
      if (optionsRef.current.token) {
        headers.Authorization = `Bearer ${optionsRef.current.token}`;
      }

      const resp = await fetch('/v1/audio/transcriptions', {
        method: 'POST',
        headers,
        body: formData,
      });

      if (!resp.ok) {
        const detail = await resp.text().catch(() => resp.statusText);
        throw new Error(`STT failed: ${resp.status} ${detail}`);
      }

      const data = await resp.json();
      const text = data.text || '';

      setState((prev) => ({
        ...prev,
        transcript: text,
        interimTranscript: '',
      }));

      if (text) {
        optionsRef.current.onFinalTranscript?.(text);
        optionsRef.current.onSilenceDetected?.(text);
      }
    } catch (err) {
      setState((prev) => ({
        ...prev,
        error: (err as Error).message,
        interimTranscript: '',
      }));
    }

    // Auto-restart if still supposed to be listening
    if (state.isListening) {
      startRecording();
    }
  }, [state.isListening]);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const recorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : 'audio/webm',
      });
      mediaRecorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      recorder.start(250); // Collect data every 250ms
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
    // Stop silence detection
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    analyserRef.current = null;

    // Stop recorder
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    mediaRecorderRef.current = null;

    // Stop media stream tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }

    chunksRef.current = [];
    setState((prev) => ({ ...prev, isListening: false, interimTranscript: '' }));
  }, []);

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
