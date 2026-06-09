import { useEffect, useRef, useCallback } from 'react';
import { apiBase, fetchStreamTicket } from '@/api';

export type ImportStatusEvent = {
  type: 'import.status';
  job_id: string;
  status: 'processing' | 'completed' | 'failed';
  chapters_created: number;
  error?: string;
};

/**
 * useImportEvents connects to the gateway WebSocket and listens for import.status events.
 * Falls back gracefully if WS is unavailable — caller should still poll as backup.
 */
export function useImportEvents(
  token: string | null,
  onEvent: (event: ImportStatusEvent) => void,
) {
  const wsRef = useRef<WebSocket | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const connect = useCallback(() => {
    if (!token) return;

    void (async () => {
      let streamToken: string;
      try {
        streamToken = await fetchStreamTicket(token);
      } catch (err) {
        if (import.meta.env.PROD) {
          console.error('stream-ticket failed in prod', err);
          return;
        }
        streamToken = token;
      }
      const base = apiBase() || window.location.origin;
      const wsUrl = base.replace(/^http/, 'ws') + '/ws?token=' + encodeURIComponent(streamToken);

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data as string);
          if (data.type === 'import.status') {
            onEventRef.current(data as ImportStatusEvent);
          }
        } catch {
          // ignore non-JSON messages
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      // WS not available — silent fallback to polling
    }
    })();
  }, [token]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);
}
