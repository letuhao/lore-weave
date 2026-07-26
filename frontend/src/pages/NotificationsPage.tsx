import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Bell, CheckCheck, Loader2 } from 'lucide-react';
import { useNotificationList } from '@/features/notifications/hooks/useNotificationList';
import { NotificationItem } from '@/features/notifications/components/NotificationItem';
import { CATEGORIES } from '@/features/notifications/constants';
import { notificationLink } from '@/features/notifications/link';
import type { Notification } from '@/features/notifications/api';

export function NotificationsPage() {
  const { t } = useTranslation('notifications');
  const navigate = useNavigate();
  const {
    category, setCategory, items, loading, loadingMore, hasMore, hasUnread,
    loadMore, markOne, markAll,
  } = useNotificationList();

  const onItemClick = (n: Notification) => {
    if (!n.read) markOne(n.id);
    // LOW-4 safety lives in notificationLink (shared with the studio panel, #11).
    const link = notificationLink(n);
    if (!link) return;
    if (/^https?:\/\//.test(link)) window.location.href = link;
    else navigate(link);
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h1 className="font-serif text-2xl font-semibold">{t('pageTitle')}</h1>
        {hasUnread && (
          <button
            onClick={markAll}
            className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <CheckCheck className="h-3.5 w-3.5" />
            {t('markAllRead')}
          </button>
        )}
      </div>

      {/* Filter tabs */}
      <div className="mb-3 flex flex-wrap gap-1 border-b pb-3">
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setCategory(cat)}
            className={`rounded px-3 py-1.5 text-xs font-medium transition-colors ${
              category === cat
                ? 'bg-[var(--primary-muted)] text-[var(--primary)]'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {t(`category.${cat}`)}
          </button>
        ))}
      </div>

      {/* List */}
      <div className="overflow-hidden rounded-lg border bg-card">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-muted-foreground">
            <Bell className="h-7 w-7 opacity-30" />
            <p className="text-sm">{t('empty')}</p>
          </div>
        ) : (
          items.map((n) => (
            <NotificationItem
              key={n.id}
              notification={n}
              // Only clickable when there's something to do (mark-read or navigate),
              // so fully-read no-link rows aren't deceptively cursor-pointer (COSMETIC).
              onClick={!n.read || notificationLink(n) ? onItemClick : undefined}
            />
          ))
        )}
      </div>

      {/* Load more */}
      {hasMore && !loading && (
        <div className="mt-3 text-center">
          <button
            onClick={loadMore}
            disabled={loadingMore}
            className="rounded-md border px-4 py-2 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
          >
            {loadingMore ? <Loader2 className="h-4 w-4 animate-spin" /> : t('loadMore')}
          </button>
        </div>
      )}
    </div>
  );
}
