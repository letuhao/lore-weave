import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { chatApi } from '../api';
import type { ChatMessage } from '../types';

type StreamStatus = 'idle' | 'streaming' | 'error';

/**
 * Unified hook: owns message list + SSE streaming for send/edit/regenerate.
 * Replaces both useMessages + useStreamingEdit + @ai-sdk/react useChat.
 */
export function useChatMessages(sessionId: string | null) {
  const { accessToken } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [streamStatus, setStreamStatus] = useState<StreamStatus>('idle');
  const abortRef = useRef<AbortController | null>(null);

  // ── Fetch messages on session change ──────────────────────────────────────────

  const fetchMessages = useCallback(async () => {
    if (!accessToken || !sessionId) {
      setMessages([]);
      return;
    }
    setIsLoading(true);
    try {
      const res = await chatApi.listMessages(accessToken, sessionId);
      setMessages(res.items);
    } catch {
      // Silently fail — toast is handled at component level
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, sessionId]);

  useEffect(() => {
    void fetchMessages();
  }, [fetchMessages]);

  // ── SSE streaming ─────────────────────────────────────────────────────────────

  const streamPost = useCallback(
    async (content: string, editFromSequence?: number): Promise<string> => {
      if (!accessToken || !sessionId) throw new Error('Not ready');

      // Abort any in-progress stream
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setStreamingText('');
      setStreamStatus('streaming');

      let accumulated = '';

      try {
        const body: Record<string, unknown> = { content };
        if (editFromSequence != null) {
          body.edit_from_sequence = editFromSequence;
        }

        const res = await fetch(chatApi.messagesUrl(sessionId), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify(body),
          signal: controller.signal,
        });

        if (!res.ok) {
          const detail = await res.text().catch(() => res.statusText);
          throw new Error(`${res.status}: ${detail}`);
        }

        const reader = res.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        let buffer = '';

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
              if (event.type === 'text-delta' && event.delta) {
                accumulated += event.delta;
                setStreamingText(accumulated);
              } else if (event.type === 'error') {
                throw new Error(event.errorText || 'Stream error');
              }
            } catch (parseErr) {
              if (parseErr instanceof SyntaxError) continue;
              throw parseErr;
            }
          }
        }

        setStreamStatus('idle');
        // Refetch messages to get persisted data (tokens, message_id, etc.)
        void fetchMessages();
        return accumulated;
      } catch (err) {
        if ((err as Error).name === 'AbortError') {
          setStreamStatus('idle');
          return accumulated;
        }
        setStreamStatus('error');
        throw err;
      } finally {
        abortRef.current = null;
        setStreamingText('');
      }
    },
    [accessToken, sessionId, fetchMessages],
  );

  // ── Public API ────────────────────────────────────────────────────────────────

  /** Send a new message (normal flow) */
  const send = useCallback(
    (content: string) => {
      // Optimistically add user message to the list
      const optimistic: ChatMessage = {
        message_id: `opt-${Date.now()}`,
        session_id: sessionId ?? '',
        owner_user_id: '',
        role: 'user',
        content,
        content_parts: null,
        sequence_num: messages.length + 1,
        input_tokens: null,
        output_tokens: null,
        model_ref: null,
        is_error: false,
        error_detail: null,
        parent_message_id: null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimistic]);
      return streamPost(content);
    },
    [sessionId, messages.length, streamPost],
  );

  /** Edit a user message and re-run from that point */
  const edit = useCallback(
    (content: string, editFromSequence: number) => {
      // Truncate messages up to (but not including) the edited sequence
      setMessages((prev) => {
        const truncated = prev.filter((m) => m.sequence_num < editFromSequence);
        const optimistic: ChatMessage = {
          message_id: `edit-${Date.now()}`,
          session_id: sessionId ?? '',
          owner_user_id: '',
          role: 'user',
          content,
          content_parts: null,
          sequence_num: editFromSequence,
          input_tokens: null,
          output_tokens: null,
          model_ref: null,
          is_error: false,
          error_detail: null,
          parent_message_id: null,
          created_at: new Date().toISOString(),
        };
        return [...truncated, optimistic];
      });
      return streamPost(content, editFromSequence);
    },
    [sessionId, streamPost],
  );

  /** Regenerate the assistant response after a given user message */
  const regenerate = useCallback(
    (userContent: string, userSequenceNum: number) => {
      // Keep messages up to and including the user message
      setMessages((prev) => prev.filter((m) => m.sequence_num <= userSequenceNum));
      // edit_from_sequence = the user message sequence (server will delete after it and re-run)
      return streamPost(userContent, userSequenceNum);
    },
    [streamPost],
  );

  /** Stop the current stream */
  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return {
    messages,
    isLoading,
    streamingText,
    streamStatus,
    isStreaming: streamStatus === 'streaming',
    send,
    edit,
    regenerate,
    stop,
    refresh: fetchMessages,
  };
}
