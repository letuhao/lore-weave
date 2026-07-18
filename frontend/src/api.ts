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
  // M4 (newcomer polish F1) — announce a real refresh so the shell can show "Reconnecting…" instead
  // of rendering confident authed chrome while every call transiently 401s (the first-run diary's
  // "logged in but nothing works" moment). Additive only — does NOT touch the refresh/retry logic.
  // Only when there's actually a refresh token to exchange (a logged-out miss isn't "reconnecting").
  const announce = !!readAuth().refreshToken;
  if (announce) window.dispatchEvent(new CustomEvent('lw-auth-refreshing', { detail: { active: true } }));
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
  void p.finally(() => {
    if (refreshInFlight === p) refreshInFlight = null;
    if (announce) window.dispatchEvent(new CustomEvent('lw-auth-refreshing', { detail: { active: false } }));
  });
  return p;
}

function forceLogout(): void {
  localStorage.removeItem('lw_auth');
  localStorage.removeItem('lw_user');
  window.location.href = '/login';
}

/** The longest a non-JSON body can be and still plausibly be a human sentence rather than a
 *  generated error page. Go's `http.Error` messages are a few words; nginx's 502 is ~150+ bytes
 *  of markup and a proxy's debug page can be kilobytes. */
const MAX_PLAIN_TEXT_MESSAGE = 200;

/** Is a non-JSON error body a real message we should show, or infra noise we must not?
 *  Exported for tests — this predicate is the whole difference between "database unavailable"
 *  reaching the author and an HTML document being rendered at them. */
export function isPlainTextMessage(text: string): boolean {
  const t = text.trim();
  if (!t || t.length > MAX_PLAIN_TEXT_MESSAGE) return false;
  return !t.startsWith('<');    // any markup/document, not a sentence
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
      // A non-JSON body is one of TWO things, and they must not be treated alike:
      //   1. a real plain-text message — Go's `http.Error(w, "database unavailable", 503)`
      //      (24 such sites across the Go services). Keep surfacing these.
      //   2. an INFRA error page — nginx's 502/504 HTML, a proxy timeout. These carry no
      //      user-facing message at all.
      // `message` flows to the Error below → readBackendError → the global MutationCache
      // toast, so (2) rendered a whole HTML document at the author (S2 hit this live on a
      // 502 through the FE nginx). Suppress markup and anything far too long to be a
      // sentence; keep the raw text under `rawBody` either way for debugging.
      body = isPlainTextMessage(text)
        ? { code: 'PARSE_ERROR', message: text.trim(), rawBody: text }
        : { code: 'PARSE_ERROR', rawBody: text };
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
    // lore-enrichment-service) returns FastAPI's native {detail: ...} for
    // BOTH a raised HTTPException and its own global 500 handler —
    // `err?.message` is always undefined against that shape, so every
    // FastAPI error silently fell back to `res.statusText` (e.g. compact's
    // clean 409 "nothing to compact" rendered as the meaningless "Conflict").
    // `detail` takes three shapes across services: a plain string (most
    // chat-service errors), an array of {msg, loc} for a 422 pydantic
    // validation error (join it), or a plain object (composition-service's
    // `{code: "action_error"}`, campaign-service's `{code, message}`) — read
    // `.message` then `.code` off it so a bare `{code}` with no `.message`
    // still surfaces SOMETHING over the generic statusText. /review-impl
    // (2026-07-09): the first cut of this fix only handled string + array,
    // missing the object shape those other two services actually raise.
    const detail = (body as { detail?: unknown } | null)?.detail;
    const detailMessage = Array.isArray(detail)
      ? detail.map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d))).join('; ')
      : typeof detail === 'string'
        ? detail
        : detail && typeof detail === 'object'
          ? (() => {
              const o = detail as { message?: unknown; code?: unknown };
              const picked = o.message ?? o.code;
              return picked != null ? String(picked) : undefined;
            })()
          : undefined;
    // D-K8-03: attach the parsed response body to the thrown error
    // so callers handling 412 Precondition Failed can read the
    // current row out of it without a second round-trip.
    // `res.statusText` is EMPTY over HTTP/2 (the protocol dropped the reason phrase), so it
    // cannot be the last resort: behind an HTTP/2 load balancer this would throw Error('') and
    // the toast would render blank — a silent failure. Fall back to the status code itself.
    const statusLine = res.statusText || `HTTP ${res.status}`;
    throw Object.assign(new Error(err?.message || detailMessage || statusLine), {
      status: res.status,
      code: err?.code,
      body,
    });
  }
  return body as T;
}
