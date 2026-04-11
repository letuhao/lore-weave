/**
 * Voice Mode orchestrator — coordinates STT, TTS, and chat into a
 * hands-free conversation loop.
 *
 * State machine: idle → listening → processing → speaking → listening → ...
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  useSpeechRecognition,
  SPEECH_RECOGNITION_SUPPORTED,
} from '@/hooks/useSpeechRecognition';
import { useBackendSTT, MEDIA_RECORDER_SUPPORTED } from '@/hooks/useBackendSTT';
import { BrowserTTSEngine } from '@/hooks/engines/BrowserTTSEngine';
import { useStreamingTTS } from '@/hooks/useStreamingTTS';
import { SentenceBuffer } from '@/lib/SentenceBuffer';
import { TTSPlaybackQueue } from '@/lib/TTSPlaybackQueue';
import { TTSConcurrencyPool } from '@/lib/TTSConcurrencyPool';
import { BargeInDetector } from '@/lib/BargeInDetector';
import { useAuth } from '@/auth';
import { loadVoicePrefs, type VoicePrefs } from '../voicePrefs';
import type { OnStreamDelta } from './useChatMessages';

export type VoicePhase = 'idle' | 'listening' | 'processing' | 'speaking' | 'paused';

export interface VoicePipelineMetrics {
  /** STT audio size in KB */
  sttAudioKB: number | null;
  /** STT processing time in ms */
  sttMs: number | null;
  /** Time to first LLM content token in ms */
  llmFirstTokenMs: number | null;
  /** Total LLM tokens received */
  llmTokenCount: number;
  /** Total LLM stream duration in ms */
  llmTotalMs: number | null;
  /** Number of sentences emitted by buffer */
  sentenceCount: number;
  /** Per-sentence TTS times in ms */
  ttsSentenceMs: number[];
  /** Total TTS audio generated in KB */
  ttsAudioKB: number;
}

export interface VoiceModeControls {
  /** Current phase of the voice loop */
  phase: VoicePhase;
  /** Whether voice mode is active (any phase except idle) */
  isActive: boolean;
  /** Whether browser supports speech recognition */
  supported: boolean;
  /** The current/last user transcript (finalized) */
  userTranscript: string;
  /** Live interim text while speaking */
  interimText: string;
  /** The AI response text (for display in overlay) */
  aiResponseText: string;
  /** Any error from STT */
  error: string | null;
  /** Start voice mode */
  activate: () => void;
  /** Stop voice mode completely */
  deactivate: () => void;
  /** Pause listening (stays in voice mode but stops mic) */
  pause: () => void;
  /** Resume listening after pause */
  resume: () => void;
  /** Reload preferences (after settings change) */
  reloadPrefs: () => void;
  /** Live performance metrics for the current turn */
  metrics: VoicePipelineMetrics;
}

interface UseVoiceModeOptions {
  /** Function to send a message — should return the AI response text */
  sendMessage: (content: string) => Promise<string>;
  /** Function to stop the current LLM stream (for barge-in) */
  stopStream?: () => void;
  /** Current streaming status from chat hook */
  streamStatus: 'idle' | 'streaming' | 'error';
  /** Current streaming text (live AI response) */
  streamingText: string;
  /** Ref to set the per-token delta callback on the chat hook */
  onStreamDeltaRef?: React.MutableRefObject<OnStreamDelta | null>;
}

export function useVoiceMode({
  sendMessage,
  stopStream,
  streamStatus,
  streamingText,
  onStreamDeltaRef,
}: UseVoiceModeOptions): VoiceModeControls {
  const { accessToken } = useAuth();
  const [phase, setPhase] = useState<VoicePhase>('idle');
  const [aiResponseText, setAiResponseText] = useState('');
  const [prefs, setPrefs] = useState<VoicePrefs>(loadVoicePrefs);
  const useBackendSTTSource = prefs.sttSource === 'ai_model';
  const useBackendTTSSource = prefs.ttsSource === 'ai_model';

  const phaseRef = useRef<VoicePhase>('idle');
  const ttsEngineRef = useRef<BrowserTTSEngine | null>(null);
  const pendingSendRef = useRef(false);

  // Streaming TTS pipeline (RTV-03)
  const sentenceBufferRef = useRef<SentenceBuffer | null>(null);
  const ttsPoolRef = useRef<TTSConcurrencyPool | null>(null);
  const ttsQueueRef = useRef<TTSPlaybackQueue | null>(null);
  const pipelineActiveRef = useRef(false);

  // Barge-in detection (RTV-04)
  const bargeInRef = useRef<BargeInDetector | null>(null);
  const bargeInStreamRef = useRef<MediaStream | null>(null);

  // Live metrics
  const [metrics, setMetrics] = useState<VoicePipelineMetrics>({
    sttAudioKB: null, sttMs: null,
    llmFirstTokenMs: null, llmTokenCount: 0, llmTotalMs: null,
    sentenceCount: 0, ttsSentenceMs: [], ttsAudioKB: 0,
  });
  const metricsRef = useRef(metrics);
  metricsRef.current = metrics;
  const resetMetrics = useCallback(() => {
    setMetrics({
      sttAudioKB: null, sttMs: null,
      llmFirstTokenMs: null, llmTokenCount: 0, llmTotalMs: null,
      sentenceCount: 0, ttsSentenceMs: [], ttsAudioKB: 0,
    });
  }, []);

  // Ref pattern — avoids stale closures in pipeline callbacks (#1, #5, #10)
  const sendMessageRef = useRef(sendMessage);
  sendMessageRef.current = sendMessage;
  const accessTokenRef = useRef(accessToken);
  accessTokenRef.current = accessToken;
  const stopStreamRef = useRef(stopStream);
  stopStreamRef.current = stopStream;
  const prefsRef = useRef(prefs);
  prefsRef.current = prefs;

  // Keep phaseRef in sync
  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  // Lazy-init TTS engine
  const getTTSEngine = useCallback(() => {
    if (!ttsEngineRef.current) {
      ttsEngineRef.current = new BrowserTTSEngine();
    }
    const engine = ttsEngineRef.current;
    engine.speed = prefs.ttsSpeed;
    if (prefs.ttsVoiceURI) {
      const voice = BrowserTTSEngine.getVoices().find(
        (v) => v.voiceURI === prefs.ttsVoiceURI,
      );
      if (voice) engine.voice = voice;
    }
    return engine;
  }, [prefs.ttsSpeed, prefs.ttsVoiceURI]);

  // onSilenceDetected ref — the callback is defined after startPipeline/stopPipeline
  // but the STT hooks need it now. Use a ref so hooks get the latest version.
  const onSilenceDetectedRef = useRef<((text: string) => void) | undefined>(undefined);

  // Browser STT (Web Speech API) — pass callbacks only when active (#15)
  const browserSTT = useSpeechRecognition({
    lang: prefs.speechLang,
    continuous: true,
    interimResults: true,
    silenceThresholdMs: !useBackendSTTSource && prefs.autoSendOnSilence ? prefs.silenceThresholdMs : 0,
    onSilenceDetected: !useBackendSTTSource ? (text: string) => onSilenceDetectedRef.current?.(text) : undefined,
  });

  // Backend STT (MediaRecorder → /v1/audio/transcriptions) — only onSilenceDetected, not both (#17)
  const backendSTT = useBackendSTT({
    lang: prefs.speechLang,
    model: prefs.sttModelRef || undefined,
    modelRef: prefs.sttModelRef || undefined,
    silenceThresholdMs: useBackendSTTSource && prefs.autoSendOnSilence ? prefs.silenceThresholdMs : 0,
    onSilenceDetected: useBackendSTTSource ? (text: string) => onSilenceDetectedRef.current?.(text) : undefined,
    onMetrics: useBackendSTTSource ? (audioKB, durationMs) => {
      setMetrics((prev) => ({ ...prev, sttAudioKB: +audioKB.toFixed(1), sttMs: Math.round(durationMs) }));
    } : undefined,
    token: accessToken,
  });

  // Backend TTS (streaming from /v1/audio/speech)
  const streamingTTS = useStreamingTTS({
    model: prefs.ttsModelRef || undefined,
    modelRef: prefs.ttsModelRef || undefined,
    voice: prefs.ttsVoiceId || prefs.ttsVoiceURI || 'alloy',
    speed: prefs.ttsSpeed,
    token: accessToken,
  });

  // Unified STT interface — switch based on preference
  const stt = useBackendSTTSource ? backendSTT : browserSTT;

  // Shorthand refs for STT/TTS control (avoid stale closures)
  const sttStartRef = useRef(stt.start);
  const sttStopRef = useRef(stt.stop);
  const sttResetRef = useRef(stt.resetTranscript);
  const streamingTTSStopRef = useRef(streamingTTS.stop);
  sttStartRef.current = stt.start;
  sttStopRef.current = stt.stop;
  streamingTTSStopRef.current = streamingTTS.stop;
  sttResetRef.current = stt.resetTranscript;

  const sttStart = useCallback(() => sttStartRef.current(), []);
  const sttStop = useCallback(() => sttStopRef.current(), []);
  const sttReset = useCallback(() => sttResetRef.current(), []);

  // No processing-phase effect needed — onSilenceDetected handles everything
  // synchronously (send, pipeline arm, STT stop) in a single callback.

  // ── Streaming TTS Pipeline (RTV-03) ─────────────────────────────

  /** Start the sentence→TTS→audio pipeline for one AI response */
  const startPipeline = useCallback(() => {
    // #2: guard against double pipeline
    if (pipelineActiveRef.current) return;

    const token = accessTokenRef.current;
    if (!token) return;

    // Create playback queue
    const queue = new TTSPlaybackQueue({
      onChunkEnd: () => {
        // RTV-04: notify barge-in detector for cooldown
        bargeInRef.current?.notifyChunkEnd();
      },
      onAllPlayed: () => {
        // H-3: guard against firing after deactivate (phaseRef lags setPhase)
        if (!pipelineActiveRef.current) return;
        pipelineActiveRef.current = false;
        if (phaseRef.current === 'speaking') {
          setPhase('listening');
          sttResetRef.current();
          sttStartRef.current();
        }
      },
    });
    ttsQueueRef.current = queue;

    // Create concurrency pool
    const pool = new TTSConcurrencyPool({
      maxConcurrent: 2,
      onError: (text, err) => {
        console.warn('TTS pipeline: skipping sentence:', text.slice(0, 50), err.message);
      },
      onComplete: (durationMs, audioSizeBytes) => {
        setMetrics((prev) => ({
          ...prev,
          ttsSentenceMs: [...prev.ttsSentenceMs, Math.round(durationMs)],
          ttsAudioKB: prev.ttsAudioKB + audioSizeBytes / 1024,
        }));
      },
    });
    ttsPoolRef.current = pool;

    // Create sentence buffer → feeds sentences to pool → pool result to queue
    const buffer = new SentenceBuffer(
      (sentence) => {
        if (!pipelineActiveRef.current) return;
        console.log('[VoiceMode] Sentence emitted:', sentence.slice(0, 60));
        setMetrics((prev) => ({ ...prev, sentenceCount: prev.sentenceCount + 1 }));
        // First sentence triggers speaking phase
        if (phaseRef.current === 'processing') {
          setPhase('speaking');
        }
        // #1: read latest prefs/token from refs (not stale closure)
        const p = prefsRef.current;
        const t = accessTokenRef.current;
        if (!t) return;
        pool
          .submit({
            text: sentence,
            modelRef: p.ttsModelRef || '',
            voice: p.ttsVoiceId || p.ttsVoiceURI || 'auto',
            speed: p.ttsSpeed,
            token: t,
          })
          .then((audio) => {
            if (pipelineActiveRef.current) {
              queue.enqueue(audio).catch(() => {});
            }
          })
          .catch((err) => {
            // Log TTS errors for debugging (don't crash the pipeline)
            if ((err as Error).message !== 'cancelled') {
              console.error('TTS pipeline error:', (err as Error).message);
            }
          });
      },
    );
    sentenceBufferRef.current = buffer;
    pipelineActiveRef.current = true;
    console.log('[VoiceMode] Pipeline started, ttsModelRef:', prefsRef.current.ttsModelRef, 'voice:', prefsRef.current.ttsVoiceId);
  }, []); // #10: no deps — reads everything from refs

  /** Stop the pipeline and clean up */
  const stopPipeline = useCallback(() => {
    pipelineActiveRef.current = false;
    sentenceBufferRef.current?.cancel();
    ttsPoolRef.current?.cancelAll();
    ttsQueueRef.current?.cancelAll();
    // #4: null refs to prevent stale object retention
    sentenceBufferRef.current = null;
    ttsPoolRef.current = null;
    ttsQueueRef.current = null;
  }, []);

  // Speech recognition — silence detected means user finished speaking.
  // Everything happens synchronously — no React effects for control flow.
  const onSilenceDetected = useCallback(
    (text: string) => {
      if (phaseRef.current !== 'listening') return;
      if (!text.trim()) return;

      // Filter Whisper hallucinations — short garbage from silence/ambient noise
      const cleaned = text.trim().replace(/[.!?,;:\s]+$/g, '').trim();
      if (cleaned.length < 2) {
        console.log('[VoiceMode] Ignoring short/garbage STT result:', JSON.stringify(text));
        return;
      }

      // 1. Stop STT immediately (prevents auto-restart and double-send)
      sttStopRef.current();

      // 2. Set flags and phase
      pendingSendRef.current = true;
      resetMetrics();
      setPhase('processing');

      // 3. Arm the streaming TTS pipeline BEFORE sending (so tokens are captured)
      const p = prefsRef.current;
      if (p.autoTTSResponses && p.ttsSource === 'ai_model') {
        stopPipeline();
        startPipeline();
      }

      // 4. Send the message — use text from callback arg, not from React state
      console.log('[VoiceMode] Sending:', text.trim().slice(0, 60));
      void sendMessageRef.current(text.trim()).catch(() => {
        if (phaseRef.current === 'processing') {
          pendingSendRef.current = false;
          stopPipeline();
          setPhase('listening');
          sttResetRef.current();
          sttStartRef.current();
        }
      });
    },
    [startPipeline, stopPipeline, resetMetrics],
  );
  onSilenceDetectedRef.current = onSilenceDetected;

  // Wire onStreamDeltaRef to feed tokens into the pipeline (runs once on mount — #11)
  const llmFirstTokenRef = useRef<number | null>(null);
  const llmTokenCountRef = useRef(0);
  useEffect(() => {
    if (!onStreamDeltaRef) return;
    onStreamDeltaRef.current = (delta, type) => {
      if (type !== 'content') return;
      if (!pipelineActiveRef.current) return;
      // Track first content token timing
      if (llmFirstTokenRef.current === null) {
        llmFirstTokenRef.current = performance.now();
        console.log('[LLM] First content token received');
        setMetrics((prev) => ({ ...prev, llmFirstTokenMs: 0 }));
      }
      llmTokenCountRef.current++;
      setMetrics((prev) => ({
        ...prev,
        llmTokenCount: llmTokenCountRef.current,
        llmFirstTokenMs: prev.llmFirstTokenMs === null ? 0 : prev.llmFirstTokenMs,
      }));
      sentenceBufferRef.current?.addToken(delta);
    };
    return () => {
      if (onStreamDeltaRef) onStreamDeltaRef.current = null;
    };
  }, [onStreamDeltaRef]);

  // Pipeline is now armed synchronously in onSilenceDetected — no effect needed.

  // Watch streaming status — handle stream-end for both pipeline and legacy TTS paths
  const prevStreamStatus = useRef(streamStatus);
  useEffect(() => {
    const wasStreaming = prevStreamStatus.current === 'streaming';
    prevStreamStatus.current = streamStatus;

    // Only handle stream-end transitions
    if (!wasStreaming || streamStatus !== 'idle') return;
    console.log('[VoiceMode] Stream ended — phase:', phaseRef.current, 'pending:', pendingSendRef.current, 'pipeline:', pipelineActiveRef.current);
    if (phaseRef.current !== 'processing' && phaseRef.current !== 'speaking') return;
    if (!pendingSendRef.current) return; // Ignore manual sends

    pendingSendRef.current = false;
    const responseText = aiResponseText || streamingText;
    setAiResponseText(responseText);

    if (pipelineActiveRef.current) {
      // Streaming pipeline path — flush remaining buffer, close queue
      const llmDuration = llmFirstTokenRef.current ? Math.round(performance.now() - llmFirstTokenRef.current) : null;
      console.log(`[LLM] Stream complete — ${llmTokenCountRef.current} tokens in ${llmDuration ?? '?'}ms`);
      setMetrics((prev) => ({ ...prev, llmTotalMs: llmDuration }));
      llmFirstTokenRef.current = null;
      llmTokenCountRef.current = 0;
      sentenceBufferRef.current?.markStreamComplete();
      ttsQueueRef.current?.close();
      // Pipeline's onAllPlayed callback handles transition to listening
    } else if (prefsRef.current.autoTTSResponses && responseText.trim()) {
      // Legacy path — browser TTS (speak full response at once)
      setPhase('speaking');
      const onTTSEnd = () => {
        if (phaseRef.current === 'speaking') {
          setPhase('listening');
          sttResetRef.current();
          sttStartRef.current();
        }
      };
      const engine = getTTSEngine();
      engine.speak(responseText, onTTSEnd);
    } else {
      setPhase('listening');
      sttReset();
      sttStart();
    }
  }, [streamStatus, streamingText, getTTSEngine, sttStart, sttReset, aiResponseText]);

  // Track streaming text for AI response display
  useEffect(() => {
    if (streamStatus === 'streaming' && streamingText) {
      setAiResponseText(streamingText);
    }
  }, [streamStatus, streamingText]);

  // Pause mic during TTS playback (separate from barge-in to avoid dep issues — H-2)
  useEffect(() => {
    if (phase === 'speaking' && prefsRef.current.pauseMicDuringTTS && stt.isListening) {
      sttStop();
    }
  }, [phase, stt.isListening, sttStop]);

  // Barge-in detection during speaking phase (RTV-04)
  useEffect(() => {
    if (phase !== 'speaking') return;

    let cancelled = false; // C-3: guard against async getUserMedia resolve after cleanup

    const startBargeIn = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true },
        });

        // C-3: if cleaned up while waiting for mic permission, release immediately
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        bargeInStreamRef.current = stream;

        const detector = new BargeInDetector({
          threshold: 40,
          sustainedMs: 200,
          cooldownMs: 400, // H-4: increased from 300 to account for rAF jitter
          onBargeIn: () => {
            if (cancelled) return; // C-2: prevent stale callback
            // C-1: abort LLM stream + reset pending flag
            pendingSendRef.current = false;
            stopStreamRef.current?.(); // C-1: abort in-flight LLM SSE stream
            // Stop everything
            stopPipeline();
            ttsEngineRef.current?.stop();
            streamingTTSStopRef.current();
            // Stop barge-in monitoring
            bargeInRef.current?.stop();
            bargeInRef.current = null;
            if (bargeInStreamRef.current) {
              bargeInStreamRef.current.getTracks().forEach((t) => t.stop());
              bargeInStreamRef.current = null;
            }
            // Transition to listening — user's speech becomes next turn
            setPhase('listening');
            sttResetRef.current();
            sttStartRef.current();
          },
        });
        detector.start(stream);
        bargeInRef.current = detector;
      } catch {
        // Can't get mic — barge-in disabled silently
      }
    };
    void startBargeIn();

    return () => {
      cancelled = true; // C-3
      bargeInRef.current?.stop();
      bargeInRef.current = null;
      if (bargeInStreamRef.current) {
        bargeInStreamRef.current.getTracks().forEach((t) => t.stop());
        bargeInStreamRef.current = null;
      }
    };
  }, [phase, stopPipeline]); // H-2: removed stt.isListening from deps

  // ── Public API ──────────────────────────────────────────────────────

  const activate = useCallback(() => {
    // Stop any ongoing TTS before starting mic
    pendingSendRef.current = false; // #8
    ttsEngineRef.current?.stop();
    streamingTTSStopRef.current();
    stopPipeline();
    setPrefs(loadVoicePrefs());
    setPhase('listening');
    setAiResponseText('');
    resetMetrics();
    sttReset();
    sttStart();
  }, [sttStart, sttReset, stopPipeline, resetMetrics]);

  const deactivate = useCallback(() => {
    pendingSendRef.current = false;
    setPhase('idle');
    sttStop();
    ttsEngineRef.current?.stop();
    streamingTTSStopRef.current();
    stopPipeline();
    bargeInRef.current?.stop();
    bargeInRef.current = null;
    if (bargeInStreamRef.current) {
      bargeInStreamRef.current.getTracks().forEach((t) => t.stop());
      bargeInStreamRef.current = null;
    }
    setAiResponseText('');
  }, [sttStop, stopPipeline]);

  // #7: pause works in both listening and speaking phases
  const pause = useCallback(() => {
    if (phaseRef.current === 'listening' || phaseRef.current === 'speaking') {
      setPhase('paused');
      sttStop();
      // If speaking, pipeline audio continues but mic stays off
      // resume() will wait for audio to finish before restarting mic
    }
  }, [sttStop]);

  const resume = useCallback(() => {
    if (phaseRef.current === 'paused') {
      setPhase('listening');
      sttReset();
      sttStart();
    }
  }, [sttStart, sttReset]);

  const reloadPrefs = useCallback(() => {
    setPrefs(loadVoicePrefs());
  }, []);

  // Cleanup on unmount (M-2: includes barge-in stream cleanup)
  useEffect(() => {
    return () => {
      sttStopRef.current();
      ttsEngineRef.current?.stop();
      streamingTTSStopRef.current();
      pipelineActiveRef.current = false;
      sentenceBufferRef.current?.cancel();
      ttsPoolRef.current?.cancelAll();
      ttsQueueRef.current?.dispose();
      bargeInRef.current?.stop();
      bargeInRef.current = null;
      bargeInStreamRef.current?.getTracks().forEach((t) => t.stop());
      bargeInStreamRef.current = null;
    };
  }, []);

  return {
    phase,
    isActive: phase !== 'idle',
    supported: useBackendSTTSource ? MEDIA_RECORDER_SUPPORTED : SPEECH_RECOGNITION_SUPPORTED,
    userTranscript: stt.transcript,
    interimText: prefs.showInterimResults ? stt.interimTranscript : '',
    aiResponseText,
    error: stt.error,
    activate,
    deactivate,
    pause,
    resume,
    reloadPrefs,
    metrics,
  };
}
