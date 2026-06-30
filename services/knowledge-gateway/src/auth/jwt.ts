import { createHmac, timingSafeEqual } from 'node:crypto';

/**
 * Minimal HS256 JWT verification using Node's built-in crypto — no external dependency.
 * The KAL only needs to (a) verify the platform HS256 signature and (b) read `sub` (user id)
 * + `exp`. It is NOT an authorization server; it trusts the same JWT_SECRET glossary/knowledge
 * verify against. Returns the user id (`sub`) on a valid, unexpired token, else null.
 *
 * Deliberately strict: alg must be exactly HS256 (no `none`, no alg confusion), signature is
 * constant-time compared, and `exp` (if present) must be in the future.
 */
export function verifyHs256(token: string | undefined, secret: string): string | null {
  if (!token || !secret) return null;
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  const [headerB64, payloadB64, sigB64] = parts;

  let header: { alg?: string; typ?: string };
  let payload: { sub?: string; exp?: number };
  try {
    header = JSON.parse(b64urlDecode(headerB64));
    payload = JSON.parse(b64urlDecode(payloadB64));
  } catch {
    return null;
  }
  if (header.alg !== 'HS256') return null; // reject `none` / alg confusion

  const expected = createHmac('sha256', secret).update(`${headerB64}.${payloadB64}`).digest();
  let actual: Buffer;
  try {
    actual = Buffer.from(sigB64.replace(/-/g, '+').replace(/_/g, '/'), 'base64');
  } catch {
    return null;
  }
  if (expected.length !== actual.length || !timingSafeEqual(expected, actual)) return null;

  if (typeof payload.exp === 'number' && payload.exp * 1000 <= nowMs()) return null; // expired
  return typeof payload.sub === 'string' && payload.sub ? payload.sub : null;
}

function b64urlDecode(s: string): string {
  return Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8');
}

// Wall-clock for exp checks. Isolated so it is the only Date use (auditable).
function nowMs(): number {
  return Date.now();
}
