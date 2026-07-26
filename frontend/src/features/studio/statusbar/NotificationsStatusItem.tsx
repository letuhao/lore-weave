// #11 F2 — unread-notifications badge on the studio status bar. Lives at frame level (NOT in the
// notifications panel) so the count stays live while the panel is closed. Count is bus-owned
// (`notificationsUnread`): this item seeds it (fetch) + bumps it (SSE); the notifications panel
// publishes corrections after mark-read — one number, no badge↔panel drift.
import { useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Bell } from 'lucide-react';
import { useAuth } from '@/auth';
import { fetchUnreadCount } from '@/features/notifications/api';
import { useNotificationStream } from '@/features/notifications/hooks/useNotificationStream';
import { onNotificationsMutated } from '@/features/notifications/mutationBus';
import { useStudioBusSelector, useStudioHost } from '../host/StudioHostProvider';
import { getStudioPanelDef } from '../panels/catalog';

export function NotificationsStatusItem() {
  const { t } = useTranslation('studio');
  const { accessToken } = useAuth();
  const host = useStudioHost();
  const unread = useStudioBusSelector((s) => s.notificationsUnread ?? 0);

  useEffect(() => {
    if (!accessToken) return;
    let mounted = true;
    fetchUnreadCount(accessToken)
      .then((r) => { if (mounted) host.publish({ type: 'notificationsUnread', count: r.count }); })
      .catch(() => { /* badge is cosmetic; panel shows the truth */ });
    return () => { mounted = false; };
  }, [accessToken, host]);

  useNotificationStream(accessToken, useCallback(() => {
    host.publish({ type: 'notificationsUnread', count: (host.getSnapshot().notificationsUnread ?? 0) + 1 });
  }, [host]));

  // Cross-surface sync: a mark-read/mark-all/delete anywhere (this panel, the center page, the
  // nav bell) RE-SEEDS the authoritative count onto the bus. Without this, the badge only
  // corrected when the panel happened to be open (which re-publishes its list count) — so a
  // mark-all could leave a stale studio badge, and the SSE-only +1 bumps had no counter-reset.
  useEffect(() => {
    if (!accessToken) return;
    return onNotificationsMutated(() => {
      fetchUnreadCount(accessToken)
        .then((r) => host.publish({ type: 'notificationsUnread', count: r.count }))
        .catch(() => {});
    });
  }, [accessToken, host]);

  const openPanel = () => {
    const def = getStudioPanelDef('notifications');
    host.openPanel('notifications', {
      title: def ? t(def.titleKey, { defaultValue: 'Notifications' }) : undefined,
    });
  };

  return (
    <button
      type="button"
      data-testid="studio-status-notifications"
      onClick={openPanel}
      title={t('status.notifications', { defaultValue: 'Notifications' })}
      className="inline-flex items-center gap-1 rounded px-1 py-0.5 hover:bg-secondary hover:text-foreground"
    >
      <Bell className="h-3 w-3" />
      {unread > 0 && (
        <span
          data-testid="studio-status-unread"
          className="flex h-[14px] min-w-[14px] items-center justify-center rounded-full bg-destructive px-0.5 text-[9px] font-bold text-white"
        >
          {unread > 99 ? '99+' : unread}
        </span>
      )}
    </button>
  );
}
