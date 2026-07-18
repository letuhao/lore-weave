import { apiJson } from '@/api';
import { emitNotificationsMutated } from './mutationBus';

export type Notification = {
  id: string;
  category: string;
  title: string;
  body?: string;
  metadata: Record<string, unknown>;
  // D-NOTIF-I18N (NOTIF-1) — the server's first-class i18n substrate: a stable
  // `notif.<category>.<status>` key + interpolation params, alongside the
  // server-rendered English `title` fallback. Both are `null` on legacy rows or
  // when a producer supplied no key, so a locale-aware client keys off them and
  // falls back to `title` otherwise.
  message_key?: string | null;
  message_params?: Record<string, unknown> | null;
  read: boolean;
  created_at: string;
};

export type PagedNotifications = {
  items: Notification[];
  total: number;
};

export function fetchNotifications(
  token: string,
  params?: { category?: string; unread?: boolean; limit?: number; offset?: number },
) {
  const q = new URLSearchParams();
  if (params?.category) q.set('category', params.category);
  if (params?.unread) q.set('unread', 'true');
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.offset) q.set('offset', String(params.offset));
  return apiJson<PagedNotifications>(`/v1/notifications?${q}`, { token });
}

export function fetchUnreadCount(token: string) {
  return apiJson<{ count: number }>('/v1/notifications/unread-count', { token });
}

export async function markRead(id: string, token: string) {
  const r = await apiJson<void>(`/v1/notifications/${id}/read`, { method: 'PATCH', token });
  emitNotificationsMutated(); // every badge re-reads the truth (cross-surface sync)
  return r;
}

export async function markAllRead(token: string) {
  const r = await apiJson<{ marked: number }>('/v1/notifications/read-all', { method: 'POST', token });
  emitNotificationsMutated();
  return r;
}

export async function deleteNotification(id: string, token: string) {
  const r = await apiJson<void>(`/v1/notifications/${id}`, { method: 'DELETE', token });
  emitNotificationsMutated();
  return r;
}
