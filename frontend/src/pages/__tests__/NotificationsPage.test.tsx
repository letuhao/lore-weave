import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NotificationsPage } from '../NotificationsPage';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const navigate = vi.fn();
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));

const fetchNotifications = vi.fn();
const fetchUnreadCount = vi.fn().mockResolvedValue({ count: 5 });
const markRead = vi.fn().mockResolvedValue(undefined);
const markAllRead = vi.fn().mockResolvedValue(undefined);
vi.mock('@/features/notifications/api', () => ({
  fetchNotifications: (...a: unknown[]) => fetchNotifications(...a),
  fetchUnreadCount: (...a: unknown[]) => fetchUnreadCount(...a),
  markRead: (...a: unknown[]) => markRead(...a),
  markAllRead: (...a: unknown[]) => markAllRead(...a),
}));

const mk = (id: string, over: Record<string, unknown> = {}) => ({
  id, category: 'translation', title: `Notif ${id}`, body: '', metadata: {}, read: false,
  created_at: new Date().toISOString(), ...over,
});

beforeEach(() => {
  navigate.mockClear(); markRead.mockClear(); markAllRead.mockClear();
  fetchNotifications.mockReset();
});

describe('NotificationsPage (UI-1)', () => {
  it('loads and renders notifications on mount', async () => {
    fetchNotifications.mockResolvedValue({ items: [mk('1'), mk('2')], total: 2 });
    render(<NotificationsPage />);
    await screen.findByText('Notif 1');
    expect(screen.getByText('Notif 2')).toBeTruthy();
    // first load is category 'all' → no category param
    expect(fetchNotifications.mock.calls[0][1]).toMatchObject({ offset: 0 });
    expect(fetchNotifications.mock.calls[0][1].category).toBeUndefined();
  });

  it('filtering by a category refetches with that category', async () => {
    fetchNotifications.mockResolvedValue({ items: [mk('1')], total: 1 });
    render(<NotificationsPage />);
    await screen.findByText('Notif 1');
    fireEvent.click(screen.getByText('category.translation'));
    await waitFor(() =>
      expect(fetchNotifications.mock.calls.some((c) => c[1]?.category === 'translation')).toBe(true),
    );
  });

  it('clicking an unread item marks it read and navigates to metadata.link', async () => {
    fetchNotifications.mockResolvedValue({
      items: [mk('1', { metadata: { link: '/books/abc' } })], total: 1,
    });
    render(<NotificationsPage />);
    fireEvent.click(await screen.findByText('Notif 1'));
    expect(markRead).toHaveBeenCalledWith('1', 'tok');
    expect(navigate).toHaveBeenCalledWith('/books/abc');
  });

  it('mark-all calls markAllRead', async () => {
    fetchNotifications.mockResolvedValue({ items: [mk('1')], total: 1 });
    render(<NotificationsPage />);
    await screen.findByText('Notif 1');
    fireEvent.click(screen.getByText('markAllRead'));
    expect(markAllRead).toHaveBeenCalledWith('tok');
  });

  it('shows Load more when total exceeds loaded and appends', async () => {
    fetchNotifications
      .mockResolvedValueOnce({ items: [mk('1')], total: 2 })
      .mockResolvedValueOnce({ items: [mk('2')], total: 2 });
    render(<NotificationsPage />);
    await screen.findByText('Notif 1');
    fireEvent.click(screen.getByText('loadMore'));
    await screen.findByText('Notif 2');
    expect(fetchNotifications.mock.calls[1][1]).toMatchObject({ offset: 1 });
  });
});
