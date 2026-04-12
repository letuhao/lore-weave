/**
 * useAutoTTS — automatically generates TTS for new assistant messages via backend.
 * Calls POST /generate-tts which runs TTS server-side, stores audio in S3,
 * and streams audio chunks back for client playback. Same pipeline as Voice Mode.
 *
 * After completion, the message's content_parts.voice_tts_sentences is set,
 * so AudioReplayPlayer will show on next render.
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
  voiceAssistEnabled: boolean = false,
  onTTSComplete?: () => void,
): AutoTTSControls {
  const { accessToken } = useAuth();
  const queueRef = useRef<TTSPlaybackQueue | null>(null);
  const lastPlayedIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const initialCountRef = useRef<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playingMessageId, setPlayingMessageId] = useState<string | null>(null);
  const onTTSCompleteRef = useRef(onTTSComplete);
  onTTSCompleteRef.current = onTTSComplete;

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

  const msgCount = messages.length;
  const lastMsgId = messages[messages.length - 1]?.message_id ?? '';

  useEffect(() => {
    if (isStreaming) return;
    if (voiceModeActive) return;
    if (!voiceAssistEnabled) return;
    if (initialCountRef.current !== null && msgCount <= initialCountRef.current) return;

    const prefs = loadVoicePrefs();
    if (!prefs.voiceAssistAutoTTS || !prefs.ttsModelRef) return;

    const lastMsg = messages[messages.length - 1];
    if (!lastMsg || lastMsg.role !== 'assistant') return;
    if (lastMsg.message_id === lastPlayedIdRef.current) return;
    // Skip optimistic/placeholder messages — they don't exist in the DB yet.
    // Don't set lastPlayedIdRef so we retry when the real message arrives via refresh.
    if (lastMsg.message_id.startsWith('opt-') || lastMsg.message_id.startsWith('done-')
        || lastMsg.message_id.startsWith('edit-')) return;
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
            onTTSCompleteRef.current?.();
          },
        });
      }

      queueRef.current.cancelAll();
      abortRef.current?.abort();
      const abort = new AbortController();
      abortRef.current = abort;

      setIsPlaying(true);
      setPlayingMessageId(lastMsg.message_id);

      // Accumulate binary audio per sentence for proper MP3 decoding
      const sentenceChunks = new Map<number, Uint8Array[]>();

      try {
        const apiBase = import.meta.env.VITE_API_BASE || '';
        const resp = await fetch(
          `${apiBase}/v1/chat/sessions/${lastMsg.session_id}/messages/${lastMsg.message_id}/generate-tts`,
          {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${accessToken}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              tts_model_source: 'user_model',
              tts_model_ref: prefs.ttsModelRef,
              tts_voice: prefs.ttsVoiceId || 'af_heart',
            }),
            signal: abort.signal,
          },
        );

        if (!resp.ok || !resp.body) {
          setIsPlaying(false);
          setPlayingMessageId(null);
          return;
        }

        // Parse SSE stream — same format as Voice Mode
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() ?? '';

            for (const line of lines) {
              if (!line.startsWith('data: ')) continue;
              const payload = line.slice(6).trim();
              if (payload === '[DONE]') continue;

              try {
                const event = JSON.parse(payload);
                if (event.type === 'audio-chunk') {
                  if (event.data) {
                    const binary = Uint8Array.from(atob(event.data), (c) => c.charCodeAt(0));
                    const key = event.sentenceIndex;
                    if (!sentenceChunks.has(key)) sentenceChunks.set(key, []);
                    sentenceChunks.get(key)!.push(binary);
                  }
                  if (event.final) {
                    // Sentence complete — combine chunks, enqueue for playback
                    const chunks = sentenceChunks.get(event.sentenceIndex);
                    sentenceChunks.delete(event.sentenceIndex);
                    if (chunks && chunks.length > 0) {
                      const totalLen = chunks.reduce((sum, c) => sum + c.length, 0);
                      const combined = new Uint8Array(totalLen);
                      let offset = 0;
                      for (const chunk of chunks) {
                        combined.set(chunk, offset);
                        offset += chunk.length;
                      }
                      queueRef.current?.enqueue(combined.buffer);
                    }
                  }
                } else if (event.type === 'finish-tts') {
                  queueRef.current?.close();
                } else if (event.type === 'error') {
                  setIsPlaying(false);
                  setPlayingMessageId(null);
                }
              } catch {
                // Malformed JSON — skip
              }
            }
          }
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
  }, [msgCount, lastMsgId, isStreaming, voiceModeActive, voiceAssistEnabled, accessToken]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      queueRef.current?.dispose();
      queueRef.current = null;
    };
  }, []);

  return { stop, isPlaying, playingMessageId };
}
