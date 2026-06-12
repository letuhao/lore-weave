import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NotificationBell } from '../NotificationBell';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('@/features/notifications/hooks/useNotificationStream', () => ({
  useNotificationStream: () => {},
}));

const fetchNotifications = vi.fn().mockResolvedValue({
  items: [
    { id: '1', category: 'translation', title: 'Hello', body: '', metadata: {}, read: false, created_at: new Date().toISOString() },
  ],
  total: 1,
});
const fetchUnreadCount = vi.fn().mockResolvedValue({ count: 3 });
const markRead = vi.fn().mockResolvedValue(undefined);
const markAllRead = vi.fn().mockResolvedValue(undefined);
const deleteNotification = vi.fn().mockResolvedValue(undefined);
vi.mock('@/features/notifications/api', () => ({
  fetchNotifications: (...a: unknown[]) => fetchNotifications(...a),
  fetchUnreadCount: (...a: unknown[]) => fetchUnreadCount(...a),
  markRead: (...a: unknown[]) => markRead(...a),
  markAllRead: (...a: unknown[]) => markAllRead(...a),
  deleteNotification: (...a: unknown[]) => deleteNotification(...a),
}));

const renderBell = () => render(<MemoryRouter><NotificationBell /></MemoryRouter>);

beforeEach(() => { markAllRead.mockClear(); fetchNotifications.mockClear(); });

describe('NotificationBell (post-F-3-refactor)', () => {
  it('seeds the unread badge from fetchUnreadCount', async () => {
    renderBell();
    await screen.findByText('3'); // badge
  });

  it('opens the dropdown, lists notifications, and shows the View-all link', async () => {
    renderBell();
    fireEvent.click(screen.getByText('title')); // bell button label (i18n mocked → key)
    await screen.findByText('Hello');
    const viewAll = screen.getByText('viewAll');
    expect(viewAll.closest('a')?.getAttribute('href')).toBe('/notifications');
  });

  it('mark-all calls markAllRead', async () => {
    renderBell();
    fireEvent.click(screen.getByText('title'));
    await screen.findByText('Hello');
    fireEvent.click(screen.getByText('markAllRead'));
    await waitFor(() => expect(markAllRead).toHaveBeenCalledWith('tok'));
  });
});
