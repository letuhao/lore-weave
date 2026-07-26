// N7/N8 (dogfood 2026-07-18/19) — a tiny cross-surface signal for "the unread set changed".
//
// The unread count has MULTIPLE independent badge owners that don't share state: the global
// nav `NotificationBell` (own useState, fetched once on mount), the studio status-bar item +
// panel (studio bus `notificationsUnread`), and the notification-center page. A mark-read on
// one surface therefore left a STALE badge on the others — the F1-class two-sources-of-truth
// bug ("mark read won't work" / "seems like it's not mine"). Rather than refactor all consumers
// into one store, every mutation (mark-one / mark-all / delete) fires this signal, and each
// badge re-reads the authoritative `/unread-count` — so the DB becomes the single source of
// truth immediately after any mutation, on every surface.

const target = new EventTarget();
const EVT = 'notifications:mutated';

/** Fire after a successful mark-read / mark-all / delete so every badge refetches the truth. */
export function emitNotificationsMutated(): void {
  target.dispatchEvent(new Event(EVT));
}

/** Subscribe a badge consumer; returns an unsubscribe. */
export function onNotificationsMutated(cb: () => void): () => void {
  target.addEventListener(EVT, cb);
  return () => target.removeEventListener(EVT, cb);
}
