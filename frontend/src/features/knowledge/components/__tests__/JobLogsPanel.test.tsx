import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { JobLog } from '../../api';

const useJobLogsMock = vi.fn();
vi.mock('../../hooks/useJobLogs', () => ({
  useJobLogs: (jobId: string | null, options?: { jobStatus?: string | null }) =>
    useJobLogsMock(jobId, options),
}));

import { JobLogsPanel } from '../JobLogsPanel';

// jsdom doesn't implement scrollTo on elements or populate
// scrollHeight/clientHeight. Stub both on HTMLElement.prototype so
// the auto-scroll effect in JobLogsPanel runs without TypeError.
// Default dimensions: scrollHeight=500, clientHeight=300, scrollTop=0
// → distance from bottom = 500 - 0 - 300 = 200 > 100 → NOT near-bottom
// for scroll-event-driven updates, but default nearBottomRef=true
// overrides on initial mount (by design: show latest on open).
const defaultScrollTo = vi.fn();
Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
  configurable: true,
  writable: true,
  value: defaultScrollTo,
});
Object.defineProperty(HTMLElement.prototype, 'scrollHeight', {
  configurable: true,
  get() { return 500; },
});
Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
  configurable: true,
  get() { return 300; },
});

interface HookState {
  logs?: JobLog[];
  hasNextPage?: boolean;
  fetchNextPage?: () => void;
  isLoading?: boolean;
  isFetchingNextPage?: boolean;
  error?: Error | null;
}

function setHookState(overrides: HookState) {
  useJobLogsMock.mockReturnValue({
    logs: overrides.logs ?? [],
    hasNextPage: overrides.hasNextPage ?? false,
    fetchNextPage: overrides.fetchNextPage ?? vi.fn(),
    isLoading: overrides.isLoading ?? false,
    isFetchingNextPage: overrides.isFetchingNextPage ?? false,
    error: overrides.error ?? null,
  });
}

function log(overrides: Partial<JobLog> & { log_id: number; level: JobLog['level'] }): JobLog {
  return {
    job_id: 'j1',
    user_id: 'u1',
    message: 'a message',
    context: {},
    created_at: '2026-04-22T12:00:00Z',
    ...overrides,
  } as JobLog;
}

describe('JobLogsPanel', () => {
  beforeEach(() => {
    useJobLogsMock.mockReset();
    defaultScrollTo.mockReset();
  });

  it('renders loading indicator when fetching', () => {
    setHookState({ isLoading: true });
    render(<JobLogsPanel jobId="j1" />);
    expect(screen.getByTestId('job-logs-loading')).toBeInTheDocument();
  });

  it('renders error message when the hook errors', () => {
    setHookState({ error: new Error('boom') });
    render(<JobLogsPanel jobId="j1" />);
    expect(screen.getByTestId('job-logs-error')).toHaveTextContent('boom');
  });

  it('renders empty state when logs array is empty', () => {
    setHookState({ logs: [] });
    render(<JobLogsPanel jobId="j1" />);
    expect(screen.getByTestId('job-logs-empty')).toBeInTheDocument();
  });

  it('renders each log with level + message', () => {
    setHookState({
      logs: [
        log({ log_id: 1, level: 'info', message: 'chapter 1 processed' }),
        log({ log_id: 2, level: 'warning', message: 'retry attempt 2' }),
        log({ log_id: 3, level: 'error', message: 'job failed' }),
      ],
    });
    render(<JobLogsPanel jobId="j1" />);
    const rows = screen.getAllByTestId('job-log-row');
    expect(rows).toHaveLength(3);
    expect(rows[0].getAttribute('data-level')).toBe('info');
    expect(rows[1].getAttribute('data-level')).toBe('warning');
    expect(rows[2].getAttribute('data-level')).toBe('error');
    expect(screen.getByText('chapter 1 processed')).toBeInTheDocument();
    expect(screen.getByText('job failed')).toBeInTheDocument();
  });

  it('shows a "+" count suffix when hasNextPage is true (more logs exist)', () => {
    setHookState({
      logs: [
        log({ log_id: 1, level: 'info' }),
        log({ log_id: 2, level: 'info' }),
      ],
      hasNextPage: true,
    });
    render(<JobLogsPanel jobId="j1" />);
    const summary = screen.getByTestId('job-logs-panel').querySelector('summary');
    expect(summary?.textContent).toContain('2+');
  });

  it('omits the "+" suffix when hasNextPage is false (end of stream)', () => {
    setHookState({
      logs: [log({ log_id: 1, level: 'info' })],
      hasNextPage: false,
    });
    render(<JobLogsPanel jobId="j1" />);
    const summary = screen.getByTestId('job-logs-panel').querySelector('summary');
    expect(summary?.textContent).toContain('(1)');
    expect(summary?.textContent).not.toContain('1+');
  });

  // ── C3 (D-K19b.8-03) — Load-more + auto-scroll ─────────────────

  it('forwards jobStatus to the hook so polling can gate on it', () => {
    setHookState({ logs: [log({ log_id: 1, level: 'info' })] });
    render(<JobLogsPanel jobId="j1" jobStatus="running" />);
    expect(useJobLogsMock).toHaveBeenCalledWith('j1', { jobStatus: 'running' });
  });

  it('renders Load-more button when hasNextPage is true', () => {
    setHookState({
      logs: [log({ log_id: 1, level: 'info' })],
      hasNextPage: true,
    });
    render(<JobLogsPanel jobId="j1" />);
    expect(screen.getByTestId('job-logs-load-more')).toBeInTheDocument();
  });

  it('does NOT render Load-more when hasNextPage is false', () => {
    setHookState({
      logs: [log({ log_id: 1, level: 'info' })],
      hasNextPage: false,
    });
    render(<JobLogsPanel jobId="j1" />);
    expect(screen.queryByTestId('job-logs-load-more')).toBeNull();
  });

  it('Load-more click invokes fetchNextPage', () => {
    const fetchNext = vi.fn();
    setHookState({
      logs: [log({ log_id: 1, level: 'info' })],
      hasNextPage: true,
      fetchNextPage: fetchNext,
    });
    render(<JobLogsPanel jobId="j1" />);
    fireEvent.click(screen.getByTestId('job-logs-load-more'));
    expect(fetchNext).toHaveBeenCalledTimes(1);
  });

  it('Load-more button is disabled while isFetchingNextPage', () => {
    setHookState({
      logs: [log({ log_id: 1, level: 'info' })],
      hasNextPage: true,
      isFetchingNextPage: true,
    });
    render(<JobLogsPanel jobId="j1" />);
    const btn = screen.getByTestId('job-logs-load-more');
    expect(btn).toBeDisabled();
    // /review-impl C9: button copy now reads "load newer" /
    // "loading newer" — disambiguates from news-feed UX where
    // "Load more" means older. Our cursor is ASC so it's newer.
    expect(btn.textContent?.toLowerCase()).toMatch(/newer|load/);
  });

  it('auto-scrolls to bottom when user is near-bottom and new logs arrive', () => {
    // Default nearBottomRef=true. Initial render scrolls; subsequent
    // renders with more logs also scroll as long as nothing has
    // pushed the ref false.
    setHookState({
      logs: [log({ log_id: 1, level: 'info' })],
    });
    const { rerender } = render(<JobLogsPanel jobId="j1" />);
    expect(defaultScrollTo).toHaveBeenCalled();

    defaultScrollTo.mockClear();
    setHookState({
      logs: [
        log({ log_id: 1, level: 'info' }),
        log({ log_id: 2, level: 'info', message: 'new' }),
      ],
    });
    rerender(<JobLogsPanel jobId="j1" />);
    expect(defaultScrollTo).toHaveBeenCalled();
  });

  it('/review-impl M1: toggle-open scrolls to bottom via rAF', async () => {
    // Stub requestAnimationFrame to fire synchronously so we can
    // assert without timing flakes.
    const rafSpy = vi
      .spyOn(window, 'requestAnimationFrame')
      .mockImplementation((cb) => {
        cb(0);
        return 0;
      });
    try {
      setHookState({
        logs: [
          log({ log_id: 1, level: 'info' }),
          log({ log_id: 2, level: 'info' }),
        ],
      });
      const { container } = render(<JobLogsPanel jobId="j1" />);
      defaultScrollTo.mockClear();

      // Fire the toggle event. React's SyntheticEvent maps `open`
      // from the target's `.open` attribute, so we force the attr
      // before dispatching.
      const details = container.querySelector(
        '[data-testid="job-logs-panel"]',
      ) as HTMLDetailsElement;
      details.open = true;
      fireEvent(details, new Event('toggle', { bubbles: false }));

      expect(rafSpy).toHaveBeenCalled();
      expect(defaultScrollTo).toHaveBeenCalled();
    } finally {
      rafSpy.mockRestore();
    }
  });

  it('/review-impl M1: toggle-closed does NOT fire scroll', () => {
    const rafSpy = vi
      .spyOn(window, 'requestAnimationFrame')
      .mockImplementation((cb) => {
        cb(0);
        return 0;
      });
    try {
      setHookState({
        logs: [log({ log_id: 1, level: 'info' })],
      });
      const { container } = render(<JobLogsPanel jobId="j1" />);
      defaultScrollTo.mockClear();

      const details = container.querySelector(
        '[data-testid="job-logs-panel"]',
      ) as HTMLDetailsElement;
      // Details stays closed — no scroll on close-toggle.
      details.open = false;
      fireEvent(details, new Event('toggle', { bubbles: false }));

      expect(defaultScrollTo).not.toHaveBeenCalled();
    } finally {
      rafSpy.mockRestore();
    }
  });

  it('does NOT auto-scroll when user has scrolled away from bottom', () => {
    // Start with 1 log. Initial render auto-scrolls (ref defaults to true).
    setHookState({ logs: [log({ log_id: 1, level: 'info' })] });
    const { rerender, container } = render(<JobLogsPanel jobId="j1" />);
    defaultScrollTo.mockClear();

    // Find the scroll container and set its scrollTop to 0 — with
    // scrollHeight=500 and clientHeight=300, distance from bottom = 200
    // which is > 100 threshold → onScroll flips nearBottomRef false.
    const list = container.querySelector('[data-testid="job-logs-list"]') as HTMLElement;
    Object.defineProperty(list, 'scrollTop', {
      configurable: true,
      get() { return 0; },
    });
    fireEvent.scroll(list);

    // New log arrives.
    setHookState({
      logs: [
        log({ log_id: 1, level: 'info' }),
        log({ log_id: 2, level: 'info', message: 'new' }),
      ],
    });
    rerender(<JobLogsPanel jobId="j1" />);
    expect(defaultScrollTo).not.toHaveBeenCalled();
  });
});
