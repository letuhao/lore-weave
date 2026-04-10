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
import { useAuth } from '@/auth';
import { loadVoicePrefs, type VoicePrefs } from '../voicePrefs';

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
}

export function useVoiceMode({
  sendMessage,
  streamStatus,
  streamingText,
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

  // Browser STT (Web Speech API)
  const browserSTT = useSpeechRecognition({
    lang: prefs.speechLang,
    continuous: true,
    interimResults: true,
    silenceThresholdMs: prefs.autoSendOnSilence ? prefs.silenceThresholdMs : 0,
    onSilenceDetected,
  });

  // Backend STT (MediaRecorder → /v1/audio/transcriptions)
  const backendSTT = useBackendSTT({
    lang: prefs.speechLang,
    model: prefs.sttModelRef || undefined,
    silenceThresholdMs: prefs.autoSendOnSilence ? prefs.silenceThresholdMs : 0,
    onSilenceDetected,
    onFinalTranscript: onSilenceDetected, // Same handler — backend STT fires once per recording
    token: accessToken,
  });

  // Backend TTS (streaming from /v1/audio/speech)
  const streamingTTS = useStreamingTTS({
    model: prefs.ttsModelRef || undefined,
    voice: prefs.ttsVoiceURI || 'alloy',
    speed: prefs.ttsSpeed,
    token: accessToken,
  });

  // Unified STT interface — switch based on preference
  const stt = useBackendSTTSource ? backendSTT : browserSTT;

  // Shorthand refs for STT control (avoid stale closures)
  const sttStartRef = useRef(stt.start);
  const sttStopRef = useRef(stt.stop);
  const sttResetRef = useRef(stt.resetTranscript);
  sttStartRef.current = stt.start;
  sttStopRef.current = stt.stop;
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

  // Watch streaming status — when AI response completes, auto-TTS
  // Only act if this was a voice-initiated send (pendingSendRef) — Issue #5, #6
  const prevStreamStatus = useRef(streamStatus);
  useEffect(() => {
    const wasStreaming = prevStreamStatus.current === 'streaming';
    prevStreamStatus.current = streamStatus;

    if (!wasStreaming || streamStatus !== 'idle') return;
    if (phaseRef.current !== 'processing') return;
    if (!pendingSendRef.current) return; // Ignore manual sends — Issue #5

    // AI response is done
    pendingSendRef.current = false;
    const responseText = aiResponseText || streamingText;
    setAiResponseText(responseText);

    if (prefs.autoTTSResponses && responseText.trim()) {
      // Speak the response — use backend or browser TTS
      setPhase('speaking');
      const onTTSEnd = () => {
        if (phaseRef.current === 'speaking') {
          setPhase('listening');
          sttReset();
          sttStart();
        }
      };
      if (useBackendTTSSource) {
        streamingTTS.speak(responseText, onTTSEnd);
      } else {
        const engine = getTTSEngine();
        engine.speak(responseText, onTTSEnd);
      }
    } else {
      // No TTS — go straight back to listening
      setPhase('listening');
      sttReset();
      sttStart();
    }
  }, [streamStatus, streamingText, prefs.autoTTSResponses, getTTSEngine, sttStart, sttReset, aiResponseText]);

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
    setPrefs(loadVoicePrefs()); // Reload latest prefs
    setPhase('listening');
    setAiResponseText('');
    sttReset();
    sttStart();
  }, [sttStart, sttReset]);

  const deactivate = useCallback(() => {
    setPhase('idle');
    sttStop();
    ttsEngineRef.current?.stop();
    streamingTTS.stop();
    setAiResponseText('');
  }, [sttStop, streamingTTS]);

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
