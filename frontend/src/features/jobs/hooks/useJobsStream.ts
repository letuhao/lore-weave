// P4 — live job stream (controller). Consumes GET /v1/jobs/stream as a
// fetch-stream (NOT EventSource): jobs-service requires the JWT in the
// Authorization header and rejects token-in-URL (it would leak into logs),
// so the browser EventSource API — which can't set headers — is unusable here.
// Mirrors composition's fetch-stream + notifications' reconnect backoff.
//
// Self-contained per CLAUDE.md FE rules: owns the fetch lifecycle, line
// buffering, reconnect timer, and abort-on-unmount. The caller supplies a
// stable `onEvent` (the hook does NOT re-subscribe when it changes).
import { useEffect, useRef, useState } from 'react';

import { jobsApi } from '../api';
import type { JobSseEvent } from '../types';

export type ConnectionState = 'idle' | 'connecting' | 'open' | 'reconnecting';

const MIN_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30_000;

export function useJobsStream(
  accessToken: string | null,
  onEvent: (event: JobSseEvent) => void,
): ConnectionState {
  const [state, setState] = useState<ConnectionState>('idle');

  // Freshest callback without resubscribing (avoids reconnect storms on re-render).
  const onEventRef = useRef(onEvent);
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!accessToken) {
      setState('idle');
      return;
    }

    let cancelled = false;
    let controller: AbortController | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let backoff = MIN_BACKOFF_MS;

    const scheduleReconnect = () => {
      if (cancelled) return;
      setState('reconnecting');
      reconnectTimer = setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
    };

    const connect = async () => {
      if (cancelled) return;
      setState('connecting');
      controller = new AbortController();
      try {
        const res = await fetch(jobsApi.streamUrl(), {
          headers: { Authorization: `Bearer ${accessToken}` },
          signal: controller.signal,
        });
        if (cancelled) return;
        if (res.status === 401) {
          // Token expired/invalid — terminal, NOT a transient blip. The read
          // queries (apiJson) will clear auth + redirect to /login on their own
          // 401; reconnecting here would just hammer the endpoint while logged out.
          setState('idle');
          return;
        }
        if (!res.ok || !res.body) {
          scheduleReconnect();
          return;
        }
        backoff = MIN_BACKOFF_MS; // reset after a successful open
        setState('open');

        const reader = res.body.getReader();
        // Ensure a pending read() resolves when this connection is aborted
        // (unmount / token change) even if the runtime doesn't propagate the
        // abort into the stream — otherwise the read hangs forever.
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
          buffer = lines.pop() ?? ''; // keep a partial line across chunks
          for (const line of lines) {
            // SSE comments (": connected", ": heartbeat") and blank separators.
            if (!line.startsWith('data:')) continue;
            const payload = line.slice(5).trimStart();
            if (!payload) continue;
            try {
              onEventRef.current(JSON.parse(payload) as JobSseEvent);
            } catch {
              // Malformed frame — drop. The stream is JSON-per-frame by contract.
            }
          }
        }
        // Stream ended cleanly (server closed) — reconnect unless we're tearing down.
        if (!cancelled) scheduleReconnect();
      } catch {
        if (!cancelled) scheduleReconnect();
      }
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      controller?.abort();
      setState('idle');
    };
  }, [accessToken]);

  return state;
}
