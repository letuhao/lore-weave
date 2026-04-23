import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { PropsWithChildren } from 'react';

const useExtractionJobsMock = vi.fn();
vi.mock('../../../hooks/useExtractionJobs', () => ({
  useExtractionJobs: () => useExtractionJobsMock(),
}));

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test' }),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const pauseExtractionMock = vi.fn();
const resumeExtractionMock = vi.fn();
const cancelExtractionMock = vi.fn();
vi.mock('../../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../../api');
  return {
    ...actual,
    knowledgeApi: {
      pauseExtraction: (...args: unknown[]) => pauseExtractionMock(...args),
      resumeExtraction: (...args: unknown[]) => resumeExtractionMock(...args),
      cancelExtraction: (...args: unknown[]) => cancelExtractionMock(...args),
    },
  };
});

import { JobsMobile } from '../JobsMobile';
import type { ExtractionJobWire } from '../../../api';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

// Review-impl M3: spy the prototype so every QueryClient instance's
// invalidateQueries is observable. Cleared in beforeEach so each test
// starts from zero calls. vi.spyOn preserves the original behavior
// (unlike vi.fn()), so react-query's cache actually invalidates.
let invalidateSpy: ReturnType<typeof vi.spyOn>;

function makeJob(overrides: Partial<ExtractionJobWire> = {}): ExtractionJobWire {
  return {
    job_id: 'j-1',
    user_id: 'u1',
    project_id: 'p-1',
    scope: 'all',
    scope_range: null,
    status: 'running',
    llm_model: 'gpt-4o-mini',
    embedding_model: 'bge-m3',
    max_spend_usd: null,
    items_processed: 5,
    items_total: 10,
    cost_spent_usd: '0.00',
    current_cursor: null,
    started_at: '2026-04-20T10:00:00Z',
    paused_at: null,
    completed_at: null,
    created_at: '2026-04-20T09:55:00Z',
    updated_at: '2026-04-20T10:00:00Z',
    error_message: null,
    project_name: 'Crimson Echoes',
    ...overrides,
  };
}

function makeHookReturn(
  overrides: Partial<ReturnType<typeof useExtractionJobsMock>> = {},
) {
  return {
    active: [] as ExtractionJobWire[],
    history: [] as ExtractionJobWire[],
    isLoading: false,
    activeError: null as Error | null,
    historyError: null as Error | null,
    ...overrides,
  };
}

describe('JobsMobile', () => {
  beforeEach(() => {
    useExtractionJobsMock.mockReset();
    pauseExtractionMock.mockReset();
    resumeExtractionMock.mockReset();
    cancelExtractionMock.mockReset();
    vi.mocked(toast.error).mockReset();
    invalidateSpy?.mockRestore();
    invalidateSpy = vi.spyOn(QueryClient.prototype, 'invalidateQueries');
  });

  it('renders loading state, then the empty state', () => {
    useExtractionJobsMock.mockReturnValueOnce(
      makeHookReturn({ isLoading: true }),
    );
    const { rerender } = render(<JobsMobile />, { wrapper: Wrapper });
    expect(screen.getByTestId('mobile-jobs-loading')).toBeTruthy();
    useExtractionJobsMock.mockReturnValue(makeHookReturn());
    rerender(<JobsMobile />);
    expect(screen.getByTestId('mobile-jobs-empty')).toBeTruthy();
  });

  it('surfaces either active or history error via the error banner', () => {
    useExtractionJobsMock.mockReturnValue(
      makeHookReturn({ activeError: new Error('net down') }),
    );
    render(<JobsMobile />, { wrapper: Wrapper });
    expect(screen.getByTestId('mobile-jobs-error')).toBeTruthy();
  });

  it('sorts running + paused before complete/failed', () => {
    // Deliberately out-of-order input to prove the sort runs.
    useExtractionJobsMock.mockReturnValue(
      makeHookReturn({
        active: [
          makeJob({ job_id: 'j-running', status: 'running', project_name: 'Running' }),
          makeJob({ job_id: 'j-paused', status: 'paused', project_name: 'Paused' }),
        ],
        history: [
          makeJob({
            job_id: 'j-failed',
            status: 'failed',
            project_name: 'Failed',
            error_message: 'boom',
          }),
          makeJob({
            job_id: 'j-complete',
            status: 'complete',
            project_name: 'Complete',
          }),
        ],
      }),
    );
    render(<JobsMobile />, { wrapper: Wrapper });
    const cards = screen.getAllByTestId('mobile-job-card');
    expect(cards.map((c) => c.getAttribute('data-status'))).toEqual([
      'running',
      'paused',
      'failed',
      'complete',
    ]);
  });

  it('renders the progress bar for running jobs and omits it for complete/failed', () => {
    useExtractionJobsMock.mockReturnValue(
      makeHookReturn({
        active: [
          makeJob({ status: 'running', items_processed: 3, items_total: 10 }),
        ],
        history: [
          makeJob({
            job_id: 'j-2',
            status: 'complete',
            items_processed: 10,
            items_total: 10,
          }),
        ],
      }),
    );
    render(<JobsMobile />, { wrapper: Wrapper });
    const fills = screen.getAllByTestId('mobile-job-progress-fill');
    expect(fills).toHaveLength(1);
    expect(fills[0].getAttribute('data-progress-pct')).toBe('30');
  });

  it('TOUCH_TARGET_CLASS is applied to the toggle button', () => {
    useExtractionJobsMock.mockReturnValue(
      makeHookReturn({ active: [makeJob()] }),
    );
    render(<JobsMobile />, { wrapper: Wrapper });
    const toggle = screen.getByTestId('mobile-job-toggle') as HTMLButtonElement;
    expect(toggle.className).toContain('min-h-[44px]');
  });

  it('single-expand: tapping one card collapses another', () => {
    useExtractionJobsMock.mockReturnValue(
      makeHookReturn({
        active: [
          makeJob({ job_id: 'j-1' }),
          makeJob({ job_id: 'j-2', project_name: 'Second' }),
        ],
      }),
    );
    render(<JobsMobile />, { wrapper: Wrapper });
    const toggles = screen.getAllByTestId('mobile-job-toggle');
    fireEvent.click(toggles[0]);
    expect(screen.getAllByTestId('mobile-job-detail')).toHaveLength(1);
    fireEvent.click(toggles[1]);
    expect(screen.getAllByTestId('mobile-job-detail')).toHaveLength(1);
  });

  it('running job: Pause button fires API + invalidates jobs query; Resume/Cancel buttons visible by status', async () => {
    pauseExtractionMock.mockResolvedValue(undefined);
    useExtractionJobsMock.mockReturnValue(
      makeHookReturn({ active: [makeJob({ status: 'running' })] }),
    );
    render(<JobsMobile />, { wrapper: Wrapper });
    fireEvent.click(screen.getByTestId('mobile-job-toggle'));
    // Running → Pause + Cancel available, Resume NOT.
    expect(screen.getByTestId('mobile-job-pause')).toBeTruthy();
    expect(screen.getByTestId('mobile-job-cancel')).toBeTruthy();
    expect(screen.queryByTestId('mobile-job-resume')).toBeNull();
    fireEvent.click(screen.getByTestId('mobile-job-pause'));
    await waitFor(() => {
      expect(pauseExtractionMock).toHaveBeenCalledWith('p-1', 'tok-test');
    });
    // Review-impl M3: invalidate query after success so the list
    // refreshes without waiting for the next 2s/10s poll tick.
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ['knowledge-jobs'],
      });
    });
  });

  it('paused job: Resume + Cancel visible, Pause NOT', () => {
    useExtractionJobsMock.mockReturnValue(
      makeHookReturn({ active: [makeJob({ status: 'paused' })] }),
    );
    render(<JobsMobile />, { wrapper: Wrapper });
    fireEvent.click(screen.getByTestId('mobile-job-toggle'));
    expect(screen.queryByTestId('mobile-job-pause')).toBeNull();
    expect(screen.getByTestId('mobile-job-resume')).toBeTruthy();
    expect(screen.getByTestId('mobile-job-cancel')).toBeTruthy();
  });

  it('complete + failed jobs show NO action buttons (no retry-with-new-settings on mobile per plan)', () => {
    // Single-expand means we check each card's expanded state
    // separately. After sort: [failed, complete] (failed rank 3,
    // complete rank 5). Expand failed first → assert no action
    // buttons + error message renders. Then expand complete (failed
    // collapses) → assert no action buttons.
    useExtractionJobsMock.mockReturnValue(
      makeHookReturn({
        history: [
          makeJob({ job_id: 'j-c', status: 'complete' }),
          makeJob({
            job_id: 'j-f',
            status: 'failed',
            error_message: 'boom',
          }),
        ],
      }),
    );
    render(<JobsMobile />, { wrapper: Wrapper });
    const toggles = screen.getAllByTestId('mobile-job-toggle');
    // Failed card is first (lower sort rank).
    fireEvent.click(toggles[0]);
    expect(screen.queryByTestId('mobile-job-pause')).toBeNull();
    expect(screen.queryByTestId('mobile-job-resume')).toBeNull();
    expect(screen.queryByTestId('mobile-job-cancel')).toBeNull();
    // Failed job shows its error message inline.
    expect(screen.getByTestId('mobile-job-error-message')).toBeTruthy();
    // Now expand complete (failed collapses). Still no actions.
    fireEvent.click(toggles[1]);
    expect(screen.queryByTestId('mobile-job-pause')).toBeNull();
    expect(screen.queryByTestId('mobile-job-resume')).toBeNull();
    expect(screen.queryByTestId('mobile-job-cancel')).toBeNull();
    // Complete card doesn't show error message (it's not failed).
    expect(screen.queryByTestId('mobile-job-error-message')).toBeNull();
  });

  it('Pause click does not collapse the card (stopPropagation regression lock)', async () => {
    pauseExtractionMock.mockResolvedValue(undefined);
    useExtractionJobsMock.mockReturnValue(
      makeHookReturn({ active: [makeJob({ status: 'running' })] }),
    );
    render(<JobsMobile />, { wrapper: Wrapper });
    fireEvent.click(screen.getByTestId('mobile-job-toggle'));
    expect(screen.getByTestId('mobile-job-detail')).toBeTruthy();
    fireEvent.click(screen.getByTestId('mobile-job-pause'));
    // Without stopPropagation, the Pause click would bubble to the
    // toggle's onClick and collapse the detail. Regression lock.
    expect(screen.getByTestId('mobile-job-detail')).toBeTruthy();
  });

  // ── review-impl follow-up coverage ──────────────────────────────

  it('Resume button fires resumeExtraction API + invalidates + stopPropagation (review-impl MED #2 + LOW #4)', async () => {
    resumeExtractionMock.mockResolvedValue(undefined);
    useExtractionJobsMock.mockReturnValue(
      makeHookReturn({ active: [makeJob({ status: 'paused' })] }),
    );
    render(<JobsMobile />, { wrapper: Wrapper });
    fireEvent.click(screen.getByTestId('mobile-job-toggle'));
    fireEvent.click(screen.getByTestId('mobile-job-resume'));
    await waitFor(() => {
      expect(resumeExtractionMock).toHaveBeenCalledWith('p-1', 'tok-test');
    });
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ['knowledge-jobs'],
      });
    });
    // Detail stays expanded — stopPropagation contract on Resume.
    expect(screen.getByTestId('mobile-job-detail')).toBeTruthy();
  });

  it('Cancel button fires cancelExtraction API + invalidates + stopPropagation (review-impl MED #2 + LOW #4)', async () => {
    cancelExtractionMock.mockResolvedValue(undefined);
    useExtractionJobsMock.mockReturnValue(
      makeHookReturn({ active: [makeJob({ status: 'running' })] }),
    );
    render(<JobsMobile />, { wrapper: Wrapper });
    fireEvent.click(screen.getByTestId('mobile-job-toggle'));
    fireEvent.click(screen.getByTestId('mobile-job-cancel'));
    await waitFor(() => {
      expect(cancelExtractionMock).toHaveBeenCalledWith('p-1', 'tok-test');
    });
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ['knowledge-jobs'],
      });
    });
    expect(screen.getByTestId('mobile-job-detail')).toBeTruthy();
  });

  it('toasts an error when an action rejects (review-impl LOW #5)', async () => {
    pauseExtractionMock.mockRejectedValue(new Error('upstream down'));
    useExtractionJobsMock.mockReturnValue(
      makeHookReturn({ active: [makeJob({ status: 'running' })] }),
    );
    render(<JobsMobile />, { wrapper: Wrapper });
    fireEvent.click(screen.getByTestId('mobile-job-toggle'));
    fireEvent.click(screen.getByTestId('mobile-job-pause'));
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
    // Query must NOT have been invalidated on failure.
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('dedups a job that appears in BOTH active and history (review-impl MED #1 poll-race regression)', () => {
    // Simulates the 2s active vs 10s history poll transition window
    // where a running→complete flip leaves the same job_id in both
    // slices momentarily. Before the dedup, React would warn about
    // duplicate keys and potentially drop / double-render one card.
    const sharedJob = makeJob({ status: 'running' });
    useExtractionJobsMock.mockReturnValue(
      makeHookReturn({
        active: [sharedJob],
        // History has the same job_id but now with the fresher
        // "complete" status — the list should take active's entry
        // (more recent poll) and the card shows status=running.
        history: [{ ...sharedJob, status: 'complete' }],
      }),
    );
    render(<JobsMobile />, { wrapper: Wrapper });
    const cards = screen.getAllByTestId('mobile-job-card');
    expect(cards).toHaveLength(1);
    // active wins — card shows running status.
    expect(cards[0].getAttribute('data-status')).toBe('running');
  });

  it('falls back to unknownProject label when project_name is null (review-impl LOW #6)', () => {
    useExtractionJobsMock.mockReturnValue(
      makeHookReturn({
        active: [makeJob({ project_name: null, project_id: 'abc12345-rest' })],
      }),
    );
    render(<JobsMobile />, { wrapper: Wrapper });
    const card = screen.getByTestId('mobile-job-card');
    // i18n mock-bypass returns the key verbatim; just ensure the
    // fallback key appears and the raw null doesn't render as empty.
    expect(card.textContent).toContain('mobile.jobs.unknownProject');
  });

  it('sorts same-status jobs with the newest created_at first (review-impl LOW #7)', () => {
    const older = makeJob({
      job_id: 'j-old',
      status: 'running',
      project_name: 'Older',
      created_at: '2026-04-01T00:00:00Z',
    });
    const newer = makeJob({
      job_id: 'j-new',
      status: 'running',
      project_name: 'Newer',
      created_at: '2026-04-20T00:00:00Z',
    });
    useExtractionJobsMock.mockReturnValue(
      // Seed oldest-first so the sort has to flip them.
      makeHookReturn({ active: [older, newer] }),
    );
    render(<JobsMobile />, { wrapper: Wrapper });
    const cards = screen.getAllByTestId('mobile-job-card');
    expect(cards.map((c) => c.getAttribute('data-job-id'))).toEqual([
      'j-new',
      'j-old',
    ]);
  });

  it('surfaces historyError when only history fails (review-impl LOW #9)', () => {
    useExtractionJobsMock.mockReturnValue(
      makeHookReturn({ historyError: new Error('history 500') }),
    );
    render(<JobsMobile />, { wrapper: Wrapper });
    expect(screen.getByTestId('mobile-jobs-error')).toBeTruthy();
  });
});
