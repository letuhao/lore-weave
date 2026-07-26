// T4d — the admin chat controller (React-MVC: owns logic + state, no JSX).
// Streams a turn from chat-service over SSE (AG-UI), accumulates text + tool
// chips, suspends on the glossary_confirm_action frontend tool, and resumes
// after the admin Confirms/Cancels. Mirrors the main-FE useChatMessages flow,
// scoped to the System-tier admin surface.
import { useCallback, useRef, useState } from 'react';
import { adminChatApi } from '../api';
import {
  AgUiEventType,
  type AgUiCustomEvent,
  type RunErrorEvent,
  type RunFinishedEvent,
  type TextMessageContentEvent,
  type ToolCallResultEvent,
  type ToolCallStartEvent,
} from '../agUiEvents';
import type { AdminToolOutcome, ChatMessage, ToolCallRecord } from '../types';

interface StreamOverride {
  url: string;
  body: Record<string, unknown>;
}

interface UseAdminChat {
  messages: ChatMessage[];
  streamingText: string;
  isStreaming: boolean;
  error: string | null;
  send: (content: string) => Promise<void>;
  submitToolResult: (runId: string, toolCallId: string, outcome: AdminToolOutcome) => Promise<void>;
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  reset: () => void;
}

export function useAdminChat(
  sessionId: string | null,
  userToken: string | null,
  adminToken: string | null,
): UseAdminChat {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    setMessages([]);
    setStreamingText('');
    setError(null);
  }, []);

  // The shared SSE consumer — used by both a fresh send and a resume (override).
  const streamPost = useCallback(
    async (content: string, override?: StreamOverride) => {
      if (!sessionId || !userToken) return;
      setError(null);
      setIsStreaming(true);
      setStreamingText('');

      const controller = new AbortController();
      abortRef.current = controller;

      let accumulatedText = '';
      const toolCalls: ToolCallRecord[] = [];
      const openToolCalls = new Map<string, string>();
      const openToolArgs = new Map<string, string>();
      let assistantId = `a-${Date.now()}`;

      const body: Record<string, unknown> =
        override?.body ?? { content, admin_context: { label: 'System admin' } };

      try {
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${userToken}`,
          'x-loreweave-stream-format': 'agui',
        };
        // The RS256 admin token rides X-Admin-Token (admin-surface routing). It
        // is a bearer credential — set on the request only, never logged.
        if (adminToken) headers['X-Admin-Token'] = adminToken;

        const res = await fetch(override?.url ?? adminChatApi.messagesUrl(sessionId), {
          method: 'POST',
          headers,
          body: JSON.stringify(body),
          signal: controller.signal,
        });
        if (!res.ok) {
          const detail = await res.text().catch(() => res.statusText);
          throw new Error(`${res.status}: ${detail}`);
        }
        const reader = res.body?.getReader();
        if (!reader) throw new Error('No response body');
        const cancelReader = () => void reader.cancel().catch(() => {});
        if (controller.signal.aborted) cancelReader();
        else controller.signal.addEventListener('abort', cancelReader, { once: true });

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
            if (payload === '[DONE]' || !payload) continue;
            let event: { type?: string };
            try {
              event = JSON.parse(payload) as { type?: string };
            } catch {
              continue;
            }
            switch (event.type) {
              case AgUiEventType.TEXT_MESSAGE_CONTENT: {
                const delta = (event as TextMessageContentEvent).delta;
                if (!delta) break;
                accumulatedText += delta;
                setStreamingText(accumulatedText);
                break;
              }
              case AgUiEventType.TOOL_CALL_START: {
                const e = event as ToolCallStartEvent;
                if (e.toolCallId) openToolCalls.set(e.toolCallId, e.toolCallName);
                break;
              }
              case AgUiEventType.TOOL_CALL_ARGS: {
                const e = event as { toolCallId?: string; delta?: string };
                if (e.toolCallId) {
                  openToolArgs.set(e.toolCallId, (openToolArgs.get(e.toolCallId) ?? '') + (e.delta ?? ''));
                }
                break;
              }
              case AgUiEventType.TOOL_CALL_RESULT: {
                const e = event as ToolCallResultEvent;
                const tool = openToolCalls.get(e.toolCallId);
                if (tool === undefined) break;
                openToolCalls.delete(e.toolCallId);
                let ok = true;
                try {
                  const parsed = JSON.parse(e.content);
                  if (parsed && typeof parsed === 'object' && parsed.ok === false) ok = false;
                } catch {
                  /* opaque non-JSON result → success */
                }
                toolCalls.push({ tool, ok });
                break;
              }
              case AgUiEventType.CUSTOM: {
                const e = event as AgUiCustomEvent;
                if (e.name === 'persisted' && e.value?.messageId) {
                  assistantId = e.value.messageId as string;
                }
                break;
              }
              case AgUiEventType.RUN_FINISHED: {
                const result = (event as RunFinishedEvent).result;
                if (result?.status === 'suspended' && result.pendingToolCall) {
                  const p = result.pendingToolCall;
                  let args: Record<string, unknown> = {};
                  try {
                    args = JSON.parse(openToolArgs.get(p.toolCallId) ?? '{}');
                  } catch {
                    args = {};
                  }
                  toolCalls.push({
                    tool: p.toolName,
                    ok: true,
                    pending: true,
                    runId: p.runId,
                    toolCallId: p.toolCallId,
                    args,
                  });
                }
                break;
              }
              case AgUiEventType.RUN_ERROR: {
                setError((event as RunErrorEvent).message || 'Stream error');
                break;
              }
            }
          }
        }

        // Commit the assistant turn (text + any tool chips / pending confirm).
        if (accumulatedText || toolCalls.length > 0) {
          setMessages((prev) => [
            ...prev,
            {
              message_id: assistantId,
              session_id: sessionId,
              role: 'assistant',
              content: accumulatedText,
              created_at: new Date().toISOString(),
              tool_calls: toolCalls.length > 0 ? toolCalls : undefined,
            },
          ]);
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setError((err as Error).message || 'Failed to stream');
        }
      } finally {
        setIsStreaming(false);
        setStreamingText('');
        abortRef.current = null;
      }
    },
    [sessionId, userToken, adminToken],
  );

  const send = useCallback(
    async (content: string) => {
      if (!content.trim()) return;
      setMessages((prev) => [
        ...prev,
        {
          message_id: `u-${Date.now()}`,
          session_id: sessionId ?? '',
          role: 'user',
          content,
          created_at: new Date().toISOString(),
        },
      ]);
      await streamPost(content);
    },
    [sessionId, streamPost],
  );

  // Resume a suspended run after the admin confirmed/cancelled the System action.
  const submitToolResult = useCallback(
    async (runId: string, toolCallId: string, outcome: AdminToolOutcome) => {
      if (!sessionId) return;
      // Clear the pending flag on the rendered card so it can't be re-clicked.
      setMessages((prev) =>
        prev.map((m) =>
          m.tool_calls?.some((tc) => tc.toolCallId === toolCallId)
            ? {
                ...m,
                tool_calls: m.tool_calls.map((tc) =>
                  tc.toolCallId === toolCallId ? { ...tc, pending: false } : tc,
                ),
              }
            : m,
        ),
      );
      await streamPost('', {
        url: adminChatApi.toolResultsUrl(sessionId),
        body: { run_id: runId, tool_call_id: toolCallId, outcome },
      });
    },
    [sessionId, streamPost],
  );

  return { messages, streamingText, isStreaming, error, send, submitToolResult, setMessages, reset };
}
