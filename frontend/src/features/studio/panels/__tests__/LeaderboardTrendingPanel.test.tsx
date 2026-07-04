// 14_utility_panels.md D2/D5 — the "trending" leaderboard capability panel: registers,
// self-titles, renders books ranking WITHOUT QuickStatsCards (matching LeaderboardPage's
// original trending tab), and forces the sort param to 'trending' regardless of the local
// sort filter (useLeaderboardList('trending')'s byte-preserving override).
import { render, screen } from '@testing-library/react';
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

import { LeaderboardTrendingPanel } from '../LeaderboardTrendingPanel';

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
    title: 'Trending Book',
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
  apiMocks.listAuthors.mockReset();
  apiMocks.listTranslators.mockReset();
});

describe('LeaderboardTrendingPanel', () => {
  it('registers with the host as an openable studio tool and self-titles', () => {
    const props = dockProps();
    withHost(<LeaderboardTrendingPanel {...props} />);
    expect(hostRef!.getRegisteredTool('leaderboard-trending')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('leaderboard-trending')!.commandId).toBe('studio.openPanel.leaderboard-trending');
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('renders the trending books ranking with sort forced to "trending", no author/translator calls', async () => {
    withHost(<LeaderboardTrendingPanel {...dockProps()} />);
    expect(await screen.findByText('Trending Book')).toBeInTheDocument();
    expect(apiMocks.listBooks).toHaveBeenCalledWith(expect.objectContaining({ sort: 'trending' }));
    expect(apiMocks.listAuthors).not.toHaveBeenCalled();
    expect(apiMocks.listTranslators).not.toHaveBeenCalled();
  });

  it('does not render QuickStatsCards (trending tab never showed it)', async () => {
    withHost(<LeaderboardTrendingPanel {...dockProps()} />);
    await screen.findByText('Trending Book');
    expect(screen.queryByText(/quickStats\./)).toBeNull();
  });
});
