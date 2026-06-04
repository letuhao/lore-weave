import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

const jobsStub = vi.hoisted(() => ({
  items: [] as unknown[],
  isLoading: false,
  resume: vi.fn(),
}));
vi.mock('../../hooks/useEnrichmentJobs', () => ({
  useEnrichmentJobs: () => jobsStub,
}));

import { JobsPanel } from '../JobsPanel';
import { EnrichmentProvider } from '../../context/EnrichmentContext';
import type { Job } from '../../types';

const J = (over: Partial<Job> = {}): Job =>
  ({
    job_id: 'job-1',
    project_id: 'proj-9',
    status: 'completed',
    technique: 'recook',
    entity_kind: null,
    book_id: 'book-1',
    proposals_total: 7,
    estimated_cost: 0.5,
    actual_cost: 0.1234,
    max_spend: null,
    error_message: null,
    created_at: '2026-06-01T10:00:00Z',
    ...over,
  } as Job);

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <EnrichmentProvider bookId="book-1">
        <JobsPanel />
      </EnrichmentProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  jobsStub.items = [];
  jobsStub.isLoading = false;
  jobsStub.resume.mockReset();
});

describe('JobsPanel', () => {
  it('shows a skeleton placeholder while isLoading', () => {
    jobsStub.isLoading = true;
    const { container } = renderPanel();
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
    expect(screen.queryByText('jobs.none')).toBeNull();
  });

  it('shows the jobs.none empty state when there are no jobs', () => {
    jobsStub.items = [];
    renderPanel();
    expect(screen.getByText('jobs.none')).toBeInTheDocument();
  });

  it('renders the column headers as i18n keys', () => {
    jobsStub.items = [J()];
    renderPanel();
    expect(screen.getByText('jobs.col.technique')).toBeInTheDocument();
    expect(screen.getByText('jobs.col.status')).toBeInTheDocument();
    expect(screen.getByText('jobs.col.proposals')).toBeInTheDocument();
    expect(screen.getByText('jobs.col.cost')).toBeInTheDocument();
    expect(screen.getByText('jobs.col.created')).toBeInTheDocument();
  });

  it('renders a row per job with tier+technique, status badge, proposals_total, cost, and created_at', () => {
    jobsStub.items = [J({ technique: 'recook', status: 'completed', proposals_total: 7, actual_cost: 0.1234 })];
    renderPanel();
    // tierOf('recook') === 'P3'; rendered as "P3 · recook"
    expect(screen.getByText('P3 · recook')).toBeInTheDocument();
    // StatusBadge label is the i18n key the panel builds: jobs.status.<status>
    expect(screen.getByText('jobs.status.completed')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    // actual_cost.toFixed(4) prefixed with $
    expect(screen.getByText('$0.1234')).toBeInTheDocument();
    // created_at is rendered via toLocaleString()
    expect(
      screen.getByText(new Date('2026-06-01T10:00:00Z').toLocaleString()),
    ).toBeInTheDocument();
  });

  it('renders the P-tier label per technique via tierOf', () => {
    jobsStub.items = [
      J({ job_id: 'a', technique: 'fabrication' }),
      J({ job_id: 'b', technique: 'template' }),
    ];
    renderPanel();
    expect(screen.getByText('P2 · fabrication')).toBeInTheDocument();
    expect(screen.getByText('P1 · template')).toBeInTheDocument();
  });

  it('maps a gate-locked failure to the friendly i18n key, keeping the raw in the title (#4, LE-PROD)', () => {
    const raw = "refused: technique 'fabrication' gate-locked (eval not cleared)";
    jobsStub.items = [J({ status: 'failed', error_message: raw })];
    renderPanel();
    const el = screen.getByTestId('job-error-job-1');
    expect(el).toHaveTextContent('jobs.error.gateLocked');
    expect(el).toHaveAttribute('title', raw); // raw preserved for debugging/audit
  });

  it('maps a raw exception repr to a generic internal-error line (no scary traceback shown)', () => {
    const raw = "KeyError: <EntityKind.CHARACTER: 'character'>";
    jobsStub.items = [J({ status: 'failed', error_message: raw })];
    renderPanel();
    const el = screen.getByTestId('job-error-job-1');
    expect(el).toHaveTextContent('jobs.error.internal');
    expect(el).not.toHaveTextContent('EntityKind'); // the raw repr is NOT the primary text
    expect(el).toHaveAttribute('title', raw); // but still inspectable on hover
  });

  it('shows an already-human error message verbatim (no over-mapping)', () => {
    const raw = 'no gaps to enrich (all targets fully described)';
    jobsStub.items = [J({ status: 'failed', error_message: raw })];
    renderPanel();
    expect(screen.getByTestId('job-error-job-1')).toHaveTextContent(raw);
  });

  it('does NOT show an error line for a completed job with no message', () => {
    jobsStub.items = [J({ status: 'completed', error_message: null })];
    renderPanel();
    expect(screen.queryByTestId('job-error-job-1')).toBeNull();
  });

  it('shows the slice-B insufficient-grounding note on a COMPLETED job as muted info (not error)', () => {
    jobsStub.items = [
      J({ status: 'completed', error_message: 'insufficient_grounding: 2 gap(s) — paste context or use fabrication' }),
    ];
    renderPanel();
    const el = screen.getByTestId('job-error-job-1');
    expect(el).toHaveTextContent('jobs.error.insufficientGrounding');
    // a note on a non-failed job is muted, NOT destructive-red
    expect(el.className).toContain('text-muted-foreground');
    expect(el.className).not.toContain('text-destructive');
  });

  it('shows spent-vs-cap when a cost cap is set (#5)', () => {
    jobsStub.items = [J({ actual_cost: 0.1234, max_spend: 2 })];
    renderPanel();
    const cost = screen.getByTestId('job-cost-job-1');
    expect(cost).toHaveTextContent('$0.1234');
    expect(cost).toHaveTextContent('/ $2.00');
  });

  it('shows the Resume button only for a paused job', () => {
    jobsStub.items = [J({ status: 'paused' })];
    renderPanel();
    expect(screen.getByText('jobs.resume')).toBeInTheDocument();
  });

  it('does NOT show the Resume button for completed or running jobs', () => {
    jobsStub.items = [
      J({ job_id: 'c', status: 'completed' }),
      J({ job_id: 'r', status: 'running' }),
    ];
    renderPanel();
    expect(screen.queryByText('jobs.resume')).toBeNull();
  });

  it('clicking Resume calls resume(job) with that paused job', () => {
    const paused = J({ status: 'paused' });
    jobsStub.items = [paused];
    renderPanel();
    fireEvent.click(screen.getByText('jobs.resume'));
    expect(jobsStub.resume).toHaveBeenCalledTimes(1);
    expect(jobsStub.resume).toHaveBeenCalledWith(paused);
  });
});
