// S3 — never offer push where the platform can't honour it. detectPushCapability gates on SW +
// PushManager, permission ≠ denied, and (on iOS) an installed PWA.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { detectPushCapability } from '../capability';

const realNotification = globalThis.Notification;

function setup(opts: {
  sw?: boolean;
  pushManager?: boolean;
  ua?: string;
  standalone?: boolean;
  permission?: NotificationPermission;
}) {
  // serviceWorker on navigator
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    get: () => (opts.sw ? {} : undefined),
  });
  Object.defineProperty(navigator, 'userAgent', { configurable: true, get: () => opts.ua ?? 'Mozilla/5.0' });
  if (opts.pushManager) (window as unknown as { PushManager: unknown }).PushManager = function () {};
  else delete (window as unknown as { PushManager?: unknown }).PushManager;
  (window.navigator as unknown as { standalone?: boolean }).standalone = opts.standalone ?? false;
  window.matchMedia = vi.fn().mockReturnValue({ matches: opts.standalone ?? false }) as unknown as typeof window.matchMedia;
  (globalThis as unknown as { Notification: unknown }).Notification = { permission: opts.permission ?? 'default' };
}

describe('detectPushCapability (S3)', () => {
  afterEach(() => {
    (globalThis as unknown as { Notification: unknown }).Notification = realNotification;
  });

  it('supported + available when SW + PushManager present and permission not denied', () => {
    setup({ sw: true, pushManager: true, permission: 'default' });
    const c = detectPushCapability();
    expect(c.supported).toBe(true);
    expect(c.available).toBe(true);
  });

  it('not supported without PushManager', () => {
    setup({ sw: true, pushManager: false });
    const c = detectPushCapability();
    expect(c.supported).toBe(false);
    expect(c.available).toBe(false);
  });

  it('iOS Safari not installed → iosNeedsInstall, not available', () => {
    setup({ sw: true, pushManager: true, ua: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)', standalone: false, permission: 'default' });
    const c = detectPushCapability();
    expect(c.iosNeedsInstall).toBe(true);
    expect(c.available).toBe(false);
  });

  it('iOS installed as PWA → available', () => {
    setup({ sw: true, pushManager: true, ua: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)', standalone: true, permission: 'default' });
    const c = detectPushCapability();
    expect(c.iosNeedsInstall).toBe(false);
    expect(c.available).toBe(true);
  });

  it('permission denied → not available (never render a toggle it cannot honour)', () => {
    setup({ sw: true, pushManager: true, permission: 'denied' });
    const c = detectPushCapability();
    expect(c.available).toBe(false);
    expect(c.permission).toBe('denied');
  });
});
