/**
 * useAutoTTS — automatically plays TTS for new assistant messages when Voice Assist is enabled.
 * Watches for completed (non-streaming) assistant messages and calls TTS via provider-registry proxy.
 */
import { useEffect, useRef, useCallback, useState } from 'react';
import { useAuth } from '@/auth';
import { TTSPlaybackQueue } from '@/lib/TTSPlaybackQueue';
import { loadVoicePrefs } from '../voicePrefs';
import type { ChatMessage } from '../types';

export interface AutoTTSControls {
  stop: () => void;
  isPlaying: boolean;
  playingMessageId: string | null;
}

export function useAutoTTS(
  messages: ChatMessage[],
  isStreaming: boolean,
  voiceModeActive: boolean = false,
): AutoTTSControls {
  const { accessToken } = useAuth();
  const queueRef = useRef<TTSPlaybackQueue | null>(null);
  const lastPlayedIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const initialCountRef = useRef<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playingMessageId, setPlayingMessageId] = useState<string | null>(null);

  // Track initial message count to skip history messages
  if (initialCountRef.current === null) {
    initialCountRef.current = messages.length;
  }

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    queueRef.current?.cancelAll();
    setIsPlaying(false);
    setPlayingMessageId(null);
  }, []);

  // Use messages.length as dep instead of messages array ref
  const msgCount = messages.length;

  useEffect(() => {
    if (isStreaming) return;
    // Voice mode handles its own TTS — don't double-play
    if (voiceModeActive) return;
    // Skip if no new messages beyond initial load
    if (initialCountRef.current !== null && msgCount <= initialCountRef.current) return;

    const prefs = loadVoicePrefs();
    if (!prefs.voiceAssistAutoTTS || !prefs.ttsModelRef) return;

    const lastMsg = messages[messages.length - 1];
    if (!lastMsg || lastMsg.role !== 'assistant') return;
    if (lastMsg.message_id === lastPlayedIdRef.current) return;
    lastPlayedIdRef.current = lastMsg.message_id;

    const text = lastMsg.content;
    if (!text || text.trim().length < 5) return;

    const playTTS = async () => {
      if (!accessToken) return;

      if (!queueRef.current) {
        queueRef.current = new TTSPlaybackQueue({
          onAllPlayed: () => {
            setIsPlaying(false);
            setPlayingMessageId(null);
          },
        });
      }

      queueRef.current.cancelAll();
      abortRef.current?.abort();
      const abort = new AbortController();
      abortRef.current = abort;

      setIsPlaying(true);
      setPlayingMessageId(lastMsg.message_id);

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
              input: text.slice(0, 4096),
              voice: prefs.ttsVoiceId || 'af_heart',
              response_format: 'mp3',
            }),
            signal: abort.signal,
          },
        );

        if (!resp.ok || !resp.body) {
          setIsPlaying(false);
          setPlayingMessageId(null);
          return;
        }

        const reader = resp.body.getReader();
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            await queueRef.current?.enqueue(value.buffer);
          }
          queueRef.current?.close();
        } finally {
          reader.releaseLock();
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setIsPlaying(false);
          setPlayingMessageId(null);
        }
      }
    };

    void playTTS();
  }, [msgCount, isStreaming, voiceModeActive, accessToken]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      queueRef.current?.dispose();
      queueRef.current = null;
    };
  }, []);

  return { stop, isPlaying, playingMessageId };
}
