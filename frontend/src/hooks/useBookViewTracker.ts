/**
 * Book view tracker — fires once per book page visit.
 * Debounced: skips if same book viewed in last 30s (sessionStorage).
 * Works for both authenticated and anonymous users.
 */
import { useEffect, useRef } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:3000';
const DEBOUNCE_KEY = 'lw:last-view';
const DEBOUNCE_MS = 30_000;

export function useBookViewTracker(bookId: string, accessToken?: string | null) {
  const fired = useRef(false);

  useEffect(() => {
    if (!bookId || fired.current) return;

    // Debounce: skip if same book viewed recently
    const lastView = sessionStorage.getItem(DEBOUNCE_KEY);
    if (lastView) {
      try {
        const { id, ts } = JSON.parse(lastView);
        if (id === bookId && Date.now() - ts < DEBOUNCE_MS) return;
      } catch { /* ignore corrupt data */ }
    }

    fired.current = true;
    sessionStorage.setItem(DEBOUNCE_KEY, JSON.stringify({ id: bookId, ts: Date.now() }));

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;

    fetch(`${API_BASE}/v1/books/${bookId}/view`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        session_id: getSessionId(),
        referrer: document.referrer || undefined,
      }),
      keepalive: true,
    }).catch(() => {}); // best-effort
  }, [bookId, accessToken]);
}

function getSessionId(): string {
  const key = 'lw:session-id';
  let sid = sessionStorage.getItem(key);
  if (!sid) {
    sid = crypto.randomUUID();
    sessionStorage.setItem(key, sid);
  }
  return sid;
}
