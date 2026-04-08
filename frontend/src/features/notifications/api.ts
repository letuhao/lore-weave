import { apiJson } from '@/api';

export type Notification = {
  id: string;
  category: string;
  title: string;
  body?: string;
  metadata: Record<string, unknown>;
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

export function markRead(id: string, token: string) {
  return apiJson<void>(`/v1/notifications/${id}/read`, { method: 'PATCH', token });
}

export function markAllRead(token: string) {
  return apiJson<{ marked: number }>('/v1/notifications/read-all', { method: 'POST', token });
}

export function deleteNotification(id: string, token: string) {
  return apiJson<void>(`/v1/notifications/${id}`, { method: 'DELETE', token });
}
