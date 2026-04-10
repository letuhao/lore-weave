/**
 * Web Speech API wrapper for continuous speech recognition.
 *
 * Features:
 * - Continuous listening with interim results
 * - Configurable silence detection (auto-finalize after pause)
 * - Auto-restart on recoverable errors
 * - Browser compatibility check
 * - External store pattern (matches useTTS.ts)
 */

import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react';

// ── Types ──────────────────────────────────────────────────────────────

export interface SpeechRecognitionState {
  isListening: boolean;
  transcript: string;
  interimTranscript: string;
  error: string | null;
  supported: boolean;
}

export interface SpeechRecognitionOptions {
  lang?: string;
  continuous?: boolean;
  interimResults?: boolean;
  silenceThresholdMs?: number;
  onFinalTranscript?: (text: string) => void;
  onSilenceDetected?: (fullTranscript: string) => void;
}

// ── Browser API types ──────────────────────────────────────────────────

interface SpeechRecognitionEvent {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionResultList {
  length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  isFinal: boolean;
  length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionErrorEvent {
  error: string;
  message?: string;
}

interface NativeSpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

// ── Detect browser support ─────────────────────────────────────────────

function getSpeechRecognitionClass(): (new () => NativeSpeechRecognition) | null {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const w = window as any;
  return (w.SpeechRecognition || w.webkitSpeechRecognition) as
    (new () => NativeSpeechRecognition) | null ?? null;
}

const SUPPORTED = typeof window !== 'undefined' && getSpeechRecognitionClass() !== null;

// Recoverable errors — auto-restart after these
const RECOVERABLE_ERRORS = new Set(['network', 'no-speech', 'aborted']);

// ── Store ──────────────────────────────────────────────────────────────

type Listener = () => void;

const INITIAL_STATE: SpeechRecognitionState = {
  isListening: false,
  transcript: '',
  interimTranscript: '',
  error: null,
  supported: SUPPORTED,
};

class SpeechRecognitionStore {
  private state: SpeechRecognitionState = { ...INITIAL_STATE };
  private listeners = new Set<Listener>();
  private recognition: NativeSpeechRecognition | null = null;
  private silenceTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldRestart = false;
  private options: SpeechRecognitionOptions = {};

  getState(): SpeechRecognitionState {
    return this.state;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private emit() {
    this.state = { ...this.state };
    for (const l of this.listeners) l();
  }

  configure(options: SpeechRecognitionOptions) {
    this.options = options;
  }

  start() {
    if (!SUPPORTED) return;
    if (this.recognition) {
      this.recognition.abort();
    }

    const Ctor = getSpeechRecognitionClass()!;
    const rec = new Ctor();
    rec.continuous = this.options.continuous ?? true;
    rec.interimResults = this.options.interimResults ?? true;
    rec.lang = this.options.lang || 'en-US';

    rec.onstart = () => {
      this.state.isListening = true;
      this.state.error = null;
      this.emit();
    };

    rec.onresult = (event: SpeechRecognitionEvent) => {
      let finalText = '';
      let interimText = '';

      for (let i = 0; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          finalText += result[0].transcript;
        } else {
          interimText += result[0].transcript;
        }
      }

      if (finalText && finalText !== this.state.transcript) {
        this.state.transcript = finalText;
        this.options.onFinalTranscript?.(finalText);
      }
      this.state.interimTranscript = interimText;
      this.emit();

      // Reset silence timer on any speech activity
      this.resetSilenceTimer();
    };

    rec.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (RECOVERABLE_ERRORS.has(event.error) && this.shouldRestart) {
        // Auto-restart after a brief delay
        setTimeout(() => {
          if (this.shouldRestart) this.start();
        }, 300);
        return;
      }
      this.state.error = event.error;
      this.state.isListening = false;
      this.emit();
    };

    rec.onend = () => {
      this.state.isListening = false;
      this.emit();
      // Auto-restart if we should still be listening (browser sometimes stops)
      if (this.shouldRestart) {
        setTimeout(() => {
          if (this.shouldRestart) this.start();
        }, 100);
      }
    };

    this.recognition = rec;
    this.shouldRestart = true;
    this.state.transcript = '';
    this.state.interimTranscript = '';
    this.state.error = null;

    try {
      rec.start();
    } catch {
      // Already started — ignore
    }
  }

  stop() {
    this.shouldRestart = false;
    this.clearSilenceTimer();
    if (this.recognition) {
      this.recognition.stop();
      this.recognition = null;
    }
    this.state.isListening = false;
    this.emit();
  }

  resetTranscript() {
    this.state.transcript = '';
    this.state.interimTranscript = '';
    this.emit();
  }

  private resetSilenceTimer() {
    this.clearSilenceTimer();
    const threshold = this.options.silenceThresholdMs ?? 1500;
    if (threshold <= 0) return;

    this.silenceTimer = setTimeout(() => {
      const full = (this.state.transcript + ' ' + this.state.interimTranscript).trim();
      if (full) {
        this.options.onSilenceDetected?.(full);
      }
    }, threshold);
  }

  private clearSilenceTimer() {
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
  }
}

// Singleton store
const store = new SpeechRecognitionStore();

// ── React Hook ─────────────────────────────────────────────────────────

export function useSpeechRecognition(options: SpeechRecognitionOptions = {}) {
  const optionsRef = useRef(options);
  optionsRef.current = options;

  // Keep store options in sync
  useEffect(() => {
    store.configure(optionsRef.current);
  }, [options.lang, options.continuous, options.interimResults, options.silenceThresholdMs]);

  const state = useSyncExternalStore(
    useCallback((cb: () => void) => store.subscribe(cb), []),
    () => store.getState(),
  );

  const start = useCallback(() => {
    store.configure(optionsRef.current);
    store.start();
  }, []);

  const stop = useCallback(() => {
    store.stop();
  }, []);

  const resetTranscript = useCallback(() => {
    store.resetTranscript();
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      store.stop();
    };
  }, []);

  return {
    ...state,
    start,
    stop,
    resetTranscript,
  };
}
