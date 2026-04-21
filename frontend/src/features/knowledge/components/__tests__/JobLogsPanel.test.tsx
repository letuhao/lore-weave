import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { JobLog } from '../../api';

const useJobLogsMock = vi.fn();
vi.mock('../../hooks/useJobLogs', () => ({
  useJobLogs: (jobId: string | null) => useJobLogsMock(jobId),
}));

import { JobLogsPanel } from '../JobLogsPanel';

function setHookState(overrides: {
  logs?: JobLog[];
  nextCursor?: number | null;
  isLoading?: boolean;
  error?: Error | null;
}) {
  useJobLogsMock.mockReturnValue({
    logs: overrides.logs ?? [],
    nextCursor: overrides.nextCursor ?? null,
    isLoading: overrides.isLoading ?? false,
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
  beforeEach(() => useJobLogsMock.mockReset());

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

  it('shows a "+" count suffix when nextCursor is non-null (more logs exist)', () => {
    // BE's nextCursor signals "more rows available"; independent of
    // whether the page happens to be exactly DEFAULT_LIMIT long
    // (review-code L6 — no magic-number coupling).
    setHookState({
      logs: [
        log({ log_id: 1, level: 'info' }),
        log({ log_id: 2, level: 'info' }),
      ],
      nextCursor: 2,
    });
    render(<JobLogsPanel jobId="j1" />);
    const summary = screen.getByTestId('job-logs-panel').querySelector('summary');
    expect(summary?.textContent).toContain('2+');
  });

  it('omits the "+" suffix when nextCursor is null (end of stream)', () => {
    setHookState({
      logs: [log({ log_id: 1, level: 'info' })],
      nextCursor: null,
    });
    render(<JobLogsPanel jobId="j1" />);
    const summary = screen.getByTestId('job-logs-panel').querySelector('summary');
    expect(summary?.textContent).toContain('(1)');
    expect(summary?.textContent).not.toContain('1+');
  });
});
