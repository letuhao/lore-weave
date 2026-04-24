import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ExtractionJobWire } from '../../api';
import * as formatMinutesModule from '@/lib/formatMinutes';

// Mock knowledgeApi + auth before component import.
vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test' }),
}));

const pauseMock = vi.fn();
const resumeMock = vi.fn();
const cancelMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      pauseExtraction: (...args: unknown[]) => pauseMock(...args),
      resumeExtraction: (...args: unknown[]) => resumeMock(...args),
      cancelExtraction: (...args: unknown[]) => cancelMock(...args),
    },
  };
});

const toastErrorMock = vi.fn();
vi.mock('sonner', () => ({
  toast: { error: (...args: unknown[]) => toastErrorMock(...args) },
}));

// useJobProgressRate is mocked to a deterministic shape so the panel
// test doesn't depend on EMA timing. Mutable via `useJobProgressRateMock`
// so individual tests can assert the ETA render path (C7).
const useJobProgressRateMock = vi.fn(() => ({
  minutesRemaining: null as number | null,
  itemsPerSecond: null as number | null,
}));
vi.mock('../../hooks/useJobProgressRate', () => ({
  useJobProgressRate: () => useJobProgressRateMock(),
}));

// K19b.8: stub JobLogsPanel so we don't drag in useJobLogs + its
// API call chain. Panel-level tests cover the real component.
vi.mock('../JobLogsPanel', () => ({
  JobLogsPanel: ({ jobId }: { jobId: string }) => (
    <div data-testid="job-logs-panel-stub" data-job-id={jobId} />
  ),
}));

import { JobDetailPanel } from '../JobDetailPanel';

function makeJob(
  overrides: Partial<ExtractionJobWire> & { status: ExtractionJobWire['status'] },
): ExtractionJobWire {
  return {
    job_id: 'job-1',
    user_id: 'u1',
    project_id: 'proj-abc',
    scope: 'chapters',
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
      overrides.status === 'complete' ||
      overrides.status === 'failed' ||
      overrides.status === 'cancelled'
        ? '2026-04-19T13:00:00Z'
        : null,
    created_at: '2026-04-19T11:00:00Z',
    updated_at: '2026-04-19T12:30:00Z',
    error_message: overrides.status === 'failed' ? 'boom' : null,
    project_name: 'Alpha Book',
    // C6: fixture default = no chapter title. Tests opt in by
    // overriding when they want to exercise the "Current chapter"
    // section.
    current_chapter_title: null,
    ...overrides,
  };
}

function renderPanel(
  job: ExtractionJobWire | null,
  onRetryClick = vi.fn(),
  onOpenChange = vi.fn(),
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <JobDetailPanel
        open={true}
        onOpenChange={onOpenChange}
        job={job}
        onRetryClick={onRetryClick}
      />
    </QueryClientProvider>,
  );
  return { ...utils, qc, onRetryClick, onOpenChange };
}

describe('JobDetailPanel', () => {
  beforeEach(() => {
    pauseMock.mockReset();
    resumeMock.mockReset();
    cancelMock.mockReset();
    toastErrorMock.mockReset();
    // Reset hook mock to the default "hide ETA" shape. Individual tests
    // opt in to numeric values to exercise the ETA render path.
    useJobProgressRateMock.mockReturnValue({
      minutesRemaining: null,
      itemsPerSecond: null,
    });
  });

  it('renders project_name and status', () => {
    renderPanel(makeJob({ status: 'running', project_name: 'Alpha Book' }));
    expect(screen.getByText('Alpha Book')).toBeInTheDocument();
    expect(screen.getByTestId('job-detail-status')).toHaveTextContent('running');
  });

  it('shows Pause + Cancel for running, not Resume', () => {
    renderPanel(makeJob({ status: 'running' }));
    expect(screen.getByTestId('job-detail-pause')).toBeInTheDocument();
    expect(screen.getByTestId('job-detail-cancel')).toBeInTheDocument();
    expect(screen.queryByTestId('job-detail-resume')).toBeNull();
  });

  it('shows Resume + Cancel for paused, not Pause', () => {
    renderPanel(makeJob({ status: 'paused' }));
    expect(screen.getByTestId('job-detail-resume')).toBeInTheDocument();
    expect(screen.getByTestId('job-detail-cancel')).toBeInTheDocument();
    expect(screen.queryByTestId('job-detail-pause')).toBeNull();
  });

  it('shows error block only on failed status', () => {
    const { unmount } = renderPanel(
      makeJob({ status: 'complete', error_message: 'should-not-render' }),
    );
    expect(screen.queryByTestId('job-detail-error')).toBeNull();
    unmount();

    renderPanel(makeJob({ status: 'failed', error_message: 'rate limit exceeded' }));
    const errorBlock = screen.getByTestId('job-detail-error');
    expect(errorBlock).toHaveTextContent('rate limit exceeded');
  });

  it('shows Retry CTA only when status=failed AND onRetryClick provided', () => {
    // failed + no onRetryClick → no button. Bypass renderPanel's default
    // `onRetryClick = vi.fn()` by rendering the component directly.
    const qc1 = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { unmount } = render(
      <QueryClientProvider client={qc1}>
        <JobDetailPanel
          open={true}
          onOpenChange={vi.fn()}
          job={makeJob({ status: 'failed' })}
          // onRetryClick omitted on purpose.
        />
      </QueryClientProvider>,
    );
    expect(screen.queryByTestId('job-detail-retry')).toBeNull();
    unmount();

    // cancelled + onRetryClick → no button (R3: only 'failed', not 'cancelled')
    const { unmount: unmount2 } = renderPanel(
      makeJob({ status: 'cancelled' }),
      vi.fn(),
    );
    expect(screen.queryByTestId('job-detail-retry')).toBeNull();
    unmount2();

    // failed + onRetryClick → visible, click forwards the job.
    const onRetry = vi.fn();
    renderPanel(makeJob({ status: 'failed' }), onRetry);
    const retryBtn = screen.getByTestId('job-detail-retry');
    fireEvent.click(retryBtn);
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onRetry.mock.calls[0][0].status).toBe('failed');
  });

  it('invokes knowledgeApi.pauseExtraction with project_id when Pause clicked', async () => {
    pauseMock.mockResolvedValue({});
    const { onOpenChange } = renderPanel(
      makeJob({ status: 'running', project_id: 'proj-abc' }),
    );
    fireEvent.click(screen.getByTestId('job-detail-pause'));
    await waitFor(() => {
      expect(pauseMock).toHaveBeenCalledWith('proj-abc', 'tok-test');
    });
    // On success the panel asks the parent to close.
    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it('toasts and keeps panel open when an action fails', async () => {
    cancelMock.mockRejectedValue(new Error('network down'));
    const { onOpenChange } = renderPanel(makeJob({ status: 'running' }));
    fireEvent.click(screen.getByTestId('job-detail-cancel'));
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalled();
    });
    // Parent was NOT asked to close on failure.
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  // ── C6 (D-K19b.3-01) — Current chapter section ──────────────────

  it('renders Current chapter section when current_chapter_title is set', () => {
    renderPanel(
      makeJob({
        status: 'running',
        current_cursor: { scope: 'chapters', last_chapter_id: 'some-uuid' },
        current_chapter_title: 'Chapter 12 — The Bridge Duel',
      }),
    );
    const section = screen.getByTestId('job-detail-current-chapter');
    expect(section).toBeInTheDocument();
    expect(section.textContent).toContain('Chapter 12 — The Bridge Duel');
  });

  it('hides Current chapter section when current_chapter_title is null', () => {
    // Happens for: chat-scope jobs, completed/failed (cursor cleared
    // or no last_chapter_id), and all book-service unavailable paths.
    renderPanel(
      makeJob({
        status: 'running',
        current_cursor: { scope: 'chat', last_pending_id: 'some-uuid' },
        current_chapter_title: null,
      }),
    );
    expect(
      screen.queryByTestId('job-detail-current-chapter'),
    ).not.toBeInTheDocument();
  });

  // ── C7 (D-K19b.3-02) — humanised ETA render path ─────────────────

  it('renders ETA line and passes minutesRemaining through formatMinutes (C7 wire)', () => {
    // Locks the wire: useJobProgressRate → JobDetailPanel line 173
    // null-gate → formatMinutes called with the number → result fed as
    // `duration` to t('jobs.detail.eta', ...). i18n interpolation is
    // covered by the locale-placeholder test in projectState.test.ts;
    // formatMinutes output is covered by formatMinutes.test.ts. This
    // test only proves the render path + call site, which nothing
    // guarded before C7 /review-impl.
    const spy = vi.spyOn(formatMinutesModule, 'formatMinutes');
    useJobProgressRateMock.mockReturnValue({
      minutesRemaining: 125,
      itemsPerSecond: 0.5,
    });
    renderPanel(makeJob({ status: 'running' }));
    expect(screen.getByTestId('job-detail-eta')).toBeInTheDocument();
    expect(spy).toHaveBeenCalledWith(125);
    spy.mockRestore();
  });

  it('hides ETA line when minutesRemaining is null', () => {
    // Default mock returns null — ensures consumer null-gate (line 173)
    // stays in place so paused / completed / non-running jobs don't
    // render a phantom ETA.
    renderPanel(makeJob({ status: 'paused' }));
    expect(screen.queryByTestId('job-detail-eta')).not.toBeInTheDocument();
  });
});
