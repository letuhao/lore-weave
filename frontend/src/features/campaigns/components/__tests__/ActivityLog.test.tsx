import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ActivityLog, relTime } from '../ActivityLog';
import { useCampaignActivity } from '../../hooks/useCampaignQueries';
import type { ActivityEntry } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../hooks/useCampaignQueries', () => ({ useCampaignActivity: vi.fn() }));

const mockUse = vi.mocked(useCampaignActivity);

function entry(id: number, over: Partial<ActivityEntry>): ActivityEntry {
  return {
    id, chapter_id: `c${id}`, chapter_sort: id, stage: 'translation',
    status: 'done', detail: null, created_at: '2026-06-11T00:00:00Z', ...over,
  };
}

function setItems(items: ActivityEntry[]) {
  mockUse.mockReturnValue({ data: { items, next_before: null } } as ReturnType<typeof useCampaignActivity>);
}

function renderLog() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ActivityLog campaignId="cmp1" active />
    </QueryClientProvider>,
  );
}

describe('relTime (pure)', () => {
  const base = new Date('2026-06-11T12:00:00Z').getTime();
  it('buckets the elapsed time', () => {
    expect(relTime('2026-06-11T12:00:00Z', base)).toBe('just now');
    expect(relTime('2026-06-11T11:59:30Z', base)).toBe('30s');
    expect(relTime('2026-06-11T11:57:00Z', base)).toBe('3m');
    expect(relTime('2026-06-11T10:00:00Z', base)).toBe('2h');
    expect(relTime('2026-06-09T12:00:00Z', base)).toBe('2d');
  });
  it('clamps a future timestamp to just now (no negative)', () => {
    expect(relTime('2026-06-11T12:01:00Z', base)).toBe('just now');
  });
});

describe('ActivityLog (view)', () => {
  beforeEach(() => mockUse.mockReset());

  it('lists the rows newest-first with a failure detail', () => {
    setItems([
      entry(9, { chapter_sort: 5, stage: 'translation', status: 'done' }),
      entry(8, { chapter_sort: 7, stage: 'knowledge', status: 'failed', detail: 'HTTP 429' }),
    ]);
    renderLog();
    expect(screen.getByText('monitor.activity')).toBeInTheDocument();
    expect(screen.getAllByText('monitor.chapterShort')).toHaveLength(2);
    expect(screen.getByText('done')).toBeInTheDocument();
    expect(screen.getByText('failed')).toBeInTheDocument();
    expect(screen.getByText('— HTTP 429')).toBeInTheDocument();
  });

  it('renders nothing when there is no activity', () => {
    setItems([]);
    const { container } = renderLog();
    expect(container).toBeEmptyDOMElement();
  });
});
