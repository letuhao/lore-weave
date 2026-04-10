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
import { BrowserTTSEngine } from '@/hooks/engines/BrowserTTSEngine';
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
  const [phase, setPhase] = useState<VoicePhase>('idle');
  const [aiResponseText, setAiResponseText] = useState('');
  const [prefs, setPrefs] = useState<VoicePrefs>(loadVoicePrefs);

  const phaseRef = useRef<VoicePhase>('idle');
  const ttsEngineRef = useRef<BrowserTTSEngine | null>(null);
  const pendingSendRef = useRef(false);

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
  const stt = useSpeechRecognition({
    lang: prefs.speechLang,
    continuous: true,
    interimResults: true,
    silenceThresholdMs: prefs.autoSendOnSilence ? prefs.silenceThresholdMs : 0,
    onSilenceDetected: useCallback(
      (text: string) => {
        if (phaseRef.current !== 'listening') return;
        if (!prefs.autoSendOnSilence) return;
        if (!text.trim()) return;

        // Transition to processing — send the message
        pendingSendRef.current = true;
        setPhase('processing');
        sttStop();

        void sendMessage(text.trim()).catch(() => {
          // On error, go back to listening
          if (phaseRef.current === 'processing') {
            setPhase('listening');
            sttStart();
          }
        });
      },
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [prefs.autoSendOnSilence, prefs.silenceThresholdMs],
    ),
  });

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

  // Watch streaming status — when AI response completes, auto-TTS
  const prevStreamStatus = useRef(streamStatus);
  useEffect(() => {
    const wasStreaming = prevStreamStatus.current === 'streaming';
    prevStreamStatus.current = streamStatus;

    if (!wasStreaming || streamStatus !== 'idle') return;
    if (phaseRef.current !== 'processing') return;

    // AI response is done
    pendingSendRef.current = false;
    const responseText = aiResponseText || streamingText;
    setAiResponseText(responseText);

    if (prefs.autoTTSResponses && responseText.trim()) {
      // Speak the response
      setPhase('speaking');
      const engine = getTTSEngine();
      engine.speak(responseText, () => {
        // TTS finished — resume listening
        if (phaseRef.current === 'speaking') {
          setPhase('listening');
          sttReset();
          sttStart();
        }
      });
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
    setAiResponseText('');
  }, [sttStop]);

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
    supported: SPEECH_RECOGNITION_SUPPORTED,
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
