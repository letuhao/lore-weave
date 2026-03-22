import { useEffect, useRef } from 'react';
import { useAuth } from '@/auth';

export type JobEvent = {
  event:    string;
  job_id:   string;
  job_type: string;
  user_id:  string;
  payload:  Record<string, unknown>;
};

type Options = {
  onEvent:       (e: JobEvent) => void;
  onReconnect?:  () => void;  // called after WS reconnects — caller should re-fetch latest state
  enabled?:      boolean;
};

/**
 * Opens a WebSocket to /ws?token=<jwt> and calls onEvent for every message.
 * Auto-reconnects on close (except auth errors 4001).
 * When the connection is re-established, calls onReconnect so the caller can
 * fetch the latest state to fill any gap that occurred while disconnected.
 */
export function useJobEvents({ onEvent, onReconnect, enabled = true }: Options): void {
  const { accessToken } = useAuth();
  const onEventRef      = useRef(onEvent);
  const onReconnectRef  = useRef(onReconnect);
  onEventRef.current     = onEvent;
  onReconnectRef.current = onReconnect;

  useEffect(() => {
    if (!enabled || !accessToken) return;

    let dead  = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let ws: WebSocket | null = null;
    let isFirstConnect = true;

    function connect() {
      if (dead) return;
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      ws = new WebSocket(`${proto}://${location.host}/ws?token=${accessToken}`);

      ws.onopen = () => {
        if (!isFirstConnect) {
          // Reconnected after a drop — caller fetches latest to fill the gap
          onReconnectRef.current?.();
        }
        isFirstConnect = false;
      };

      ws.onmessage = (e: MessageEvent) => {
        try {
          onEventRef.current(JSON.parse(e.data as string) as JobEvent);
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = (ev: CloseEvent) => {
        if (dead) return;
        if (ev.code === 4001) return; // auth error — do not reconnect
        timer = setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        ws?.close();
      };
    }

    connect();

    return () => {
      dead = true;
      if (timer) clearTimeout(timer);
      ws?.close();
    };
  }, [accessToken, enabled]);
}
