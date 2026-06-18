import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { JobsList } from '../JobsList';
import type { Job } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../context/JobsStreamProvider', () => ({
  useJobsConnection: () => 'open',
  useJobLive: () => undefined,
}));

const dashMock = vi.fn();
vi.mock('../../hooks/useJobsDashboard', () => ({ useJobsDashboard: () => dashMock() }));

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

function renderList() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <JobsList />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => dashMock.mockReset());

describe('JobsList', () => {
  it('renders the 4 summary cards with counts', () => {
    dashMock.mockReturnValue(baseDash());
    renderList();
    // counts: active 1, completed 9, failed 2, cancelled 3
    expect(screen.getByText('9')).toBeInTheDocument();
    expect(screen.getByText('summary.completed')).toBeInTheDocument();
  });

  it('shows the empty history state when there are no terminal jobs', () => {
    dashMock.mockReturnValue(baseDash());
    renderList();
    expect(screen.getByText('list.empty')).toBeInTheDocument();
    expect(screen.getByText('list.noActive')).toBeInTheDocument();
  });

  it('renders a History row per job with the detail link', () => {
    dashMock.mockReturnValue(
      baseDash({ history: { data: { items: [job], total: 1, next_cursor: null }, isLoading: false, error: null } }),
    );
    renderList();
    expect(screen.getByRole('link', { name: 'Translate book X' })).toHaveAttribute('href', '/jobs/translation/t1');
  });

  it('a summary card click selects that quick-filter', () => {
    const selectQuick = vi.fn();
    dashMock.mockReturnValue(baseDash({ selectQuick }));
    renderList();
    fireEvent.click(screen.getByText('summary.failed'));
    expect(selectQuick).toHaveBeenCalledWith('failed');
  });
});
