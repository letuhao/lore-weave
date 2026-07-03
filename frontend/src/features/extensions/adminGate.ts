// UI show/hide gate for admin-only surfaces (registry ingest). This decodes the JWT
// `role` claim WITHOUT verifying it — it only controls what the UI renders; the API is
// the real gate (every /admin/* route returns 403 for a non-admin regardless).
import { useAuth } from '@/auth';

export function jwtRole(token: string | null): string {
  if (!token) return '';
  const parts = token.split('.');
  if (parts.length < 2) return '';
  try {
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const json = decodeURIComponent(
      atob(b64)
        .split('')
        .map((c) => '%' + c.charCodeAt(0).toString(16).padStart(2, '0'))
        .join(''),
    );
    const claims = JSON.parse(json) as { role?: string };
    return typeof claims.role === 'string' ? claims.role : '';
  } catch {
    return '';
  }
}

export function useIsAdmin(): boolean {
  const { accessToken } = useAuth();
  return jwtRole(accessToken) === 'admin';
}
