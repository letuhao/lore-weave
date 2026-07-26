import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { JobMonitor } from '../JobMonitor';
import type { Job } from '../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

const job: Job = {
  service: 'knowledge', job_id: 'j1', owner_user_id: 'u', kind: 'extraction',
  status: 'running', parent_job_id: null, detail_status: null,
  progress: { done: 2, total: 5 }, control_caps: ['pause', 'cancel'], title: 'Extract ch 1-40',
  error: null, model: null, cost_usd: null, tokens_in: null, tokens_out: null, params: null,
  created_at: null, updated_at: '2026-06-16T00:00:00+00:00', child_count: 0,
};

vi.mock('../../hooks/useJob', () => ({ useJob: () => ({ isLoading: false, error: null, data: job }) }));
vi.mock('../../context/JobsStreamProvider', () => ({ useJobLive: () => undefined }));
vi.mock('../JobStatusBadge', () => ({ JobStatusBadge: () => <span data-testid="status-badge" /> }));
vi.mock('../JobControls', () => ({ JobControls: () => <div data-testid="job-controls" /> }));
vi.mock('../JobChildrenTable', () => ({ JobChildrenTable: () => <div data-testid="children-table" /> }));
vi.mock('../JobTableHeader', () => ({ JobTableHeader: () => <div data-testid="table-header" /> }));
vi.mock('../detail/JobProgressPanel', () => ({ JobProgressPanel: () => <div data-testid="progress-panel" /> }));
vi.mock('../detail/JobCostUsagePanel', () => ({ JobCostUsagePanel: () => <div data-testid="cost-panel" /> }));
vi.mock('../detail/JobParametersPanel', () => ({ JobParametersPanel: () => <div data-testid="params-panel" /> }));
vi.mock('../detail/JobMetadataGrid', () => ({ JobMetadataGrid: () => <div data-testid="metadata-grid" /> }));
vi.mock('../detail/JobActivityTimeline', () => ({ JobActivityTimeline: () => <div data-testid="activity-timeline" /> }));

function renderMonitor(hideBack?: boolean) {
  return render(
    <MemoryRouter>
      <JobMonitor service="knowledge" jobId="j1" hideBack={hideBack} />
    </MemoryRouter>,
  );
}

// docs/standards/dockable-gui.md U3/DOCK-7 — the studio JobDetailPanel has no "/jobs" route to
// return to (dock tabs already show what's open), so it hides the breadcrumb instead of
// route-navigating. Omitted (the standalone /jobs/:service/:jobId page): byte-identical.
describe('JobMonitor hideBack (dockable-migration injectable prop)', () => {
  it('omitted: renders the "All jobs" back-breadcrumb <Link> (byte-identical to before)', () => {
    renderMonitor();
    expect(screen.getByRole('link', { name: /All jobs/ })).toHaveAttribute('href', '/jobs');
  });

  it('hideBack=true: omits the breadcrumb entirely (no <Link>)', () => {
    renderMonitor(true);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('still renders the job title regardless of hideBack', () => {
    renderMonitor(true);
    expect(screen.getByText('Extract ch 1-40')).toBeInTheDocument();
  });
});
