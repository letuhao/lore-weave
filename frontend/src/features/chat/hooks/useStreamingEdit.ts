import { useCallback, useRef, useState } from 'react';
import { useAuth } from '@/auth';

const apiBase = () => import.meta.env.VITE_API_BASE || 'http://localhost:3000';

type Status = 'idle' | 'streaming' | 'error';

interface StreamingEditResult {
  /** Accumulated text from the streaming response */
  streamingText: string;
  /** Current status of the streaming edit */
  status: Status;
  /** Send an edited message (re-run from a given sequence) */
  sendEdit: (sessionId: string, content: string, editFromSequence: number) => Promise<string>;
  /** Regenerate the last assistant response */
  regenerate: (sessionId: string, lastUserContent: string, lastUserSequence: number) => Promise<string>;
  /** Cancel an in-progress stream */
  cancel: () => void;
}

/**
 * Hook for message editing and regeneration.
 * Makes a manual POST with `edit_from_sequence` and parses the SSE stream.
 */
export function useStreamingEdit(): StreamingEditResult {
  const { accessToken } = useAuth();
  const [streamingText, setStreamingText] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const abortRef = useRef<AbortController | null>(null);

  const streamPost = useCallback(
    async (sessionId: string, content: string, editFromSequence: number): Promise<string> => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setStreamingText('');
      setStatus('streaming');

      let accumulated = '';

      try {
        const res = await fetch(
          `${apiBase()}/v1/chat/sessions/${sessionId}/messages`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
            },
            body: JSON.stringify({ content, edit_from_sequence: editFromSequence }),
            signal: controller.signal,
          },
        );

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

        setStatus('idle');
        return accumulated;
      } catch (err) {
        if ((err as Error).name === 'AbortError') {
          setStatus('idle');
          return accumulated;
        }
        setStatus('error');
        throw err;
      } finally {
        abortRef.current = null;
      }
    },
    [accessToken],
  );

  const sendEdit = useCallback(
    (sessionId: string, content: string, editFromSequence: number) =>
      streamPost(sessionId, content, editFromSequence),
    [streamPost],
  );

  const regenerate = useCallback(
    (sessionId: string, lastUserContent: string, lastUserSequence: number) =>
      streamPost(sessionId, lastUserContent, lastUserSequence - 1),
    [streamPost],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { streamingText, status, sendEdit, regenerate, cancel };
}
