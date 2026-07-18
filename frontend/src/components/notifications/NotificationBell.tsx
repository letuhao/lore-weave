import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';
import { Bell, CheckCheck } from 'lucide-react';
import { useAuth } from '@/auth';
import {
  fetchNotifications,
  fetchUnreadCount,
  markRead,
  markAllRead,
  deleteNotification,
} from '@/features/notifications/api';
import type { Notification } from '@/features/notifications/api';
import { CATEGORIES, type NotificationCategory } from '@/features/notifications/constants';
import { NotificationItem } from '@/features/notifications/components/NotificationItem';
import { useNotificationStream } from '@/features/notifications/hooks/useNotificationStream';
import { onNotificationsMutated } from '@/features/notifications/mutationBus';

export function NotificationBell() {
  const { t } = useTranslation('notifications');
  const { accessToken } = useAuth();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);
  const [category, setCategory] = useState<NotificationCategory>('all');
  const { pathname } = useLocation();
  // Monotonic request id (GET-vs-GET) + a mask of ids just marked read locally
  // whose PATCH may still be in flight (GET-vs-PATCH) — without both, a refetch
  // triggered right after mark-read can land with the pre-write snapshot and
  // silently flip the item back to unread.
  const reqIdRef = useRef(0);
  const pendingReadIdsRef = useRef<Set<string>>(new Set());

  // Seed the badge before the first SSE event arrives, and re-sync on every
  // route change — so reading notifications on the /notifications page (which
  // owns its own state) is reflected back in this badge (MED-1: avoid the
  // bell ↔ page unread-count drift).
  useEffect(() => {
    if (!accessToken) return;
    fetchUnreadCount(accessToken)
      .then((r) => setUnread(r.count))
      .catch(() => {});
  }, [accessToken, pathname]);

  // Cross-surface sync: a mark-read/mark-all/delete on ANY surface (center page, studio
  // panel) re-reads the authoritative count here, so this badge can't be left stale on the
  // same route (the pathname refetch above only caught route changes). Single source of truth
  // = the DB, post-mutation.
  useEffect(() => {
    if (!accessToken) return;
    return onNotificationsMutated(() => {
      fetchUnreadCount(accessToken).then((r) => setUnread(r.count)).catch(() => {});
    });
  }, [accessToken]);

  // Live SSE subscription — each event bumps the unread badge.
  useNotificationStream(
    accessToken,
    useCallback(() => setUnread((c) => c + 1), []),
  );

  // Load notifications when panel opens or category changes.
  useEffect(() => {
    if (!open || !accessToken) return;
    const reqId = ++reqIdRef.current;
    setLoading(true);
    fetchNotifications(accessToken, {
      category: category === 'all' ? undefined : category,
      limit: 30,
    })
      .then((r) => {
        if (reqId !== reqIdRef.current) return; // superseded by a newer request
        const pending = pendingReadIdsRef.current;
        setItems(
          pending.size === 0
            ? r.items
            : r.items.map((n) => (pending.has(n.id) ? { ...n, read: true } : n)),
        );
        pending.clear();
      })
      .catch(() => {})
      .finally(() => {
        if (reqId === reqIdRef.current) setLoading(false);
      });
  }, [open, category, accessToken]);

  const handleMarkRead = useCallback(
    async (id: string) => {
      if (!accessToken) return;
      pendingReadIdsRef.current.add(id);
      setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
      setUnread((c) => Math.max(0, c - 1));
      await markRead(id, accessToken).catch(() => {});
    },
    [accessToken],
  );

  const handleMarkAllRead = useCallback(async () => {
    if (!accessToken) return;
    setItems((prev) => {
      prev.forEach((n) => pendingReadIdsRef.current.add(n.id));
      return prev.map((n) => ({ ...n, read: true }));
    });
    setUnread(0);
    await markAllRead(accessToken).catch(() => {});
  }, [accessToken]);

  const handleDelete = useCallback(
    async (id: string) => {
      if (!accessToken) return;
      const wasUnread = items.find((n) => n.id === id && !n.read);
      setItems((prev) => prev.filter((n) => n.id !== id));
      if (wasUnread) setUnread((c) => Math.max(0, c - 1));
      await deleteNotification(id, accessToken).catch(() => {});
    },
    [accessToken, items],
  );

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="relative flex w-full items-center gap-3 rounded-md px-2 py-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
      >
        <Bell className="h-4 w-4 flex-shrink-0" />
        <span>{t('title')}</span>
        {unread > 0 && (
          <span className="ml-auto flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-destructive px-1 text-[9px] font-bold text-white">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute bottom-full left-0 z-50 mb-2 w-[380px] rounded-lg border bg-card shadow-xl">
            {/* Header */}
            <div className="flex items-center justify-between border-b px-4 py-3">
              <span className="text-sm font-semibold">{t('title')}</span>
              {unread > 0 && (
                <button
                  onClick={() => void handleMarkAllRead()}
                  className="flex items-center gap-1 rounded px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                >
                  <CheckCheck className="h-3 w-3" />
                  {t('markAllRead')}
                </button>
              )}
            </div>

            {/* Category tabs */}
            <div className="flex gap-1 border-b px-3 py-2">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setCategory(cat)}
                  className={`rounded px-2.5 py-1 text-[11px] font-medium transition-colors ${
                    category === cat
                      ? 'bg-[var(--primary-muted)] text-[var(--primary)]'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {t(`category.${cat}`)}
                </button>
              ))}
            </div>

            {/* Notification list */}
            <div className="max-h-[400px] overflow-y-auto">
              {loading && items.length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground">{t('loading')}</div>
              ) : items.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-8 text-muted-foreground">
                  <Bell className="h-6 w-6 opacity-30" />
                  <p className="text-xs">{t('empty')}</p>
                </div>
              ) : (
                items.map((n) => (
                  <NotificationItem
                    key={n.id}
                    notification={n}
                    showActions
                    onClick={(x) => !x.read && void handleMarkRead(x.id)}
                    onMarkRead={(id) => void handleMarkRead(id)}
                    onDelete={(id) => void handleDelete(id)}
                  />
                ))
              )}
            </div>

            {/* Footer — full notification center (design §2) */}
            <div className="border-t px-4 py-2.5 text-center">
              <Link
                to="/notifications"
                onClick={() => setOpen(false)}
                className="text-xs text-[var(--primary)] hover:underline"
              >
                {t('viewAll')}
              </Link>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
