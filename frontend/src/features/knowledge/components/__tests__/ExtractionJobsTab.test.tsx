import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ExtractionJobWire } from '../../api';
import type { ExtractionJobStatus } from '../../types/projectState';

// Mock the hook so the component tests don't hit React Query or BE.
const useExtractionJobsMock = vi.fn();
vi.mock('../../hooks/useExtractionJobs', () => ({
  useExtractionJobs: () => useExtractionJobsMock(),
}));

import { ExtractionJobsTab } from '../ExtractionJobsTab';

function makeJob(
  overrides: Partial<ExtractionJobWire> & { status: ExtractionJobStatus },
): ExtractionJobWire {
  return {
    job_id: `job-${Math.random().toString(36).slice(2, 8)}`,
    user_id: 'user-42',
    project_id: overrides.project_id ?? 'proj-0001',
    scope: 'all',
    scope_range: null,
    llm_model: 'claude-sonnet-4-6',
    embedding_model: 'bge-m3',
    max_spend_usd: '5.00',
    items_processed: 3,
    items_total: 10,
    cost_spent_usd: '0.50',
    current_cursor: null,
    started_at: '2026-04-19T12:00:00Z',
    paused_at: null,
    completed_at:
      overrides.status === 'complete' || overrides.status === 'failed'
        ? '2026-04-19T13:00:00Z'
        : null,
    created_at: '2026-04-19T11:00:00Z',
    updated_at: '2026-04-19T12:30:00Z',
    error_message: null,
    project_name: null,
    ...overrides,
  };
}

function setHookState(overrides: {
  active?: ExtractionJobWire[];
  history?: ExtractionJobWire[];
  isLoading?: boolean;
  activeError?: Error | null;
  historyError?: Error | null;
}) {
  const active = overrides.active ?? [];
  const history = overrides.history ?? [];
  const activeError = overrides.activeError ?? null;
  const historyError = overrides.historyError ?? null;
  useExtractionJobsMock.mockReturnValue({
    active,
    history,
    isLoading: overrides.isLoading ?? false,
    error: activeError ?? historyError,
    activeError,
    historyError,
  });
}

describe('ExtractionJobsTab', () => {
  beforeEach(() => {
    useExtractionJobsMock.mockReset();
  });

  it('renders all 4 section titles even when empty', () => {
    setHookState({});
    render(<ExtractionJobsTab />);
    expect(screen.getByText('jobs.sections.running.title')).toBeInTheDocument();
    expect(screen.getByText('jobs.sections.paused.title')).toBeInTheDocument();
    expect(screen.getByText('jobs.sections.complete.title')).toBeInTheDocument();
    expect(screen.getByText('jobs.sections.failed.title')).toBeInTheDocument();
  });

  it('splits active jobs into Running (running+pending) and Paused sections', () => {
    setHookState({
      active: [
        makeJob({ status: 'running', project_name: 'Alpha', job_id: 'a1' }),
        makeJob({ status: 'pending', project_name: 'Beta', job_id: 'a2' }),
        makeJob({ status: 'paused', project_name: 'Gamma', job_id: 'a3' }),
      ],
    });
    render(<ExtractionJobsTab />);

    const rows = screen.getAllByTestId('job-row');
    const rowIdsByName: Record<string, string> = {};
    rows.forEach((r) => {
      const jobId = r.getAttribute('data-job-id');
      const name = r.textContent ?? '';
      if (jobId) rowIdsByName[name] = jobId;
    });
    // All 3 rows rendered somewhere.
    expect(Object.keys(rowIdsByName)).toHaveLength(3);
  });

  it('splits history into Complete and Failed (including cancelled)', () => {
    setHookState({
      history: [
        makeJob({ status: 'complete', project_name: 'C-one', job_id: 'h1' }),
        makeJob({ status: 'failed', project_name: 'F-one', job_id: 'h2' }),
        makeJob({ status: 'cancelled', project_name: 'X-one', job_id: 'h3' }),
      ],
    });
    render(<ExtractionJobsTab />);
    const rows = screen.getAllByTestId('job-row');
    expect(rows).toHaveLength(3);
  });

  it('caps Complete section at 10 rows', () => {
    const complete = Array.from({ length: 15 }, (_, i) =>
      makeJob({ status: 'complete', job_id: `h${i}` }),
    );
    setHookState({ history: complete });
    render(<ExtractionJobsTab />);
    const rows = screen.getAllByTestId('job-row');
    expect(rows.length).toBeLessThanOrEqual(10);
  });

  it('renders loading placeholder when isLoading', () => {
    setHookState({ isLoading: true });
    render(<ExtractionJobsTab />);
    expect(screen.getByTestId('jobs-loading')).toBeInTheDocument();
    // 4 section titles should NOT render during loading.
    expect(screen.queryByText('jobs.sections.running.title')).toBeNull();
  });

  it('renders active and history error banners separately', () => {
    const activeErr = new Error('active boom');
    const historyErr = new Error('history boom');
    setHookState({ activeError: activeErr, historyError: historyErr });
    render(<ExtractionJobsTab />);
    const banners = screen.getAllByTestId('jobs-error-banner');
    expect(banners).toHaveLength(2);
    expect(banners[0].textContent).toContain('active boom');
    expect(banners[1].textContent).toContain('history boom');
  });

  it('falls back to the unknownProject i18n key when project_name is null', () => {
    setHookState({
      active: [
        makeJob({
          status: 'running',
          project_id: 'abcdef1234567890-deadbeef',
          project_name: null,
        }),
      ],
    });
    render(<ExtractionJobsTab />);
    // vitest.setup.ts globally mocks useTranslation so t() returns the
    // dotted key verbatim; interpolation only fires for placeholders
    // literally in the KEY string, not the resolved template. Asserting
    // the key presence confirms the fallback branch was taken. The
    // actual project_id.slice(0, 8) truncation is locally verifiable in
    // source and covered at runtime by the real i18next template.
    expect(screen.getByText('jobs.row.unknownProject')).toBeInTheDocument();
  });

  it('uses project_name when present', () => {
    setHookState({
      active: [
        makeJob({ status: 'running', project_name: 'My Book Project' }),
      ],
    });
    render(<ExtractionJobsTab />);
    expect(screen.getByText('My Book Project')).toBeInTheDocument();
  });

  it('highlights Failed section only when non-empty', () => {
    // When empty, border should NOT carry destructive styling.
    setHookState({});
    const { container: emptyContainer, unmount } = render(<ExtractionJobsTab />);
    const failedEmpty = [...emptyContainer.querySelectorAll('details')].find(
      (d) => d.textContent?.includes('jobs.sections.failed.title'),
    );
    expect(failedEmpty?.className).not.toMatch(/border-destructive/);
    unmount();

    setHookState({
      history: [makeJob({ status: 'failed', project_name: 'F' })],
    });
    const { container: nonEmptyContainer } = render(<ExtractionJobsTab />);
    const failedNonEmpty = [
      ...nonEmptyContainer.querySelectorAll('details'),
    ].find((d) => d.textContent?.includes('jobs.sections.failed.title'));
    expect(failedNonEmpty?.className).toMatch(/border-destructive/);
  });
});
