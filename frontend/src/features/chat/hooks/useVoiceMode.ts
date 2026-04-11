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
import { useAuth } from '@/auth';
import { loadVoicePrefs, type VoicePrefs } from '../voicePrefs';
import type { OnStreamDelta } from './useChatMessages';

export type VoicePhase = 'idle' | 'listening' | 'processing' | 'speaking' | 'paused';

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
}

interface UseVoiceModeOptions {
  /** Function to send a message — should return the AI response text */
  sendMessage: (content: string) => Promise<string>;
  /** Current streaming status from chat hook */
  streamStatus: 'idle' | 'streaming' | 'error';
  /** Current streaming text (live AI response) */
  streamingText: string;
  /** Ref to set the per-token delta callback on the chat hook */
  onStreamDeltaRef?: React.MutableRefObject<OnStreamDelta | null>;
}

export function useVoiceMode({
  sendMessage,
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

  // Ref pattern for sendMessage — avoids stale closure in callbacks (Issue #1, #2)
  const sendMessageRef = useRef(sendMessage);
  sendMessageRef.current = sendMessage;

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

  // Speech recognition hook (own instance via factory pattern)
  const onSilenceDetected = useCallback(
    (text: string) => {
      if (phaseRef.current !== 'listening') return;
      if (!text.trim()) return;

      // Transition to processing — send the message
      pendingSendRef.current = true;
      setPhase('processing');
      // sttStop called below after hook is defined
    },
    [],
  );

  // Browser STT (Web Speech API) — pass callbacks only when active (#15)
  const browserSTT = useSpeechRecognition({
    lang: prefs.speechLang,
    continuous: true,
    interimResults: true,
    silenceThresholdMs: !useBackendSTTSource && prefs.autoSendOnSilence ? prefs.silenceThresholdMs : 0,
    onSilenceDetected: !useBackendSTTSource ? onSilenceDetected : undefined,
  });

  // Backend STT (MediaRecorder → /v1/audio/transcriptions) — only onSilenceDetected, not both (#17)
  const backendSTT = useBackendSTT({
    lang: prefs.speechLang,
    model: prefs.sttModelRef || undefined,
    modelRef: prefs.sttModelRef || undefined,
    silenceThresholdMs: useBackendSTTSource && prefs.autoSendOnSilence ? prefs.silenceThresholdMs : 0,
    onSilenceDetected: useBackendSTTSource ? onSilenceDetected : undefined,
    token: accessToken,
  });

  // Backend TTS (streaming from /v1/audio/speech)
  const streamingTTS = useStreamingTTS({
    model: prefs.ttsModelRef || undefined,
    modelRef: prefs.ttsModelRef || undefined,
    voice: prefs.ttsVoiceURI || 'alloy',
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

  // When phase transitions to 'processing', stop STT and send the transcript
  useEffect(() => {
    if (phase !== 'processing' || !pendingSendRef.current) return;
    sttStop();
    const text = stt.transcript || stt.interimTranscript;
    if (!text.trim()) {
      setPhase('listening');
      pendingSendRef.current = false;
      sttStart();
      return;
    }
    void sendMessageRef.current(text.trim()).catch(() => {
      if (phaseRef.current === 'processing') {
        pendingSendRef.current = false;
        setPhase('listening');
        sttReset();
        sttStart();
      }
    });
  }, [phase, stt.transcript, stt.interimTranscript, sttStop, sttStart, sttReset]);

  // ── Streaming TTS Pipeline (RTV-03) ─────────────────────────────

  /** Start the sentence→TTS→audio pipeline for one AI response */
  const startPipeline = useCallback(() => {
    if (!accessToken || !useBackendTTSSource || !prefs.autoTTSResponses) return;

    // Create playback queue
    const queue = new TTSPlaybackQueue({
      onAllPlayed: () => {
        pipelineActiveRef.current = false;
        if (phaseRef.current === 'speaking') {
          setPhase('listening');
          sttReset();
          sttStart();
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
    });
    ttsPoolRef.current = pool;

    // Create sentence buffer → feeds sentences to pool → pool result to queue
    const buffer = new SentenceBuffer(
      (sentence) => {
        if (!pipelineActiveRef.current) return;
        // First sentence triggers speaking phase
        if (phaseRef.current === 'processing') {
          setPhase('speaking');
        }
        // Submit sentence to TTS pool
        pool
          .submit({
            text: sentence,
            modelRef: prefs.ttsModelRef || '',
            voice: prefs.ttsVoiceURI || 'auto',
            speed: prefs.ttsSpeed,
            token: accessToken!,
          })
          .then((audio) => {
            if (pipelineActiveRef.current) {
              queue.enqueue(audio).catch(() => {});
            }
          })
          .catch(() => {
            // Sentence skipped (cancelled or failed) — pipeline continues
          });
      },
    );
    sentenceBufferRef.current = buffer;
    pipelineActiveRef.current = true;
  }, [accessToken, useBackendTTSSource, prefs, sttStart, sttReset]);

  /** Stop the pipeline and clean up */
  const stopPipeline = useCallback(() => {
    pipelineActiveRef.current = false;
    sentenceBufferRef.current?.cancel();
    ttsPoolRef.current?.cancelAll();
    ttsQueueRef.current?.cancelAll();
  }, []);

  // Wire onStreamDeltaRef to feed tokens into the pipeline
  useEffect(() => {
    if (!onStreamDeltaRef) return;
    onStreamDeltaRef.current = (delta, type) => {
      if (type !== 'content') return; // Skip reasoning tokens
      if (!pipelineActiveRef.current) return;
      sentenceBufferRef.current?.addToken(delta);
    };
    return () => {
      if (onStreamDeltaRef) onStreamDeltaRef.current = null;
    };
  }, [onStreamDeltaRef]);

  // Watch streaming status — handle both pipeline and legacy TTS paths
  const prevStreamStatus = useRef(streamStatus);
  useEffect(() => {
    const wasStreaming = prevStreamStatus.current === 'streaming';
    const wasIdle = prevStreamStatus.current === 'idle';
    prevStreamStatus.current = streamStatus;

    // Stream started — start pipeline if backend TTS
    if (wasIdle && streamStatus === 'streaming' && pendingSendRef.current && useBackendTTSSource) {
      startPipeline();
    }

    // Stream ended
    if (!wasStreaming || streamStatus !== 'idle') return;
    if (phaseRef.current !== 'processing' && phaseRef.current !== 'speaking') return;
    if (!pendingSendRef.current) return;

    pendingSendRef.current = false;
    const responseText = aiResponseText || streamingText;
    setAiResponseText(responseText);

    if (pipelineActiveRef.current) {
      // Streaming pipeline path — flush remaining buffer, close queue
      sentenceBufferRef.current?.markStreamComplete();
      ttsQueueRef.current?.close();
      // Pipeline's onAllPlayed callback handles transition to listening
    } else if (prefs.autoTTSResponses && responseText.trim()) {
      // Legacy path — browser TTS (speak full response at once)
      setPhase('speaking');
      const onTTSEnd = () => {
        if (phaseRef.current === 'speaking') {
          setPhase('listening');
          sttReset();
          sttStart();
        }
      };
      const engine = getTTSEngine();
      engine.speak(responseText, onTTSEnd);
    } else {
      setPhase('listening');
      sttReset();
      sttStart();
    }
  }, [streamStatus, streamingText, prefs.autoTTSResponses, useBackendTTSSource, getTTSEngine, sttStart, sttReset, aiResponseText, startPipeline]);

  // Track streaming text for AI response display
  useEffect(() => {
    if (streamStatus === 'streaming' && streamingText) {
      setAiResponseText(streamingText);
    }
  }, [streamStatus, streamingText]);

  // Pause mic during TTS playback
  useEffect(() => {
    if (phase === 'speaking' && prefs.pauseMicDuringTTS && stt.isListening) {
      sttStop();
    }
  }, [phase, prefs.pauseMicDuringTTS, stt.isListening, sttStop]);

  // ── Public API ──────────────────────────────────────────────────────

  const activate = useCallback(() => {
    // Stop any ongoing TTS before starting mic
    ttsEngineRef.current?.stop();
    streamingTTSStopRef.current();
    stopPipeline();
    setPrefs(loadVoicePrefs());
    setPhase('listening');
    setAiResponseText('');
    sttReset();
    sttStart();
  }, [sttStart, sttReset, stopPipeline]);

  const deactivate = useCallback(() => {
    setPhase('idle');
    sttStop();
    ttsEngineRef.current?.stop();
    streamingTTSStopRef.current();
    stopPipeline();
    setAiResponseText('');
  }, [sttStop, stopPipeline]);

  const pause = useCallback(() => {
    if (phaseRef.current === 'listening') {
      setPhase('paused');
      sttStop();
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

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      sttStopRef.current();
      ttsEngineRef.current?.stop();
      streamingTTSStopRef.current();
      pipelineActiveRef.current = false;
      sentenceBufferRef.current?.cancel();
      ttsPoolRef.current?.cancelAll();
      ttsQueueRef.current?.dispose();
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
  };
}
