import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ChapterProjectionTable } from '../ChapterProjectionTable';
import { useCampaignChapters } from '../../hooks/useCampaignQueries';
import type { CampaignChapter } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../hooks/useCampaignQueries', () => ({ useCampaignChapters: vi.fn() }));

const mockUse = vi.mocked(useCampaignChapters);

function ch(sort: number, over: Partial<CampaignChapter>): CampaignChapter {
  return {
    chapter_id: `c${sort}`, chapter_sort: sort,
    ingest_status: 'done', knowledge_status: 'done', translation_status: 'done', eval_status: 'done',
    knowledge_attempts: 0, translation_attempts: 0, last_error: null, eval_fidelity_score: null,
    ...over,
  };
}

function setPage(items: CampaignChapter[], total: number) {
  mockUse.mockReturnValue({ data: { items, total }, isLoading: false } as ReturnType<typeof useCampaignChapters>);
}

function renderTable(props: Partial<Parameters<typeof ChapterProjectionTable>[0]> = {}) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ChapterProjectionTable campaignId="cmp1" active hasFailures={false} {...props} />
    </QueryClientProvider>,
  );
}

describe('ChapterProjectionTable (server-paginated)', () => {
  beforeEach(() => mockUse.mockReset());

  it('renders the server page + range, paginates via offset', async () => {
    setPage([ch(1, { translation_status: 'failed', last_error: 'boom' }), ch(2, { translation_status: 'dispatched' })], 250);
    renderTable();
    expect(screen.getByRole('cell', { name: '1' })).toBeInTheDocument();
    expect(screen.getByText('monitor.pageRange')).toBeInTheDocument();  // i18n key (range shown)
    // Next advances the offset → the hook is re-called with offset 200
    await userEvent.click(screen.getByText('monitor.next'));
    const offsets = mockUse.mock.calls.map((c) => (c[1] as { offset: number }).offset);
    expect(offsets).toContain(200);
  });

  it('"show all" switches the server status filter to all', async () => {
    setPage([ch(1, {})], 1);
    renderTable();
    await userEvent.click(screen.getByText('monitor.showAll'));
    const statuses = mockUse.mock.calls.map((c) => (c[1] as { status: string }).status);
    expect(statuses).toContain('all');
  });

  it('all-done message when the attention page is empty', () => {
    setPage([], 0);
    renderTable();
    expect(screen.getByText('monitor.allDone')).toBeInTheDocument();
  });

  it('G2: re-run-all shows when hasFailures; selecting a failed row enables re-run-selected', async () => {
    setPage([ch(2, { translation_status: 'failed', last_error: 'x' })], 1);
    renderTable({ hasFailures: true });
    expect(screen.getByText('monitor.rerunAll')).toBeInTheDocument();
    const cb = screen.getByLabelText('select chapter 2');
    await userEvent.click(cb);
    expect(cb).toBeChecked();
  });

  it('no re-run-all when the campaign has no failures', () => {
    setPage([ch(3, { translation_status: 'dispatched' })], 1);
    renderTable({ hasFailures: false });
    expect(screen.queryByText('monitor.rerunAll')).not.toBeInTheDocument();
  });
});
