/**
 * Web Speech API wrapper for continuous speech recognition.
 *
 * Features:
 * - Continuous listening with interim results
 * - Configurable silence detection (auto-finalize after pause)
 * - Auto-restart on recoverable errors (with max retry cap)
 * - Browser compatibility check
 * - Factory pattern — each consumer gets its own instance (no singleton conflicts)
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

export const SPEECH_RECOGNITION_SUPPORTED =
  typeof window !== 'undefined' && getSpeechRecognitionClass() !== null;

// Recoverable errors — auto-restart after these
const RECOVERABLE_ERRORS = new Set(['network', 'no-speech', 'aborted']);
const MAX_CONSECUTIVE_RESTARTS = 5;

// ── Store (factory — each consumer gets its own instance) ──────────────

type Listener = () => void;

const INITIAL_STATE: SpeechRecognitionState = {
  isListening: false,
  transcript: '',
  interimTranscript: '',
  error: null,
  supported: SPEECH_RECOGNITION_SUPPORTED,
};

export class SpeechRecognitionStore {
  private state: SpeechRecognitionState = { ...INITIAL_STATE };
  private listeners = new Set<Listener>();
  private recognition: NativeSpeechRecognition | null = null;
  private silenceTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldRestart = false;
  private restartCount = 0;
  private optionsRef: { current: SpeechRecognitionOptions } = { current: {} };

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

  /** Update options reference (used by callbacks to avoid stale closures) */
  setOptions(options: SpeechRecognitionOptions) {
    this.optionsRef.current = options;
  }

  start() {
    if (!SPEECH_RECOGNITION_SUPPORTED) return;
    if (this.recognition) {
      this.recognition.abort();
    }

    const Ctor = getSpeechRecognitionClass()!;
    const rec = new Ctor();
    const opts = this.optionsRef.current;
    rec.continuous = opts.continuous ?? true;
    rec.interimResults = opts.interimResults ?? true;
    rec.lang = opts.lang || 'en-US';

    rec.onstart = () => {
      this.restartCount = 0; // Reset on successful start
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
        this.optionsRef.current.onFinalTranscript?.(finalText);
      }
      this.state.interimTranscript = interimText;
      this.emit();

      // Reset silence timer on any speech activity
      this.resetSilenceTimer();
    };

    rec.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (RECOVERABLE_ERRORS.has(event.error) && this.shouldRestart) {
        this.restartCount++;
        if (this.restartCount > MAX_CONSECUTIVE_RESTARTS) {
          this.state.error = `Too many restart attempts (${event.error})`;
          this.state.isListening = false;
          this.shouldRestart = false;
          this.emit();
          return;
        }
        setTimeout(() => {
          if (this.shouldRestart) this.start();
        }, 300 * this.restartCount); // Exponential-ish backoff
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
        this.restartCount++;
        if (this.restartCount > MAX_CONSECUTIVE_RESTARTS) {
          this.state.error = 'Recognition stopped unexpectedly';
          this.shouldRestart = false;
          this.emit();
          return;
        }
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
    this.restartCount = 0;
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
    const threshold = this.optionsRef.current.silenceThresholdMs ?? 1500;
    if (threshold <= 0) return;

    this.silenceTimer = setTimeout(() => {
      // Use the latest state at the time the timer fires (not stale closure)
      const currentState = this.state;
      // Prefer interim if available (hasn't been promoted to final yet),
      // otherwise use the accumulated final transcript
      const text = currentState.interimTranscript.trim()
        || currentState.transcript.trim();
      if (text) {
        this.optionsRef.current.onSilenceDetected?.(text);
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

/** Create a new speech recognition store instance */
export function createSpeechRecognitionStore(): SpeechRecognitionStore {
  return new SpeechRecognitionStore();
}

// ── React Hook ─────────────────────────────────────────────────────────

export function useSpeechRecognition(options: SpeechRecognitionOptions = {}) {
  // Each hook instance gets its own store — no singleton conflicts
  const storeRef = useRef<SpeechRecognitionStore | null>(null);
  if (!storeRef.current) {
    storeRef.current = createSpeechRecognitionStore();
  }
  const store = storeRef.current;

  // Keep options in sync on every render (avoids stale closures in callbacks)
  store.setOptions(options);

  const state = useSyncExternalStore(
    useCallback((cb: () => void) => store.subscribe(cb), [store]),
    () => store.getState(),
  );

  const start = useCallback(() => {
    store.start();
  }, [store]);

  const stop = useCallback(() => {
    store.stop();
  }, [store]);

  const resetTranscript = useCallback(() => {
    store.resetTranscript();
  }, [store]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      store.stop();
    };
  }, [store]);

  return {
    ...state,
    start,
    stop,
    resetTranscript,
  };
}
