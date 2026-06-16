import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { JobsList } from '../JobsList';
import type { Job } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const listMock = vi.fn();
vi.mock('../../hooks/useJobsList', () => ({ useJobsList: () => listMock() }));

const job: Job = {
  service: 'translation', job_id: 't1', owner_user_id: 'u', kind: 'translation',
  status: 'running', parent_job_id: null, detail_status: null, progress: null,
  control_caps: ['cancel'], title: 'Translate book X', error: null,
  created_at: null, updated_at: '2026-06-16T00:00:00+00:00', child_count: 0,
};

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

describe('JobsList', () => {
  it('shows the empty state when there are no jobs', () => {
    listMock.mockReturnValue({ data: { pages: [{ items: [], next_cursor: null }] }, isLoading: false, error: null, hasNextPage: false, fetchNextPage: vi.fn(), isFetchingNextPage: false });
    renderList();
    expect(screen.getByText('list.empty')).toBeInTheDocument();
  });

  it('renders a row per job with the detail link', () => {
    listMock.mockReturnValue({ data: { pages: [{ items: [job], next_cursor: null }] }, isLoading: false, error: null, hasNextPage: false, fetchNextPage: vi.fn(), isFetchingNextPage: false });
    renderList();
    expect(screen.getByRole('link', { name: 'Translate book X' })).toHaveAttribute('href', '/jobs/translation/t1');
  });
});
