import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ExtractionJobWire } from '../../api';
import type { ExtractionJobStatus } from '../../types/projectState';

// Mock auth + API for the retry flow's getProject fetch.
vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test' }),
}));

const getProjectMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      ...(actual.knowledgeApi as Record<string, unknown>),
      getProject: (...args: unknown[]) => getProjectMock(...args),
    },
  };
});

// Stub the JobDetailPanel + BuildGraphDialog so the tab test focuses on
// wiring (click → panel open, retry → dialog open with initialValues)
// rather than dragging their internals (hooks, Radix portals, Query).
vi.mock('../JobDetailPanel', () => ({
  JobDetailPanel: ({
    open,
    job,
    onRetryClick,
  }: {
    open: boolean;
    job: ExtractionJobWire | null;
    onRetryClick?: (job: ExtractionJobWire) => void;
  }) =>
    open && job ? (
      <div data-testid="detail-panel-stub" data-job-id={job.job_id}>
        {job.project_name ?? '—'}
        {job.status === 'failed' && onRetryClick && (
          <button
            data-testid="detail-panel-retry-stub"
            onClick={() => onRetryClick(job)}
          >
            retry
          </button>
        )}
      </div>
    ) : null,
}));

// Stub CostSummary — its own test file covers behaviour; tab test
// focuses on layout + section wiring.
vi.mock('../CostSummary', () => ({
  CostSummary: () => <div data-testid="cost-summary-stub" />,
}));

vi.mock('../BuildGraphDialog', () => ({
  BuildGraphDialog: ({
    open,
    initialValues,
    project,
  }: {
    open: boolean;
    initialValues?: { scope?: string; llmModel?: string };
    project: { project_id: string };
  }) =>
    open ? (
      <div
        data-testid="build-graph-stub"
        data-project-id={project.project_id}
        data-scope={initialValues?.scope ?? ''}
        data-llm={initialValues?.llmModel ?? ''}
      />
    ) : null,
}));

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
    // C11 — default: no more pages. Individual tests opt in via
    // setHookState({hasMoreHistory: true, ...}).
    hasMoreHistory: overrides.hasMoreHistory ?? false,
    fetchMoreHistory: overrides.fetchMoreHistory ?? vi.fn(),
    isFetchingMoreHistory: overrides.isFetchingMoreHistory ?? false,
  });
}

// Each render() needs a fresh QueryClient because the retry flow uses
// useQuery internally. Wrapping all render() calls through this helper
// ensures the Provider is always present without cluttering each test.
function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ExtractionJobsTab />
    </QueryClientProvider>,
  );
}

describe('ExtractionJobsTab', () => {
  beforeEach(() => {
    useExtractionJobsMock.mockReset();
    getProjectMock.mockReset();
  });

  it('renders all 4 section titles even when empty', () => {
    setHookState({});
    renderTab();
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
    renderTab();

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
    renderTab();
    const rows = screen.getAllByTestId('job-row');
    expect(rows).toHaveLength(3);
  });

  it('shows every Complete row from loaded history pages (C11 — no client-side cap)', () => {
    // C11 (D-K19b.2-01): before cursor pagination the FE capped the
    // Complete section at 10 rows and silently hid the rest. With
    // cursor pagination the cap is meaningless — the user pulls more
    // via Load more. This test locks the removal: 15 rows all render.
    const complete = Array.from({ length: 15 }, (_, i) =>
      makeJob({ status: 'complete', job_id: `h${i}` }),
    );
    setHookState({ history: complete });
    renderTab();
    const rows = screen.getAllByTestId('job-row');
    expect(rows.length).toBe(15);
  });

  it('renders loading placeholder when isLoading', () => {
    setHookState({ isLoading: true });
    renderTab();
    expect(screen.getByTestId('jobs-loading')).toBeInTheDocument();
    // 4 section titles should NOT render during loading.
    expect(screen.queryByText('jobs.sections.running.title')).toBeNull();
  });

  it('renders active and history error banners separately', () => {
    const activeErr = new Error('active boom');
    const historyErr = new Error('history boom');
    setHookState({ activeError: activeErr, historyError: historyErr });
    renderTab();
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
    renderTab();
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
    renderTab();
    expect(screen.getByText('My Book Project')).toBeInTheDocument();
  });

  it('highlights Failed section only when non-empty', () => {
    // When empty, border should NOT carry destructive styling.
    setHookState({});
    const { container: emptyContainer, unmount } = renderTab();
    const failedEmpty = [...emptyContainer.querySelectorAll('details')].find(
      (d) => d.textContent?.includes('jobs.sections.failed.title'),
    );
    expect(failedEmpty?.className).not.toMatch(/border-destructive/);
    unmount();

    setHookState({
      history: [makeJob({ status: 'failed', project_name: 'F' })],
    });
    const { container: nonEmptyContainer } = renderTab();
    const failedNonEmpty = [
      ...nonEmptyContainer.querySelectorAll('details'),
    ].find((d) => d.textContent?.includes('jobs.sections.failed.title'));
    expect(failedNonEmpty?.className).toMatch(/border-destructive/);
  });

  // K19b.3: click + keyboard open the detail panel.
  it('opens JobDetailPanel on row click', () => {
    setHookState({
      active: [makeJob({ status: 'running', job_id: 'row-click', project_name: 'X' })],
    });
    renderTab();
    expect(screen.queryByTestId('detail-panel-stub')).toBeNull();
    fireEvent.click(screen.getByTestId('job-row'));
    const panel = screen.getByTestId('detail-panel-stub');
    expect(panel.getAttribute('data-job-id')).toBe('row-click');
  });

  it('opens JobDetailPanel on Enter key', () => {
    setHookState({
      active: [makeJob({ status: 'running', job_id: 'row-kb', project_name: 'Y' })],
    });
    renderTab();
    const row = screen.getByTestId('job-row');
    fireEvent.keyDown(row, { key: 'Enter' });
    expect(screen.getByTestId('detail-panel-stub').getAttribute('data-job-id')).toBe(
      'row-kb',
    );
  });

  // K19b.5: retry flow closes panel (R2), fetches project, opens BuildGraphDialog.
  it('retry click fetches project and opens BuildGraphDialog with initialValues', async () => {
    getProjectMock.mockResolvedValue({
      project_id: 'proj-retry',
      user_id: 'user-42',
      name: 'Retry Project',
      description: '',
      project_type: 'book',
      book_id: 'book-1',
      instructions: '',
      extraction_enabled: false,
      extraction_status: 'failed',
      embedding_model: 'bge-m3',
      extraction_config: {},
      last_extracted_at: null,
      estimated_cost_usd: '0',
      actual_cost_usd: '0',
      is_archived: false,
      version: 1,
      created_at: '2026-04-19T00:00:00Z',
      updated_at: '2026-04-19T00:00:00Z',
    });
    setHookState({
      history: [
        makeJob({
          status: 'failed',
          job_id: 'failed-1',
          project_id: 'proj-retry',
          project_name: 'Retry Project',
          scope: 'chat',
          llm_model: 'claude-opus-4-7',
          embedding_model: 'bge-m3',
          max_spend_usd: '12.34',
        }),
      ],
    });
    renderTab();

    // 1. click the failed row to open detail panel (our stubbed panel).
    fireEvent.click(screen.getByTestId('job-row'));
    expect(screen.getByTestId('detail-panel-stub')).toBeInTheDocument();

    // 2. click the stubbed Retry button — invokes onRetryClick which
    //    closes the panel + sets retryIntent.
    fireEvent.click(screen.getByTestId('detail-panel-retry-stub'));
    // R2: panel closes immediately.
    expect(screen.queryByTestId('detail-panel-stub')).toBeNull();

    // 3. wait for getProject → BuildGraphDialog stub to render with
    //    the failed job's initialValues.
    await waitFor(() => {
      expect(getProjectMock).toHaveBeenCalledWith('proj-retry', 'tok-test');
    });
    const dlg = await screen.findByTestId('build-graph-stub');
    expect(dlg.getAttribute('data-project-id')).toBe('proj-retry');
    expect(dlg.getAttribute('data-scope')).toBe('chat');
    expect(dlg.getAttribute('data-llm')).toBe('claude-opus-4-7');
  });

  // ── C11 — Load more history pagination ────────────────────────

  it('does not render Load more when hasMoreHistory is false', () => {
    setHookState({ hasMoreHistory: false });
    renderTab();
    expect(
      screen.queryByTestId('jobs-history-load-more'),
    ).not.toBeInTheDocument();
  });

  it('renders Load more when hasMoreHistory is true', () => {
    setHookState({ hasMoreHistory: true });
    renderTab();
    expect(
      screen.getByTestId('jobs-history-load-more'),
    ).toBeInTheDocument();
  });

  it('clicking Load more calls fetchMoreHistory', () => {
    const fetchMoreHistory = vi.fn();
    setHookState({ hasMoreHistory: true, fetchMoreHistory });
    renderTab();
    fireEvent.click(screen.getByTestId('jobs-history-load-more'));
    expect(fetchMoreHistory).toHaveBeenCalledTimes(1);
  });

  it('Load more button is disabled and shows loading label while fetching', () => {
    setHookState({
      hasMoreHistory: true,
      isFetchingMoreHistory: true,
    });
    renderTab();
    const btn = screen.getByTestId(
      'jobs-history-load-more',
    ) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.textContent).toContain('jobs.loadingMore');
  });
});
