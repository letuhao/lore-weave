// 14_utility_panels.md D2/D5 — the "translators" leaderboard capability panel: registers,
// self-titles, and renders ONLY the translators list from useLeaderboardList('translators') —
// no books/authors fetch, confirming DOCK-8's one-capability-per-panel split.
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

import { LeaderboardTranslatorsPanel } from '../LeaderboardTranslatorsPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(ui: ReactNode) {
  return render(<StudioHostProvider bookId="irrelevant"><HostProbe />{ui}</StudioHostProvider>);
}

function translatorRow(overrides: Record<string, unknown> = {}) {
  return {
    rank: 1,
    user_id: 't1',
    display_name: 'Jian Translator',
    total_chapters_done: 42,
    languages: ['en', 'vi'],
    ...overrides,
  };
}

beforeEach(() => {
  hostRef = null;
  apiMocks.listBooks.mockReset();
  apiMocks.listAuthors.mockReset();
  apiMocks.listTranslators.mockReset().mockResolvedValue({ items: [translatorRow()], total: 1, period: '30d' });
});

describe('LeaderboardTranslatorsPanel', () => {
  it('registers with the host as an openable studio tool and self-titles', () => {
    const props = dockProps();
    withHost(<LeaderboardTranslatorsPanel {...props} />);
    expect(hostRef!.getRegisteredTool('leaderboard-translators')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('leaderboard-translators')!.commandId).toBe('studio.openPanel.leaderboard-translators');
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('renders translators sourced from useLeaderboardList("translators") — no books/authors calls', async () => {
    withHost(<LeaderboardTranslatorsPanel {...dockProps()} />);
    expect(await screen.findByText('Jian Translator')).toBeInTheDocument();
    expect(apiMocks.listTranslators).toHaveBeenCalledWith({ period: '30d', limit: 20, offset: 0 });
    expect(apiMocks.listBooks).not.toHaveBeenCalled();
    expect(apiMocks.listAuthors).not.toHaveBeenCalled();
  });
});
