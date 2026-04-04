import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { chatApi } from '../api';
import type { ChatMessage } from '../types';

type StreamStatus = 'idle' | 'streaming' | 'error';
type StreamPhase = 'idle' | 'thinking' | 'responding';

/**
 * Unified hook: owns message list + SSE streaming for send/edit/regenerate.
 * Supports reasoning-delta (thinking) and text-delta (content) events.
 */
export function useChatMessages(sessionId: string | null) {
  const { accessToken } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [streamingReasoning, setStreamingReasoning] = useState('');
  const [streamPhase, setStreamPhase] = useState<StreamPhase>('idle');
  const [thinkingElapsed, setThinkingElapsed] = useState(0);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>('idle');
  const abortRef = useRef<AbortController | null>(null);
  const thinkingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const thinkingStartRef = useRef<number>(0);

  // ── Fetch messages on session change ──────────────────────────────────────────

  const fetchMessages = useCallback(async (branchId?: number) => {
    if (!accessToken || !sessionId) {
      setMessages([]);
      return;
    }
    setIsLoading(true);
    try {
      const res = await chatApi.listMessages(accessToken, sessionId, undefined, branchId);
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
    async (content: string, editFromSequence?: number, thinking?: boolean): Promise<string> => {
      if (!accessToken || !sessionId) throw new Error('Not ready');

      // Abort any in-progress stream
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setStreamingText('');
      setStreamingReasoning('');
      setStreamPhase('idle');
      setThinkingElapsed(0);
      setStreamStatus('streaming');

      let accumulatedContent = '';
      let accumulatedReasoning = '';
      let streamMessageId: string | null = null;
      let streamUsage: { promptTokens?: number; completionTokens?: number } = {};
      let streamTiming: { responseTimeMs?: number; timeToFirstTokenMs?: number } = {};

      // Thinking timer
      function startThinkingTimer() {
        thinkingStartRef.current = Date.now();
        thinkingTimerRef.current = setInterval(() => {
          setThinkingElapsed((Date.now() - thinkingStartRef.current) / 1000);
        }, 100);
      }
      function stopThinkingTimer() {
        if (thinkingTimerRef.current) {
          clearInterval(thinkingTimerRef.current);
          thinkingTimerRef.current = null;
        }
      }

      try {
        const body: Record<string, unknown> = { content };
        if (editFromSequence != null) {
          body.edit_from_sequence = editFromSequence;
        }
        if (thinking != null) {
          body.thinking = thinking;
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
              if (event.type === 'reasoning-delta' && event.delta) {
                if (accumulatedReasoning === '') {
                  setStreamPhase('thinking');
                  startThinkingTimer();
                }
                accumulatedReasoning += event.delta;
                setStreamingReasoning(accumulatedReasoning);
              } else if (event.type === 'text-delta' && event.delta) {
                if (accumulatedContent === '' && accumulatedReasoning !== '') {
                  // Transition from thinking → responding
                  stopThinkingTimer();
                  setStreamPhase('responding');
                } else if (accumulatedContent === '') {
                  setStreamPhase('responding');
                }
                accumulatedContent += event.delta;
                setStreamingText(accumulatedContent);
              } else if (event.type === 'data' && event.data?.[0]) {
                streamMessageId = event.data[0].message_id || null;
              } else if (event.type === 'finish-message') {
                streamUsage = event.usage || {};
                streamTiming = event.timing || {};
              } else if (event.type === 'error') {
                throw new Error(event.errorText || 'Stream error');
              }
            } catch (parseErr) {
              if (parseErr instanceof SyntaxError) continue;
              throw parseErr;
            }
          }
        }

        stopThinkingTimer();
        setStreamStatus('idle');
        setStreamPhase('idle');

        // Seamless append: add completed assistant message to list without refetch
        const assistantMessage: ChatMessage = {
          message_id: streamMessageId || `done-${Date.now()}`,
          session_id: sessionId ?? '',
          owner_user_id: '',
          role: 'assistant',
          content: accumulatedContent,
          content_parts: {
            ...(accumulatedReasoning ? { reasoning: accumulatedReasoning, reasoning_length: accumulatedReasoning.length } : {}),
            ...(streamTiming.responseTimeMs != null ? { response_time_ms: streamTiming.responseTimeMs } : {}),
            ...(streamTiming.timeToFirstTokenMs != null ? { time_to_first_token_ms: streamTiming.timeToFirstTokenMs } : {}),
          },
          sequence_num: messages.length + 2, // user msg + this
          branch_id: 0,
          input_tokens: streamUsage.promptTokens ?? null,
          output_tokens: streamUsage.completionTokens ?? null,
          model_ref: null,
          is_error: false,
          error_detail: null,
          parent_message_id: null,
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, assistantMessage]);

        return accumulatedContent;
      } catch (err) {
        stopThinkingTimer();
        if ((err as Error).name === 'AbortError') {
          setStreamStatus('idle');
          setStreamPhase('idle');
          // Refetch to pick up any partially persisted messages from backend
          void fetchMessages();
          return accumulatedContent;
        }
        setStreamStatus('error');
        setStreamPhase('idle');
        // Refetch on error too — backend may have persisted partial data
        void fetchMessages();
        throw err;
      } finally {
        stopThinkingTimer();
        abortRef.current = null;
        setStreamingText('');
        setStreamingReasoning('');
      }
    },
    [accessToken, sessionId, fetchMessages],
  );

  // ── Public API ────────────────────────────────────────────────────────────────

  /** Send a new message (normal flow) */
  const send = useCallback(
    (content: string, thinking?: boolean) => {
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
        branch_id: 0,
        parent_message_id: null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimistic]);
      return streamPost(content, undefined, thinking);
    },
    [sessionId, messages.length, streamPost],
  );

  /** Edit a user message and re-run from that point */
  const edit = useCallback(
    (content: string, editFromSequence: number) => {
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
          branch_id: 0,
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
      setMessages((prev) => prev.filter((m) => m.sequence_num <= userSequenceNum));
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
    streamingReasoning,
    streamPhase,
    thinkingElapsed,
    streamStatus,
    isStreaming: streamStatus === 'streaming',
    send,
    edit,
    regenerate,
    stop,
    refresh: fetchMessages,
    refreshBranch: (branchId: number) => fetchMessages(branchId),
  };
}
