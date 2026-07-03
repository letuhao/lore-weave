// The UI show/hide admin gate reads the JWT `role` claim (the API is the real gate).
import { describe, it, expect } from 'vitest';
import { jwtRole } from '../adminGate';

// Build a JWT-shaped token with the given payload (base64url, unsigned — the gate
// never verifies; it only shows/hides).
function tok(payload: Record<string, unknown>): string {
  const b64 = (o: unknown) =>
    btoa(JSON.stringify(o)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return `${b64({ alg: 'HS256' })}.${b64(payload)}.sig`;
}

describe('jwtRole', () => {
  it('reads role=admin', () => {
    expect(jwtRole(tok({ sub: 'u1', role: 'admin' }))).toBe('admin');
  });
  it('returns "" for a non-admin / roleless token', () => {
    expect(jwtRole(tok({ sub: 'u1', role: 'user' }))).toBe('user');
    expect(jwtRole(tok({ sub: 'u1' }))).toBe('');
  });
  it('is safe on null / malformed tokens', () => {
    expect(jwtRole(null)).toBe('');
    expect(jwtRole('not-a-jwt')).toBe('');
    expect(jwtRole('a.b')).toBe(''); // b is not valid base64 JSON
  });
});
