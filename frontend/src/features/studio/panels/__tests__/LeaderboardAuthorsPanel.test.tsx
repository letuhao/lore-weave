// 14_utility_panels.md D2/D5 — the "authors" leaderboard capability panel: registers,
// self-titles, and renders ONLY the authors list from useLeaderboardList('authors') — no
// books/translators fetch, confirming DOCK-8's one-capability-per-panel split.
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

import { LeaderboardAuthorsPanel } from '../LeaderboardAuthorsPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(ui: ReactNode) {
  return render(<StudioHostProvider bookId="irrelevant"><HostProbe />{ui}</StudioHostProvider>);
}

function authorRow(overrides: Record<string, unknown> = {}) {
  return {
    rank: 1,
    user_id: 'a1',
    display_name: 'Jane Author',
    total_books: 3,
    readers: 100,
    avg_rating: 4.2,
    total_chapters: 20,
    ...overrides,
  };
}

beforeEach(() => {
  hostRef = null;
  apiMocks.listBooks.mockReset();
  apiMocks.listAuthors.mockReset().mockResolvedValue({ items: [authorRow()], total: 1, period: '30d' });
  apiMocks.listTranslators.mockReset();
});

describe('LeaderboardAuthorsPanel', () => {
  it('registers with the host as an openable studio tool and self-titles', () => {
    const props = dockProps();
    withHost(<LeaderboardAuthorsPanel {...props} />);
    expect(hostRef!.getRegisteredTool('leaderboard-authors')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('leaderboard-authors')!.commandId).toBe('studio.openPanel.leaderboard-authors');
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('renders authors sourced from useLeaderboardList("authors") — no books/translators calls', async () => {
    withHost(<LeaderboardAuthorsPanel {...dockProps()} />);
    expect(await screen.findByText('Jane Author')).toBeInTheDocument();
    expect(apiMocks.listAuthors).toHaveBeenCalledWith({ period: '30d', limit: 20, offset: 0 });
    expect(apiMocks.listBooks).not.toHaveBeenCalled();
    expect(apiMocks.listTranslators).not.toHaveBeenCalled();
  });
});
