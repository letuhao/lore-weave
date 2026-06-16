import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { JobRow } from '../JobRow';
import type { Job } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const job: Job = {
  service: 'knowledge', job_id: 'j1', owner_user_id: 'u', kind: 'extraction',
  status: 'running', parent_job_id: null, detail_status: null,
  progress: { done: 2, total: 5 }, control_caps: ['pause', 'cancel'], title: 'Extract ch 1-40',
  error: null, created_at: null, updated_at: '2026-06-16T00:00:00+00:00', child_count: 0,
};

function renderRow(j: Job) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <JobRow job={j} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('JobRow deep-link + grouping', () => {
  it('non-campaign job links to /jobs/:service/:jobId', () => {
    renderRow(job);
    expect(screen.getByRole('link', { name: 'Extract ch 1-40' })).toHaveAttribute(
      'href', '/jobs/knowledge/j1',
    );
  });

  it('campaign job deep-links to the existing campaign monitor', () => {
    renderRow({ ...job, kind: 'campaign', title: 'My campaign', job_id: 'c9' });
    expect(screen.getByRole('link', { name: 'My campaign' })).toHaveAttribute(
      'href', '/campaigns/c9',
    );
  });

  it('shows a child-count badge + expander when child_count > 0', () => {
    renderRow({ ...job, kind: 'campaign', job_id: 'c9', child_count: 3 });
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'list.toggleChildren' })).toBeInTheDocument();
  });

  it('renders control buttons gated on control_caps', () => {
    renderRow(job);
    expect(screen.getByText('controls.pause')).toBeInTheDocument();
    expect(screen.queryByText('controls.resume')).not.toBeInTheDocument();
  });
});
