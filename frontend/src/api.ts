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

const AUTH_KEY = 'lw_auth';

function readAuth(): { accessToken?: string | null; refreshToken?: string | null } {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

// bug #20: single-flight access-token refresh. The access token is short-lived; on expiry the
// app used to wipe auth + bounce to /login mid-work (data loss). Instead we silently exchange
// the long-lived refresh token for a new access token and retry. The refresh ROTATES the
// refresh token server-side, so concurrent 401s MUST share one in-flight refresh — otherwise
// the 2nd request reads the same (already-rotated) refresh token and gets logged out.
let refreshInFlight: Promise<string | null> | null = null;

// Exported for long-lived streams (SSE) that must proactively refresh when the token
// expires while the tab is idle — no apiJson 401 ever fires there (#11 side-finding).
export function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  const p = (async (): Promise<string | null> => {
    try {
      const { refreshToken } = readAuth();
      if (!refreshToken) return null;
      const res = await fetch(`${base()}/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return null;
      const data = (await res.json()) as { access_token?: string; refresh_token?: string };
      if (!data.access_token) return null;
      localStorage.setItem(
        AUTH_KEY,
        JSON.stringify({ accessToken: data.access_token, refreshToken: data.refresh_token ?? refreshToken }),
      );
      // Same-tab React state sync (storage events only fire cross-tab). AuthProvider re-reads.
      window.dispatchEvent(new CustomEvent('lw-auth-refreshed'));
      return data.access_token;
    } catch {
      return null;
    }
  })();
  refreshInFlight = p;
  // Clear AFTER assignment (a microtask, even for a synchronous early-return path) so a later
  // refresh isn't short-circuited by a stale resolved promise. Guard against clobbering a newer
  // in-flight refresh. NOTE: clearing inside the IIFE's `finally` would run BEFORE this
  // assignment on the sync path, leaking the resolved promise forever.
  void p.finally(() => { if (refreshInFlight === p) refreshInFlight = null; });
  return p;
}

function forceLogout(): void {
  localStorage.removeItem('lw_auth');
  localStorage.removeItem('lw_user');
  window.location.href = '/login';
}

export async function apiJson<T>(
  path: string,
  init: RequestInit & { token?: string | null } = {},
  retried = false,
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
    // 401 on an authenticated request — try a silent refresh + ONE retry before logging out.
    // Skip the auth endpoints themselves (a bad login/refresh must not loop). `retried` guards
    // against an infinite loop if even the freshly-refreshed token is rejected.
    if (res.status === 401 && init.token && !path.startsWith('/v1/auth/')) {
      if (!retried) {
        const newToken = await refreshAccessToken();
        if (newToken) {
          return apiJson<T>(path, { ...init, token: newToken }, true);
        }
        // Multi-tab rotation race: our refresh can fail because ANOTHER tab refreshed first,
        // rotating + revoking our refresh token. If localStorage now holds a different access
        // token, that other tab already recovered the session — retry with it instead of
        // logging out (otherwise one of two active tabs loses its work).
        const current = readAuth().accessToken;
        if (current && current !== init.token) {
          return apiJson<T>(path, { ...init, token: current }, true);
        }
      }
      forceLogout();
      return undefined as T;
    }
    const err = body as ApiError;
    // D-CHAT-COMPACT-ERROR-SWALLOWED (2026-07-09): Go/TS services use the
    // {code, message} envelope ApiError expects, but every Python/FastAPI
    // service (chat-service, knowledge-service, composition-service,
    // lore-enrichment-service) returns FastAPI's native {detail: string |
    // ValidationErrorItem[]} for BOTH a raised HTTPException and its own
    // global 500 handler — `err?.message` is always undefined against that
    // shape, so every FastAPI error silently fell back to `res.statusText`
    // (e.g. compact's clean 409 "nothing to compact" rendered as the
    // meaningless "Conflict"). `detail` is a plain string for a raised
    // HTTPException, or an array of {msg, loc} for a 422 pydantic
    // validation error — join the latter so nothing is dropped either way.
    const detail = (body as { detail?: unknown } | null)?.detail;
    const detailMessage = Array.isArray(detail)
      ? detail.map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d))).join('; ')
      : typeof detail === 'string'
        ? detail
        : undefined;
    // D-K8-03: attach the parsed response body to the thrown error
    // so callers handling 412 Precondition Failed can read the
    // current row out of it without a second round-trip.
    throw Object.assign(new Error(err?.message || detailMessage || res.statusText), {
      status: res.status,
      code: err?.code,
      body,
    });
  }
  return body as T;
}
