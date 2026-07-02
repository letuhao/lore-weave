// #11 W2 · Notifications dock panel. Reuses the feature layer AS-IS (useNotificationList +
// NotificationItem + CATEGORIES); what differs from NotificationsPage is ONLY navigation:
// item clicks go through the studio link resolver (F3) — same-book chapters focus the editor,
// panel paths open panels, everything else opens a NEW TAB. navigate() is forbidden here.
// Publishes its authoritative unread count to the bus so the F2 badge never drifts.
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Bell, CheckCheck, Loader2 } from 'lucide-react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useNotificationList } from '@/features/notifications/hooks/useNotificationList';
import { NotificationItem } from '@/features/notifications/components/NotificationItem';
import { CATEGORIES } from '@/features/notifications/constants';
import { notificationLink } from '@/features/notifications/link';
import type { Notification } from '@/features/notifications/api';
import { useStudioHost } from '../host/StudioHostProvider';
import { followStudioLink } from '../host/studioLinks';
import { getStudioPanelDef } from './catalog';
import { useStudioPanel } from './useStudioPanel';

export function NotificationsPanel(props: IDockviewPanelProps) {
  useStudioPanel('notifications', props.api);
  const { t } = useTranslation('notifications');
  const { t: tStudio } = useTranslation('studio');
  const host = useStudioHost();
  const {
    category, setCategory, items, loading, loadingMore, hasMore, hasUnread, unreadCount,
    loadMore, markOne, markAll,
  } = useNotificationList();

  // Sync the authoritative count onto the bus (F2 badge reads it) — mark-read here corrects
  // the badge immediately, no route-change resync exists in the studio.
  useEffect(() => {
    host.publish({ type: 'notificationsUnread', count: unreadCount });
  }, [host, unreadCount]);

  const onItemClick = (n: Notification) => {
    if (!n.read) markOne(n.id);
    const link = notificationLink(n);
    if (!link) return;
    followStudioLink(link, host, {
      bookId: host.bookId,
      titleFor: (panelId) => {
        const def = getStudioPanelDef(panelId);
        return def ? tStudio(def.titleKey, { defaultValue: panelId }) : undefined;
      },
    });
  };

  return (
    <div data-testid="studio-notifications-panel" className="flex h-full min-h-0 flex-col">
      <div className="flex flex-shrink-0 items-center gap-1 border-b px-3 py-2">
        <div className="flex flex-1 flex-wrap gap-1">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setCategory(cat)}
              className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                category === cat
                  ? 'bg-[var(--primary-muted)] text-[var(--primary)]'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {t(`category.${cat}`)}
            </button>
          ))}
        </div>
        {hasUnread && (
          <button
            type="button"
            data-testid="studio-notifications-mark-all"
            onClick={markAll}
            className="flex items-center gap-1 rounded px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <CheckCheck className="h-3 w-3" />
            {t('markAllRead')}
          </button>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {loading && items.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 text-muted-foreground">
            <Bell className="h-6 w-6 opacity-30" />
            <p className="text-xs">{t('empty')}</p>
          </div>
        ) : (
          items.map((n) => (
            <NotificationItem key={n.id} notification={n} onClick={onItemClick} />
          ))
        )}
        {hasMore && !loading && (
          <div className="p-3 text-center">
            <button
              type="button"
              onClick={loadMore}
              disabled={loadingMore}
              className="rounded border px-3 py-1.5 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground disabled:opacity-40"
            >
              {loadingMore ? t('loading') : t('loadMore')}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
