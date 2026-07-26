// MB4 — the post-login redirect must preserve the FULL deep-link (search + hash), not just the
// pathname, so a cold `/entry/123?sheet=today#note` survives the login round-trip.
import { describe, it, expect } from 'vitest';
import { resolveLoginRedirect } from '../LoginPage';

describe('resolveLoginRedirect (MB4)', () => {
  it('preserves pathname + search + hash from a location object', () => {
    const to = resolveLoginRedirect({ pathname: '/entry/123', search: '?sheet=today', hash: '#note' });
    expect(to).toEqual({ pathname: '/entry/123', search: '?sheet=today', hash: '#note' });
  });

  it('fills missing search/hash with empty strings', () => {
    expect(resolveLoginRedirect({ pathname: '/books' })).toEqual({ pathname: '/books', search: '', hash: '' });
  });

  it('accepts a legacy pathname string', () => {
    expect(resolveLoginRedirect('/worlds')).toBe('/worlds');
  });

  it('defaults to /books when there is no saved location', () => {
    expect(resolveLoginRedirect(undefined)).toBe('/books');
    expect(resolveLoginRedirect(null)).toBe('/books');
    expect(resolveLoginRedirect('')).toBe('/books');
    expect(resolveLoginRedirect({})).toBe('/books'); // object without pathname
  });

  it('rejects an off-origin / protocol-relative target (open-redirect defense-in-depth)', () => {
    expect(resolveLoginRedirect('//evil.com')).toBe('/books');
    expect(resolveLoginRedirect('https://evil.com')).toBe('/books');
    expect(resolveLoginRedirect({ pathname: '//evil.com' })).toBe('/books');
    expect(resolveLoginRedirect({ pathname: 'https://evil.com/x' })).toBe('/books');
  });
});
