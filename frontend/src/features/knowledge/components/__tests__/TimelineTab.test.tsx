import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({
    accessToken: 'tok-test',
    user: {
      user_id: 'u1',
      email: 'a@b',
      display_name: null,
      avatar_url: null,
    },
  }),
}));

const listTimelineMock = vi.fn();
const listProjectsMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      listTimeline: (...args: unknown[]) => listTimelineMock(...args),
      listProjects: (...args: unknown[]) => listProjectsMock(...args),
    },
  };
});

import { TimelineTab } from '../TimelineTab';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const EVENT_DUEL = {
  id: 'ev-duel',
  user_id: 'u1',
  project_id: 'p-1',
  title: 'Kai duels Zhao',
  canonical_title: 'kai duels zhao',
  summary: 'A clash at the bridge.',
  chapter_id: 'ch-aaaa-bbbb-cccc-dddd',
  // C6: TimelineEvent now carries the BE-resolved title. Default
  // fixtures leave it null so existing tests exercise the UUID-
  // short fallback path; a dedicated test below opts in.
  chapter_title: null,
  event_order: 10,
  chronological_order: null,
  participants: ['Kai', 'Zhao', 'Phoenix', 'Master'],
  confidence: 0.9,
  source_types: ['book_content'],
  evidence_count: 3,
  mention_count: 5,
  archived_at: null,
  created_at: null,
  updated_at: null,
};

const EVENT_REVEAL = {
  ...EVENT_DUEL,
  id: 'ev-reveal',
  title: 'The hidden name revealed',
  summary: null,
  participants: ['Kai'],
  event_order: 20,
};

describe('TimelineTab', () => {
  beforeEach(() => {
    listTimelineMock.mockReset();
    listProjectsMock.mockReset();
    listProjectsMock.mockResolvedValue({ items: [], next_cursor: null });
    listTimelineMock.mockResolvedValue({
      events: [EVENT_DUEL, EVENT_REVEAL],
      total: 2,
    });
  });

  it('renders loading state then the list with events + forwards defaults', async () => {
    render(<TimelineTab />, { wrapper: Wrapper });
    // Loading surface appears synchronously before the query resolves.
    expect(screen.getByTestId('timeline-loading')).toBeTruthy();
    await screen.findByTestId('timeline-list');
    expect(await screen.findAllByTestId('timeline-event-row')).toHaveLength(2);
    expect(listTimelineMock).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 50, offset: 0 }),
      'tok-test',
    );
  });

  it('surfaces API errors via the error banner', async () => {
    listTimelineMock.mockRejectedValueOnce(new Error('network is down'));
    render(<TimelineTab />, { wrapper: Wrapper });
    await screen.findByTestId('timeline-error');
  });

  it('renders empty-state when total=0 (no events yet variant)', async () => {
    listTimelineMock.mockResolvedValueOnce({ events: [], total: 0 });
    render(<TimelineTab />, { wrapper: Wrapper });
    const empty = await screen.findByTestId('timeline-empty');
    // "no events yet" wording vs "no events match filters"
    expect(empty.textContent?.length ?? 0).toBeGreaterThan(0);
  });

  it('toggles a row expansion on click and collapses on second click', async () => {
    render(<TimelineTab />, { wrapper: Wrapper });
    const rows = await screen.findAllByTestId('timeline-event-row');
    expect(screen.queryByTestId('timeline-event-detail')).toBeNull();
    fireEvent.click(rows[0]);
    await screen.findByTestId('timeline-event-detail');
    fireEvent.click(rows[0]);
    await waitFor(() => {
      expect(screen.queryByTestId('timeline-event-detail')).toBeNull();
    });
  });

  it('changes project filter and refetches with project_id + offset=0', async () => {
    listProjectsMock.mockResolvedValueOnce({
      items: [
        { project_id: 'p-1', name: 'Crimson Echoes' },
        { project_id: 'p-2', name: 'Second Book' },
      ],
      next_cursor: null,
    });
    render(<TimelineTab />, { wrapper: Wrapper });
    await screen.findByTestId('timeline-list');
    listTimelineMock.mockClear();
    const select = screen.getByTestId(
      'timeline-filter-project',
    ) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'p-2' } });
    await waitFor(() => {
      expect(listTimelineMock).toHaveBeenCalled();
    });
    const call = listTimelineMock.mock.calls.at(-1)!;
    expect(call[0]).toEqual(
      expect.objectContaining({ project_id: 'p-2', offset: 0 }),
    );
  });

  it('clicking Next advances offset by PAGE_SIZE and refetches', async () => {
    // Seed 200 events so canNext is true at offset=0.
    listTimelineMock.mockResolvedValue({
      events: [EVENT_DUEL, EVENT_REVEAL],
      total: 200,
    });
    render(<TimelineTab />, { wrapper: Wrapper });
    await screen.findByTestId('timeline-list');
    fireEvent.click(screen.getByTestId('timeline-pagination-next'));
    // Wait until the BE was called with offset=50 — don't mockClear()
    // because that races with react-query's in-flight resolution.
    await waitFor(() => {
      const calls = listTimelineMock.mock.calls;
      expect(calls.some((c) => c[0].offset === 50)).toBe(true);
    });
  });

  it('clicking Previous from offset>0 returns to the previous page (Prev re-disables)', async () => {
    // Tests Prev via observable UI state rather than mock-call count —
    // react-query will hit the cached offset=0 query on the way back
    // (no new BE call), so the contract we actually care about is that
    // the state flipped (Prev button toggles from enabled → disabled).
    listTimelineMock.mockResolvedValue({
      events: [EVENT_DUEL, EVENT_REVEAL],
      total: 200,
    });
    render(<TimelineTab />, { wrapper: Wrapper });
    await screen.findByTestId('timeline-list');
    const prev = () =>
      screen.getByTestId('timeline-pagination-prev') as HTMLButtonElement;
    // At offset=0, Prev is disabled.
    expect(prev().disabled).toBe(true);
    fireEvent.click(screen.getByTestId('timeline-pagination-next'));
    await waitFor(() => {
      expect(prev().disabled).toBe(false);
    });
    fireEvent.click(prev());
    await waitFor(() => {
      expect(prev().disabled).toBe(true);
    });
  });

  it('Prev is disabled at offset=0 and Next is disabled at the last page', async () => {
    // Tiny dataset so we are simultaneously at the first AND last page.
    listTimelineMock.mockResolvedValue({
      events: [EVENT_DUEL],
      total: 1,
    });
    render(<TimelineTab />, { wrapper: Wrapper });
    await screen.findByTestId('timeline-list');
    const prev = screen.getByTestId(
      'timeline-pagination-prev',
    ) as HTMLButtonElement;
    const next = screen.getByTestId(
      'timeline-pagination-next',
    ) as HTMLButtonElement;
    expect(prev.disabled).toBe(true);
    expect(next.disabled).toBe(true);
  });

  it('L6 escape-hatch: past-end offset with total>0 shows "back to first" reset', async () => {
    // Simulate the stale-offset race: user was on an advanced page, a
    // delete cascade shrank total below their offset. We reproduce by
    // first advancing the offset (via Next), then switching the mock
    // to return empty+total>0 for subsequent queries. The mismatch
    // mirrors what would happen on the next 30s-staleTime refetch.
    listTimelineMock.mockResolvedValue({
      events: [EVENT_DUEL, EVENT_REVEAL],
      total: 200,
    });
    render(<TimelineTab />, { wrapper: Wrapper });
    await screen.findByTestId('timeline-list');
    fireEvent.click(screen.getByTestId('timeline-pagination-next'));
    // Prev becomes enabled means offset advanced successfully.
    await waitFor(() => {
      expect(
        (screen.getByTestId('timeline-pagination-prev') as HTMLButtonElement)
          .disabled,
      ).toBe(false);
    });
    // Switch the mock for the NEXT page-change fetch. When the user
    // clicks Next again (offset 50 → 100), the new query returns the
    // shrunk-total state.
    listTimelineMock.mockResolvedValue({ events: [], total: 10 });
    fireEvent.click(screen.getByTestId('timeline-pagination-next'));
    const reset = await screen.findByTestId('timeline-empty-reset');
    fireEvent.click(reset);
    // offset back to 0 means the initial cached page reappears.
    await screen.findByTestId('timeline-list');
  });

  // ── C6 (D-K19e-β-01) — chapter title rendering ────────────────

  it('renders chapter_title when BE provides it (no UUID fallback)', async () => {
    listTimelineMock.mockResolvedValue({
      events: [
        {
          ...EVENT_DUEL,
          chapter_title: 'Chapter 12 — The Bridge Duel',
        },
      ],
      total: 1,
    });
    render(<TimelineTab />, { wrapper: Wrapper });
    const row = await screen.findByTestId('timeline-event-row');
    expect(row.textContent).toContain('Chapter 12 — The Bridge Duel');
    // UUID short NOT rendered when title is present.
    // chapterShort('ch-aaaa-bbbb-cccc-dddd') takes the last 8 chars
    // = 'ccc-dddd' (8 chars, leading dash dropped by slice).
    expect(row.textContent).not.toContain('ccc-dddd');
  });

  it('falls back to UUID short when chapter_title is null (graceful degrade)', async () => {
    listTimelineMock.mockResolvedValue({
      events: [{ ...EVENT_DUEL, chapter_title: null }],
      total: 1,
    });
    render(<TimelineTab />, { wrapper: Wrapper });
    const row = await screen.findByTestId('timeline-event-row');
    // Last 8 chars of the fixture's chapter_id.
    expect(row.textContent).toContain('ccc-dddd');
  });
});
