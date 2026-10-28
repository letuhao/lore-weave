/**
 * Book view tracker — fires once per book page visit.
 * Debounced: skips if same book viewed in last 30s (sessionStorage).
 * Works for both authenticated and anonymous users.
 */
import { useEffect, useRef } from 'react';
import { apiBase } from '@/api';

const API_BASE = apiBase();
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
    sid = createSessionId();
    sessionStorage.setItem(key, sid);
  }
  return sid;
}

/**
 * `crypto.randomUUID()` is exposed only in secure contexts in some browsers.
 * LoreWeave is also used over plain HTTP on a LAN address, so keep analytics
 * best-effort instead of allowing the page tree to crash during mount.
 */
function createSessionId(): string {
  const webCrypto = globalThis.crypto;
  if (typeof webCrypto?.randomUUID === 'function') return webCrypto.randomUUID();

  if (typeof webCrypto?.getRandomValues === 'function') {
    const bytes = new Uint8Array(16);
    webCrypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  // Last-resort non-secret identifier: analytics only, never an auth token.
  return `lw-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
