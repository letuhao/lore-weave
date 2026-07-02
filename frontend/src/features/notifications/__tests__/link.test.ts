import { describe, expect, it } from 'vitest';
import { notificationLink } from '../link';
import type { Notification } from '../api';

const notif = (metadata: Record<string, unknown>) => ({ metadata } as unknown as Notification);

describe('notificationLink (LOW-4 safe extraction)', () => {
  it('accepts http(s) and single-slash app paths; prefers link over url', () => {
    expect(notificationLink(notif({ link: 'https://x.y/z' }))).toBe('https://x.y/z');
    expect(notificationLink(notif({ url: '/books/b1' }))).toBe('/books/b1');
    expect(notificationLink(notif({ link: '/a', url: '/b' }))).toBe('/a');
  });

  it('rejects protocol-relative "//" (external-origin escape), unsafe schemes, and non-strings', () => {
    expect(notificationLink(notif({ link: '//evil.example/x' }))).toBeNull();
    // eslint-disable-next-line no-script-url
    expect(notificationLink(notif({ link: 'javascript:alert(1)' }))).toBeNull();
    expect(notificationLink(notif({ link: 42 }))).toBeNull();
    expect(notificationLink(notif({}))).toBeNull();
  });
});
