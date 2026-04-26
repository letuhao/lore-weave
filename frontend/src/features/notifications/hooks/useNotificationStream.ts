/**
 * Phase 2f (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN). Live EventSource
 * subscription to api-gateway-bff `/v1/notifications/stream`.
 *
 * Replaces the 30s poll on the unread-badge with real-time push:
 * - One EventSource per user (per browser tab).
 * - Reconnect on error with exponential backoff (1s → 2 → 4 → 8 → cap 30s).
 * - Closes on unmount or when accessToken disappears (logout).
 *
 * The hook is self-contained per CLAUDE.md FE rules: it owns its
 * EventSource lifecycle, error handling, and reconnect timer. The
 * caller supplies an `onEvent` callback that runs once per parsed
 * SSE message — typically to bump unread count, prepend to a list,
 * or toast.
 */

import { useEffect, useRef, useState } from 'react';

import { apiBase } from '@/api';

/**
 * Shape of the SSE event body. Matches the gateway's wire format
 * (provider-registry's TerminalEvent + translation-service's events).
 * Extra fields are passthrough — consumers can narrow further.
 */
export type NotificationStreamEvent = {
  // Phase 2c TerminalEvent shape:
  job_id?: string;
  owner_user_id?: string;
  operation?: string;
  status?: 'completed' | 'failed' | 'cancelled' | string;
  result?: unknown;
  error_code?: string;
  error_message?: string;
  finish_reason?: string;
  // Legacy translation-service event shape:
  user_id?: string;
  // Catch-all for forward compat.
  [k: string]: unknown;
};

export type ConnectionState = 'idle' | 'connecting' | 'open' | 'reconnecting';

const MIN_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30_000;

/**
 * Subscribe to the gateway's notification stream. The hook returns the
 * current connection state so consumers can show a "live"/"reconnecting"
 * indicator if they want.
 *
 * @param accessToken JWT to auth the EventSource (passed as `?token=`
 *   because EventSource cannot set Authorization headers).
 * @param onEvent Called for each parsed event payload. Should be stable
 *   (`useCallback`) — the hook does NOT re-subscribe when it changes.
 */
export function useNotificationStream(
  accessToken: string | null,
  onEvent: (event: NotificationStreamEvent) => void,
): ConnectionState {
  const [state, setState] = useState<ConnectionState>('idle');

  // Latest onEvent ref so reconnects pick up the freshest callback
  // without resetting the EventSource (avoids reconnect storms when
  // parent re-renders).
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
    let es: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let backoff = MIN_BACKOFF_MS;

    const connect = () => {
      if (cancelled) return;
      setState('connecting');
      const url = `${apiBase()}/v1/notifications/stream?token=${encodeURIComponent(accessToken)}`;
      es = new EventSource(url);

      es.onopen = () => {
        if (cancelled) return;
        backoff = MIN_BACKOFF_MS; // reset after successful open
        setState('open');
      };

      es.onmessage = (msg) => {
        if (cancelled) return;
        try {
          const parsed = JSON.parse(msg.data) as NotificationStreamEvent;
          onEventRef.current(parsed);
        } catch {
          // Malformed event — drop silently. The gateway is supposed
          // to JSON-encode every payload; if we ever see this, it's
          // a publisher contract bug.
        }
      };

      es.onerror = () => {
        if (cancelled) return;
        es?.close();
        es = null;
        setState('reconnecting');
        reconnectTimer = setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      es?.close();
      setState('idle');
    };
  }, [accessToken]);

  return state;
}
