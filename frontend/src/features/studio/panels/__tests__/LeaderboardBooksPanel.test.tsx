// 14_utility_panels.md D2/D5 — the "books" leaderboard capability panel: registers, self-titles,
// renders the books ranking (Podium/RankingList/QuickStatsCards) sourced from
// useLeaderboardList('books'), and opens sibling leaderboard panels via host.openPanel (never a
// route hop — DOCK-7).
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { IDockviewPanelProps } from 'dockview-react';
import type { ReactNode } from 'react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

const apiMocks = vi.hoisted(() => ({
  listBooks: vi.fn(),
  listAuthors: vi.fn(),
  listTranslators: vi.fn(),
}));
vi.mock('@/features/leaderboard/api', () => ({ leaderboardApi: apiMocks }));

import { LeaderboardBooksPanel } from '../LeaderboardBooksPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(ui: ReactNode) {
  return render(<StudioHostProvider bookId="irrelevant"><HostProbe />{ui}</StudioHostProvider>);
}

function book(overrides: Record<string, unknown> = {}) {
  return {
    rank: 1,
    book_id: 'b1',
    owner_user_id: 'u1',
    owner_display_name: 'Author',
    title: 'The First Book',
    genre_tags: [],
    original_language: null,
    views: 0,
    unique_readers: 10,
    chapter_count: 5,
    translation_count: 0,
    avg_rating: 4.5,
    rating_count: 3,
    favorites_count: 2,
    rank_change: 0,
    has_cover: false,
    ...overrides,
  };
}

beforeEach(() => {
  hostRef = null;
  apiMocks.listBooks.mockReset().mockResolvedValue({ items: [book()], total: 1, period: '30d' });
  apiMocks.listAuthors.mockReset().mockResolvedValue({ items: [], total: 0, period: '30d' });
  apiMocks.listTranslators.mockReset().mockResolvedValue({ items: [], total: 0, period: '30d' });
});

describe('LeaderboardBooksPanel', () => {
  it('registers with the host as an openable studio tool and self-titles', () => {
    const props = dockProps();
    withHost(<LeaderboardBooksPanel {...props} />);
    expect(hostRef!.getRegisteredTool('leaderboard-books')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('leaderboard-books')!.commandId).toBe('studio.openPanel.leaderboard-books');
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('renders the books ranking sourced from useLeaderboardList("books")', async () => {
    withHost(<LeaderboardBooksPanel {...dockProps()} />);
    expect(await screen.findByText('The First Book')).toBeInTheDocument();
    expect(apiMocks.listBooks).toHaveBeenCalledWith(expect.objectContaining({ period: '30d', limit: 20, offset: 0 }));
  });

  it('QuickStatsCards "view all authors" opens the leaderboard-authors dock panel via host.openPanel', async () => {
    withHost(<LeaderboardBooksPanel {...dockProps()} />);
    await screen.findByText('The First Book');
    const openPanelSpy = vi.spyOn(hostRef!, 'openPanel');
    const viewAllButtons = screen.getAllByRole('button').filter((b) => b.textContent?.includes('quickStats.viewAll'));
    expect(viewAllButtons.length).toBe(2); // authors card + translators card
    fireEvent.click(viewAllButtons[0]);
    expect(openPanelSpy).toHaveBeenCalledWith('leaderboard-authors');
    fireEvent.click(viewAllButtons[1]);
    expect(openPanelSpy).toHaveBeenCalledWith('leaderboard-translators');
  });
});
