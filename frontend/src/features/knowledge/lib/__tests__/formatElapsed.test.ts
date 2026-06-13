import { describe, it, expect } from 'vitest';
import { formatElapsed } from '../formatElapsed';

const NOW = Date.parse('2026-06-13T12:00:00Z');

describe('formatElapsed', () => {
  it('returns null for missing/blank input', () => {
    expect(formatElapsed(null, NOW)).toBeNull();
    expect(formatElapsed(undefined, NOW)).toBeNull();
    expect(formatElapsed('', NOW)).toBeNull();
  });

  it('returns null for an unparseable timestamp', () => {
    expect(formatElapsed('not-a-date', NOW)).toBeNull();
  });

  it('returns null for a future timestamp (clock skew guard)', () => {
    expect(formatElapsed('2026-06-13T12:05:00Z', NOW)).toBeNull();
  });

  it('formats seconds under a minute', () => {
    expect(formatElapsed('2026-06-13T11:59:30Z', NOW)).toBe('30s');
  });

  it('formats minutes and seconds', () => {
    expect(formatElapsed('2026-06-13T11:57:25Z', NOW)).toBe('2m 35s');
  });

  it('formats hours and minutes past an hour', () => {
    expect(formatElapsed('2026-06-13T10:23:00Z', NOW)).toBe('1h 37m');
  });
});
