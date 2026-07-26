// M5 (D-MOB-4) — push capability detection (§8-S3). Never offer a toggle the platform can't honour:
// require serviceWorker + PushManager, permission ≠ denied, and on iOS an INSTALLED PWA (iOS 16.4+
// only delivers push to a Home-Screen PWA). Pure function of the environment so it's unit-testable.
export interface PushCapability {
  /** SW + PushManager exist in this browser. */
  supported: boolean;
  /** iOS Safari that is NOT installed to the Home Screen — push won't work until it is. */
  iosNeedsInstall: boolean;
  /** The OS Notification permission. */
  permission: NotificationPermission;
  /** Whether we may OFFER push here (supported, not iOS-needs-install, not hard-denied). */
  available: boolean;
}

export function detectPushCapability(): PushCapability {
  const nav = typeof navigator !== 'undefined' ? navigator : undefined;
  const hasSW = !!nav && 'serviceWorker' in nav;
  const hasPush = typeof window !== 'undefined' && 'PushManager' in window;
  const supported = hasSW && hasPush;

  const ua = nav?.userAgent ?? '';
  const isIOS = /iP(hone|ad|od)/.test(ua);
  const standalone =
    (typeof window !== 'undefined' &&
      ((window.navigator as unknown as { standalone?: boolean }).standalone === true ||
        window.matchMedia?.('(display-mode: standalone)').matches)) ||
    false;
  const iosNeedsInstall = isIOS && !standalone;

  const permission: NotificationPermission =
    supported && typeof Notification !== 'undefined' ? Notification.permission : 'denied';

  const available = supported && !iosNeedsInstall && permission !== 'denied';
  return { supported, iosNeedsInstall, permission, available };
}
