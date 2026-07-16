// DF1 — the platform home renders the draft layout: greeting top bar, the always-present assistant
// hero (Start-talking + mic), a jump-back-in rail of real cards, the launcher, and an inline feed.
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';

const useHome = vi.fn();
const useActivity = vi.fn();
vi.mock('../../hooks/useHome', () => ({ useHome: () => useHome() }));
vi.mock('../../hooks/useActivity', () => ({ useActivity: () => useActivity() }));
vi.mock('@/auth', () => ({ useAuth: () => ({ user: { display_name: 'Hao', email: 'hao@x.dev' } }) }));

import { PlatformHomePage } from '../PlatformHomePage';
import type { HomeResponse } from '../../types';

const okData: HomeResponse = {
  tiles: {
    activity: { status: 'ok', data: { unread: 4 } },
    books: { status: 'ok', data: [{ id: 'b1', title: 'The Empty Throne', updated_at: new Date().toISOString() }] },
    jobs: { status: 'ok', data: [{ id: 'j1', kind: 'translation', status: 'running' }] },
  },
  generated_at: 'x',
};
const feed = {
  items: [{ id: 'n1', category: 'assistant', title: 'Weekly reflection ready', body: null, read_at: null, created_at: new Date().toISOString() }],
  unread: 4,
  isLoading: false,
  error: null,
  hasMore: false,
  isFetchingMore: false,
  loadMore: vi.fn(),
  refetch: vi.fn(),
  markAllRead: vi.fn(),
  markingAll: false,
};

function renderHome() {
  return render(<MemoryRouter><PlatformHomePage /></MemoryRouter>);
}

describe('PlatformHomePage (DF1 draft layout)', () => {
  it('renders the greeting top bar with the user name + a notifications bell', () => {
    useHome.mockReturnValue({ data: okData, isLoading: false, refetch: vi.fn() });
    useActivity.mockReturnValue(feed);
    renderHome();
    expect(screen.getByText(/, Hao/)).toBeTruthy(); // "Good <time>, Hao"
    expect(screen.getByLabelText(/Notifications, 4 unread/)).toBeTruthy();
  });

  it('always renders the assistant hero with Start-talking (front door never blanks)', () => {
    useHome.mockReturnValue({ data: undefined, isLoading: true, refetch: vi.fn() });
    useActivity.mockReturnValue({ ...feed, isLoading: true, items: [] });
    renderHome();
    const hero = screen.getByTestId('home-assistant-hero');
    expect(hero).toBeTruthy();
    expect(screen.getByTestId('home-start-talking').getAttribute('href')).toBe('/assistant');
  });

  it('renders jump-back-in cards from real books + jobs', () => {
    useHome.mockReturnValue({ data: okData, isLoading: false, refetch: vi.fn() });
    useActivity.mockReturnValue(feed);
    renderHome();
    expect(screen.getByText('The Empty Throne')).toBeTruthy();
    expect(screen.getByTestId('home-jump-back-in')).toBeTruthy();
  });

  it('renders an inline recent-activity feed and the all-apps launcher', () => {
    useHome.mockReturnValue({ data: okData, isLoading: false, refetch: vi.fn() });
    useActivity.mockReturnValue(feed);
    renderHome();
    expect(screen.getByTestId('home-recent-feed').textContent).toContain('Weekly reflection ready');
    expect(screen.getByTestId('home-all-apps')).toBeTruthy();
  });
});
