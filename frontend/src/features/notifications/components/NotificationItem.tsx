import { useTranslation } from 'react-i18next';
import { Check, Trash2 } from 'lucide-react';
import type { Notification } from '../api';
import { CATEGORY_COLORS, categoryIcon } from '../constants';

type Props = {
  notification: Notification;
  /** Row click — bell uses it to mark-read; page uses it to mark-read + navigate. */
  onClick?: (n: Notification) => void;
  onMarkRead?: (id: string) => void;
  onDelete?: (id: string) => void;
  /** Show hover mark-read / delete buttons (bell dropdown). The page omits them. */
  showActions?: boolean;
};

/** Shared notification row used by both the bell dropdown and the full page,
 *  so the icon/color/time/unread treatment stays in one place. */
const humanize = (s: string) => {
  const x = s.replace(/_/g, ' ').trim();
  return x.charAt(0).toUpperCase() + x.slice(1);
};

export function NotificationItem({ notification: n, onClick, onMarkRead, onDelete, showActions = false }: Props) {
  const { t } = useTranslation('notifications');
  const Icon = categoryIcon(n.category);

  // i18n the title client-side from machine-readable metadata (the stored `title`
  // is server-rendered English). Phase 1: LLM-job events carry operation + status.
  // Phase 2 (emitters with interpolated titles) sets metadata.i18n_key + params.
  const meta = (n.metadata ?? {}) as Record<string, unknown>;
  const key = typeof meta.i18n_key === 'string' ? meta.i18n_key : null;
  const op = typeof meta.operation === 'string' ? meta.operation : null;
  const status = typeof meta.status === 'string' ? meta.status : null;
  let title = n.title; // fallback: stored English
  if (key) {
    const params = (meta.i18n_params as Record<string, unknown>) ?? {};
    title = t(key, { defaultValue: n.title, ...params });
  } else if (op) {
    title = t('event.title', {
      op: t(`event.operation.${op}`, { defaultValue: humanize(op) }),
      status: t(`event.status.${status}`, { defaultValue: status ?? '' }),
    }).trim();
  }

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
    <div
      className={`group flex gap-3 border-b px-4 py-3 transition-colors last:border-b-0 hover:bg-[var(--card-hover)] ${
        onClick ? 'cursor-pointer' : ''
      } ${!n.read ? 'border-l-2 border-l-[var(--primary)] bg-[rgba(232,168,50,0.03)]' : ''}`}
      onClick={onClick ? () => onClick(n) : undefined}
    >
      <div
        className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg"
        style={{ background: CATEGORY_COLORS[n.category] || CATEGORY_COLORS.system }}
      >
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>

      <div className="min-w-0 flex-1">
        <p className="text-[13px] leading-snug">{title}</p>
        {n.body && <p className="mt-0.5 text-[11px] text-muted-foreground line-clamp-2">{n.body}</p>}
      </div>

      <div className="flex flex-col items-end gap-1">
        <span className={`text-[11px] ${!n.read ? 'text-[var(--primary)]' : 'text-muted-foreground'}`}>
          {timeAgo(n.created_at)}
        </span>
        {showActions && (
          <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 max-md:opacity-100">
            {!n.read && onMarkRead && (
              <button
                onClick={(e) => { e.stopPropagation(); onMarkRead(n.id); }}
                className="rounded p-0.5 text-muted-foreground hover:text-foreground"
                title={t('markRead')}
              >
                <Check className="h-3 w-3" />
              </button>
            )}
            {onDelete && (
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(n.id); }}
                className="rounded p-0.5 text-muted-foreground hover:text-destructive"
                title={t('delete')}
              >
                <Trash2 className="h-3 w-3" />
              </button>
            )}
          </div>
        )}
        {!n.read && <span className="h-[7px] w-[7px] rounded-full bg-[var(--primary)]" />}
      </div>
    </div>
  );
}
