// FE→BE base URL. Default '' = relative/same-origin, which rides the
// proxy→gateway path in both environments:
//   dev:  Vite proxy  /v1 → localhost:3123 (host port of api-gateway-bff)
//   prod: nginx proxy /v1 → api-gateway-bff:3000 (container port)
const base = () => import.meta.env.VITE_API_BASE || '';

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
    // Auto-clear auth on 401 — token expired or invalid. Uses the CMS-specific
    // localStorage key so it never collides with the main app's `lw_auth`.
    if (res.status === 401 && init.token) {
      localStorage.removeItem('cms_auth');
      window.location.href = '/login';
      return undefined as T;
    }
    const err = body as ApiError;
    throw Object.assign(new Error(err?.message || res.statusText), {
      status: res.status,
      code: err?.code,
      body,
    });
  }
  return body as T;
}
