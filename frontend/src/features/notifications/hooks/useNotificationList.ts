import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '@/auth';
import {
  fetchNotifications,
  fetchUnreadCount,
  markRead,
  markAllRead,
  type Notification,
} from '../api';
import type { NotificationCategory } from '../constants';

const PAGE_SIZE = 20;

/**
 * Controller for the full-page notification center: category filter +
 * offset pagination (load-more) + mark-read / mark-all. Owns all state and
 * network; the page component only renders.
 */
export function useNotificationList() {
  const { accessToken } = useAuth();
  const [category, setCategoryState] = useState<NotificationCategory>('all');
  const [items, setItems] = useState<Notification[]>([]);
  const [total, setTotal] = useState(0);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  // Monotonic request id: a response is applied only if it is still the latest
  // request, so rapid category switches can't let a stale response overwrite the
  // current category's list (MED-2).
  const reqIdRef = useRef(0);

  const load = useCallback(
    async (cat: NotificationCategory, offset: number) => {
      if (!accessToken) return;
      const reqId = ++reqIdRef.current;
      const first = offset === 0;
      first ? setLoading(true) : setLoadingMore(true);
      try {
        const r = await fetchNotifications(accessToken, {
          category: cat === 'all' ? undefined : cat,
          limit: PAGE_SIZE,
          offset,
        });
        if (reqId !== reqIdRef.current) return; // superseded by a newer request
        setTotal(r.total);
        setItems((prev) => {
          if (first) return r.items;
          // Dedupe on append — offset pagination can overlap if rows shifted (LOW-2).
          const seen = new Set(prev.map((n) => n.id));
          return [...prev, ...r.items.filter((n) => !seen.has(n.id))];
        });
      } catch {
        // best-effort; leave existing items in place
      } finally {
        if (reqId === reqIdRef.current) {
          first ? setLoading(false) : setLoadingMore(false);
        }
      }
    },
    [accessToken],
  );

  // Initial + category-change load (offset reset to 0).
  useEffect(() => {
    void load(category, 0);
  }, [category, load]);

  // Authoritative unread count (so the Mark-all button reflects unread on
  // not-yet-loaded pages too, not just loaded items — LOW-3).
  useEffect(() => {
    if (!accessToken) return;
    fetchUnreadCount(accessToken)
      .then((r) => setUnreadCount(r.count))
      .catch(() => {});
  }, [accessToken]);

  const setCategory = useCallback((cat: NotificationCategory) => {
    setItems([]);
    setTotal(0);
    setCategoryState(cat);
  }, []);

  const loadMore = useCallback(() => {
    if (loadingMore) return;
    void load(category, items.length);
  }, [load, category, items.length, loadingMore]);

  const markOne = useCallback(
    (id: string) => {
      if (!accessToken) return;
      let wasUnread = false;
      setItems((prev) =>
        prev.map((n) => {
          if (n.id === id && !n.read) wasUnread = true;
          return n.id === id ? { ...n, read: true } : n;
        }),
      );
      if (wasUnread) setUnreadCount((c) => Math.max(0, c - 1));
      void markRead(id, accessToken).catch(() => {});
    },
    [accessToken],
  );

  const markAll = useCallback(() => {
    if (!accessToken) return;
    setItems((prev) => prev.map((n) => ({ ...n, read: true })));
    setUnreadCount(0);
    void markAllRead(accessToken).catch(() => {});
  }, [accessToken]);

  return {
    category,
    setCategory,
    items,
    total,
    loading,
    loadingMore,
    hasMore: items.length < total,
    hasUnread: unreadCount > 0,
    loadMore,
    markOne,
    markAll,
  };
}
