// Safe link extraction from notification metadata (LOW-4): metadata is server-authored
// (createNotification is internal-token-gated), but still — only http(s) externally and
// '/'-prefixed in-app paths are ever followable. Shared by the notifications page (navigate)
// and the studio panel (studio link resolver, #11 F3).
import type { Notification } from './api';

export function notificationLink(n: Notification): string | null {
  const meta = n.metadata as Record<string, unknown> | undefined;
  const l = typeof meta?.link === 'string' ? meta.link : typeof meta?.url === 'string' ? meta.url : null;
  // '//' is protocol-relative (resolves to an EXTERNAL origin in window.open) — an "app path"
  // must be exactly one leading slash.
  return l && (/^https?:\/\//.test(l) || (l.startsWith('/') && !l.startsWith('//'))) ? l : null;
}
