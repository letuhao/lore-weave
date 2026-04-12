/**
 * useAutoTTS — automatically plays TTS for new assistant messages when Voice Assist is enabled.
 * Watches for completed (non-streaming) assistant messages and calls TTS via provider-registry proxy.
 */
import { useEffect, useRef, useCallback } from 'react';
import { useAuth } from '@/auth';
import { TTSPlaybackQueue } from '@/lib/TTSPlaybackQueue';
import { loadVoicePrefs } from '../voicePrefs';
import type { ChatMessage } from '../types';

export interface AutoTTSControls {
  /** Stop any currently playing TTS */
  stop: () => void;
  /** Whether TTS is currently playing */
  isPlaying: boolean;
  /** Message ID of the currently playing message (null if not playing) */
  playingMessageId: string | null;
}

export function useAutoTTS(
  messages: ChatMessage[],
  isStreaming: boolean,
): AutoTTSControls {
  const { accessToken } = useAuth();
  const queueRef = useRef<TTSPlaybackQueue | null>(null);
  const lastPlayedIdRef = useRef<string | null>(null);
  const playingIdRef = useRef<string | null>(null);
  const isPlayingRef = useRef(false);

  const stop = useCallback(() => {
    queueRef.current?.cancelAll();
    isPlayingRef.current = false;
    playingIdRef.current = null;
  }, []);

  useEffect(() => {
    // Only trigger when streaming finishes (new message completed)
    if (isStreaming) return;

    const prefs = loadVoicePrefs();
    if (!prefs.voiceAssistAutoTTS || !prefs.ttsModelRef) return;

    // Find the last assistant message
    const lastMsg = [...messages].reverse().find((m) => m.role === 'assistant');
    if (!lastMsg) return;
    if (lastMsg.message_id === lastPlayedIdRef.current) return; // Already played
    lastPlayedIdRef.current = lastMsg.message_id;

    // Play TTS for this message
    const text = lastMsg.content;
    if (!text || text.trim().length < 5) return;

    const playTTS = async () => {
      if (!accessToken) return;

      // Create queue if needed
      if (!queueRef.current) {
        queueRef.current = new TTSPlaybackQueue({
          onAllPlayed: () => {
            isPlayingRef.current = false;
            playingIdRef.current = null;
          },
        });
      }

      queueRef.current.cancelAll();
      isPlayingRef.current = true;
      playingIdRef.current = lastMsg.message_id;

      try {
        const apiBase = import.meta.env.VITE_API_BASE || '';
        const params = new URLSearchParams({
          model_source: 'user_model',
          model_ref: prefs.ttsModelRef,
        });
        const resp = await fetch(
          `${apiBase}/v1/model-registry/proxy/v1/audio/speech?${params}`,
          {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${accessToken}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              input: text.slice(0, 4096), // Cap length
              voice: prefs.ttsVoiceId || 'af_heart',
              response_format: 'mp3',
            }),
          },
        );

        if (!resp.ok || !resp.body) {
          isPlayingRef.current = false;
          playingIdRef.current = null;
          return;
        }

        // Stream audio chunks to playback queue
        const reader = resp.body.getReader();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (!isPlayingRef.current) { reader.cancel(); break; } // Stopped
          await queueRef.current?.enqueue(value.buffer);
        }
        queueRef.current?.close();
      } catch {
        isPlayingRef.current = false;
        playingIdRef.current = null;
      }
    };

    void playTTS();
  }, [messages, isStreaming, accessToken]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      queueRef.current?.dispose();
      queueRef.current = null;
    };
  }, []);

  return {
    stop,
    isPlaying: isPlayingRef.current,
    playingMessageId: playingIdRef.current,
  };
}
