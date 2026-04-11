import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Bell, Check, CheckCheck, Trash2 } from 'lucide-react';
import { useAuth } from '@/auth';
import {
  fetchNotifications,
  fetchUnreadCount,
  markRead,
  markAllRead,
  deleteNotification,
} from '@/features/notifications/api';
import type { Notification } from '@/features/notifications/api';

const CATEGORIES = ['all', 'translation', 'social', 'wiki', 'system'] as const;
type Category = (typeof CATEGORIES)[number];

const CATEGORY_COLORS: Record<string, string> = {
  translation: 'rgba(61,186,106,0.1)',
  social: 'rgba(232,93,117,0.1)',
  wiki: 'rgba(61,166,146,0.1)',
  system: 'rgba(232,168,50,0.1)',
};

const POLL_INTERVAL = 30_000;

export function NotificationBell() {
  const { t } = useTranslation('notifications');
  const { accessToken } = useAuth();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);
  const [category, setCategory] = useState<Category>('all');
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  // Poll unread count
  useEffect(() => {
    if (!accessToken) return;
    const poll = () => {
      fetchUnreadCount(accessToken)
        .then((r) => setUnread(r.count))
        .catch(() => {});
    };
    poll();
    timerRef.current = setInterval(poll, POLL_INTERVAL);
    return () => clearInterval(timerRef.current);
  }, [accessToken]);

  // Load notifications when panel opens or category changes
  useEffect(() => {
    if (!open || !accessToken) return;
    setLoading(true);
    fetchNotifications(accessToken, {
      category: category === 'all' ? undefined : category,
      limit: 30,
    })
      .then((r) => setItems(r.items))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [open, category, accessToken]);

  const handleMarkRead = useCallback(
    async (id: string) => {
      if (!accessToken) return;
      setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
      setUnread((c) => Math.max(0, c - 1));
      await markRead(id, accessToken).catch(() => {});
    },
    [accessToken],
  );

  const handleMarkAllRead = useCallback(async () => {
    if (!accessToken) return;
    setItems((prev) => prev.map((n) => ({ ...n, read: true })));
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

  const timeAgo = (iso: string) => {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return t('justNow');
    if (mins < 60) return t('minsAgo', { count: mins });
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return t('hrsAgo', { count: hrs });
    const days = Math.floor(hrs / 24);
    return t('daysAgo', { count: days });
  };

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
                  <div
                    key={n.id}
                    className={`group flex cursor-pointer gap-3 border-b px-4 py-3 transition-colors last:border-b-0 hover:bg-[var(--card-hover)] ${
                      !n.read ? 'border-l-2 border-l-[var(--primary)] bg-[rgba(232,168,50,0.03)]' : ''
                    }`}
                    onClick={() => !n.read && void handleMarkRead(n.id)}
                  >
                    {/* Icon */}
                    <div
                      className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg"
                      style={{ background: CATEGORY_COLORS[n.category] || CATEGORY_COLORS.system }}
                    >
                      <Bell className="h-4 w-4 text-muted-foreground" />
                    </div>

                    {/* Content */}
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] leading-snug">{n.title}</p>
                      {n.body && (
                        <p className="mt-0.5 text-[11px] text-muted-foreground line-clamp-1">
                          {n.body}
                        </p>
                      )}
                    </div>

                    {/* Time + actions */}
                    <div className="flex flex-col items-end gap-1">
                      <span
                        className={`text-[11px] ${!n.read ? 'text-[var(--primary)]' : 'text-muted-foreground'}`}
                      >
                        {timeAgo(n.created_at)}
                      </span>
                      <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 max-md:opacity-100">
                        {!n.read && (
                          <button
                            onClick={(e) => { e.stopPropagation(); void handleMarkRead(n.id); }}
                            className="rounded p-0.5 text-muted-foreground hover:text-foreground"
                            title={t('markRead')}
                          >
                            <Check className="h-3 w-3" />
                          </button>
                        )}
                        <button
                          onClick={(e) => { e.stopPropagation(); void handleDelete(n.id); }}
                          className="rounded p-0.5 text-muted-foreground hover:text-destructive"
                          title={t('delete')}
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                      {!n.read && <span className="h-[7px] w-[7px] rounded-full bg-[var(--primary)]" />}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
