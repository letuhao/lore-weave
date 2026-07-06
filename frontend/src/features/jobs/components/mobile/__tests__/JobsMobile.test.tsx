import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { JobsMobile } from '../JobsMobile';
import type { Job } from '../../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../../context/JobsStreamProvider', () => ({
  useJobsConnection: () => 'open',
  useJobLive: () => undefined,
}));

const dashMock = vi.fn();
vi.mock('../../../hooks/useJobsDashboard', () => ({ useJobsDashboard: () => dashMock() }));

const job: Job = {
  service: 'translation', job_id: 't1', owner_user_id: 'u', kind: 'translation',
  status: 'completed', parent_job_id: null, detail_status: null, progress: null,
  control_caps: [], title: 'Translate book X', error: null,
  model: 'gemma', cost_usd: 0.02, tokens_in: 12000, tokens_out: 9000, params: null,
  created_at: '2026-06-16T00:00:00+00:00', updated_at: '2026-06-16T00:00:00+00:00', child_count: 0,
};

function baseDash(over: Record<string, unknown> = {}) {
  return {
    quick: 'active',
    selectQuick: vi.fn(),
    kind: '',
    changeKind: vi.fn(),
    rawQ: '',
    changeQ: vi.fn(),
    showActive: true,
    summary: { data: { active: 1, completed: 9, failed: 2, cancelled: 3 } },
    active: { data: { pages: [{ items: [], next_cursor: null }] }, isLoading: false, error: null, hasNextPage: false, fetchNextPage: vi.fn(), isFetchingNextPage: false },
    history: { data: { items: [], total: 0, next_cursor: null }, isLoading: false, error: null },
    page: 0,
    setPage: vi.fn(),
    pageSize: 50,
    changePageSize: vi.fn(),
    ...over,
  };
}

function renderMobile(onOpenDetail?: (service: string, jobId: string) => void) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <JobsMobile onOpenDetail={onOpenDetail} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => dashMock.mockReset());

// docs/standards/dockable-gui.md U3 — same injectable-prop convention as JobRow/JobsList,
// applied to the dedicated mobile card list (JobsListPanel picks this shell on narrow viewports).
describe('JobsMobile onOpenDetail (dockable-migration injectable prop)', () => {
  it('omitted: a History card renders the plain <Link> (byte-identical to the standalone /jobs page)', () => {
    dashMock.mockReturnValue(
      baseDash({ history: { data: { items: [job], total: 1, next_cursor: null }, isLoading: false, error: null } }),
    );
    renderMobile();
    expect(screen.getByRole('link', { name: 'Translate book X' })).toHaveAttribute('href', '/jobs/translation/t1');
  });

  it('provided: renders a button (no <Link>) and calls back with service/jobId', () => {
    const onOpenDetail = vi.fn();
    dashMock.mockReturnValue(
      baseDash({ history: { data: { items: [job], total: 1, next_cursor: null }, isLoading: false, error: null } }),
    );
    renderMobile(onOpenDetail);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Translate book X' }));
    expect(onOpenDetail).toHaveBeenCalledWith('translation', 't1');
  });

  // /review-impl HIGH fix — same campaign-deep-link gap as JobRow.tsx, duplicated here since
  // JobCard has its own independent onOpenDetail branch.
  it('campaign job keeps the real <Link> to /campaigns/:id even when onOpenDetail is provided', () => {
    const onOpenDetail = vi.fn();
    const campaignJob = { ...job, kind: 'campaign', title: 'My campaign', job_id: 'c9' };
    dashMock.mockReturnValue(
      baseDash({ history: { data: { items: [campaignJob], total: 1, next_cursor: null }, isLoading: false, error: null } }),
    );
    renderMobile(onOpenDetail);
    expect(screen.queryByRole('button', { name: 'My campaign' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'My campaign' })).toHaveAttribute('href', '/campaigns/c9');
    expect(onOpenDetail).not.toHaveBeenCalled();
  });
});
