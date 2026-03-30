// In dev: Vite proxy handles /v1 → localhost:3001 (gateway)
// In Docker: nginx proxy handles /v1 → api-gateway-bff:3000
// VITE_API_BASE override for custom setups
const base = () => import.meta.env.VITE_API_BASE || '';

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
    const err = body as ApiError;
    throw Object.assign(new Error(err.message || res.statusText), {
      status: res.status,
      code: err.code,
    });
  }
  return body as T;
}
