// SINGLE source of truth for the FE→BE base URL. Default '' = relative/same-origin,
// which rides the proxy→gateway path in BOTH environments:
//   dev:  Vite proxy  /v1 → localhost:3123  (host port of api-gateway-bff)
//   prod: nginx proxy /v1 → api-gateway-bff:3000 (container port)
// Set VITE_API_BASE only for non-proxied custom setups.
// NOTE: every FE caller (incl. SSE/WebSocket/upload) MUST use `apiBase` — do NOT
// re-declare a local base with a hardcoded host:port (that was the LW-PLAN F-3 rot:
// 8 call-sites defaulting to http://localhost:3000, the gateway's *container* port,
// which the browser cannot reach → silently broke chat/stats/media/import when
// VITE_API_BASE was unset).
const base = () => import.meta.env.VITE_API_BASE || '';

/** Same base URL `apiJson` uses — exported for callers that bypass
 *  fetch (EventSource, WebSocket, direct multipart upload, etc.).
 *  WebSocket callers need an absolute URL: use `apiBase() || window.location.origin`. */
export const apiBase = base;

export type ApiError = { code: string; message: string };

export async function apiJson<T>(
  path: string,
  init: RequestInit & { token?: string | null } = {},
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string>),
  };
  if (init.token) {
    headers.Authorization = `Bearer ${init.token}`;
  }
  const res = await fetch(`${base()}${path}`, { ...init, headers });
  if (res.status === 204) {
    return undefined as T;
  }
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { code: 'PARSE_ERROR', message: text };
    }
  }
  if (!res.ok) {
    // Auto-clear auth on 401 — token expired or invalid
    if (res.status === 401 && init.token) {
      localStorage.removeItem('lw_auth');
      window.location.href = '/login';
      return undefined as T;
    }
    const err = body as ApiError;
    // D-K8-03: attach the parsed response body to the thrown error
    // so callers handling 412 Precondition Failed can read the
    // current row out of it without a second round-trip.
    throw Object.assign(new Error(err?.message || res.statusText), {
      status: res.status,
      code: err?.code,
      body,
    });
  }
  return body as T;
}
