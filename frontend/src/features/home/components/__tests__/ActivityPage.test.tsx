// M2 — the activity feed renders items, an unread badge, a mark-all-read (disabled at 0 unread),
// keyset load-more, and honest empty/error states.
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';

const useActivity = vi.fn();
vi.mock('../../hooks/useActivity', () => ({ useActivity: () => useActivity() }));

import { ActivityPage } from '../ActivityPage';
import type { ActivityItem } from '../../types';

const item = (over: Partial<ActivityItem>): ActivityItem => ({
  id: 'n1',
  category: 'assistant',
  title: 'Your weekly reflection is ready',
  body: null,
  read_at: null,
  created_at: new Date().toISOString(),
  ...over,
});

const base = {
  items: [] as ActivityItem[],
  unread: 0,
  isLoading: false,
  error: null,
  hasMore: false,
  isFetchingMore: false,
  loadMore: vi.fn(),
  markAllRead: vi.fn(),
  markingAll: false,
};

function renderFeed() {
  return render(
    <MemoryRouter>
      <ActivityPage />
    </MemoryRouter>,
  );
}

describe('ActivityPage', () => {
  it('groups items into Needs-you (unread) and Earlier (read) + shows the unread badge', () => {
    useActivity.mockReturnValue({
      ...base,
      items: [item({ id: 'n1', read_at: null }), item({ id: 'n2', read_at: 'x' })],
      unread: 1,
    });
    renderFeed();
    // one unread → Needs you; one read → Earlier
    expect(screen.getByTestId('activity-needs-you').querySelectorAll('li').length).toBe(1);
    expect(screen.getByTestId('activity-earlier').querySelectorAll('li').length).toBe(1);
    expect(screen.getByText('Needs you')).toBeTruthy();
    expect(screen.getByText('Earlier')).toBeTruthy();
    expect(screen.getByTestId('activity-unread-badge').textContent).toBe('1');
  });

  it('omits an empty group (all read → no Needs-you section)', () => {
    useActivity.mockReturnValue({ ...base, items: [item({ id: 'n1', read_at: 'x' })], unread: 0 });
    renderFeed();
    expect(screen.queryByTestId('activity-needs-you')).toBeNull();
    expect(screen.getByTestId('activity-earlier')).toBeTruthy();
  });

  it('mark-all-read is disabled at 0 unread and calls the mutation when there are unread', () => {
    const markAllRead = vi.fn();
    useActivity.mockReturnValue({ ...base, items: [item({})], unread: 0, markAllRead });
    const { rerender } = renderFeed();
    expect((screen.getByTestId('activity-mark-all') as HTMLButtonElement).disabled).toBe(true);

    useActivity.mockReturnValue({ ...base, items: [item({})], unread: 3, markAllRead });
    rerender(
      <MemoryRouter>
        <ActivityPage />
      </MemoryRouter>,
    );
    const btn = screen.getByTestId('activity-mark-all') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);
    expect(markAllRead).toHaveBeenCalled();
  });

  it('shows load-more when there are more pages and calls loadMore', () => {
    const loadMore = vi.fn();
    useActivity.mockReturnValue({ ...base, items: [item({})], hasMore: true, loadMore });
    renderFeed();
    fireEvent.click(screen.getByTestId('activity-load-more'));
    expect(loadMore).toHaveBeenCalled();
  });

  it('shows an honest empty state', () => {
    useActivity.mockReturnValue({ ...base });
    renderFeed();
    expect(screen.getByText(/Nothing yet/i)).toBeTruthy();
    // no load-more when there is nothing more
    expect(screen.queryByTestId('activity-load-more')).toBeNull();
  });
});
