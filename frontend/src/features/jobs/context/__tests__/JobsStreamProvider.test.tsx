import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { JobsStreamProvider, useJobLive } from '../JobsStreamProvider';
import type { JobSseEvent } from '../../types';

// Capture the onEvent the provider hands to the stream so the test can feed frames.
let captured: ((e: JobSseEvent) => void) | null = null;
vi.mock('../../hooks/useJobsStream', () => ({
  useJobsStream: (_t: unknown, onEvent: (e: JobSseEvent) => void) => {
    captured = onEvent;
    return 'open';
  },
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const ev = (over: Partial<JobSseEvent>): JobSseEvent => ({
  service: 'knowledge', job_id: 'j1', owner_user_id: 'u', kind: 'extraction',
  status: 'running', parent_job_id: null, detail_status: null, progress: null,
  control_caps: [], title: null, error: null, updated_at: '2026-06-16T00:00:00+00:00',
  ...over,
});

function Probe({ k }: { k: string }) {
  const live = useJobLive(k);
  return <div data-testid="s">{live?.status ?? 'none'}</div>;
}

function setup(qc = new QueryClient()) {
  return render(
    <QueryClientProvider client={qc}>
      <JobsStreamProvider>
        <Probe k="knowledge:j1" />
      </JobsStreamProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => { captured = null; });

describe('JobsStreamProvider live overlay', () => {
  it('propagates a live event to useJobLive for that key', () => {
    setup();
    expect(screen.getByTestId('s').textContent).toBe('none');
    act(() => captured!(ev({ status: 'paused' })));
    expect(screen.getByTestId('s').textContent).toBe('paused');
  });

  it('does NOT update a probe subscribed to a different key', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <JobsStreamProvider>
          <Probe k="knowledge:other" />
        </JobsStreamProvider>
      </QueryClientProvider>,
    );
    act(() => captured!(ev({ status: 'paused' }))); // key knowledge:j1
    expect(screen.getByTestId('s').textContent).toBe('none');
  });

  it('evicts a terminal job from the overlay after the refetch window (D-JOBS-P4-OVERLAY-EVICT)', () => {
    vi.useFakeTimers();
    try {
      setup();
      act(() => captured!(ev({ status: 'completed' })));
      // terminal state shows immediately…
      expect(screen.getByTestId('s').textContent).toBe('completed');
      // …then the entry is dropped once the refetch window passes (2× throttle here),
      // so the row falls back to the query (probe → 'none' with no overlay entry).
      act(() => vi.advanceTimersByTime(3000));
      expect(screen.getByTestId('s').textContent).toBe('none');
    } finally {
      vi.useRealTimers();
    }
  });

  it('does NOT evict a non-terminal job (it stays resident for live updates)', () => {
    vi.useFakeTimers();
    try {
      setup();
      act(() => captured!(ev({ status: 'running' })));
      act(() => vi.advanceTimersByTime(5000));
      expect(screen.getByTestId('s').textContent).toBe('running'); // still resident
    } finally {
      vi.useRealTimers();
    }
  });

  it('throttles list invalidation (coalesces a burst into one flush)', () => {
    vi.useFakeTimers();
    try {
      const qc = new QueryClient();
      const spy = vi.spyOn(qc, 'invalidateQueries');
      setup(qc);
      act(() => {
        captured!(ev({ status: 'running' }));
        captured!(ev({ status: 'paused' }));
        captured!(ev({ status: 'cancelling' }));
      });
      expect(spy).not.toHaveBeenCalled(); // trailing throttle — not yet
      act(() => vi.advanceTimersByTime(1500));
      expect(spy).toHaveBeenCalledTimes(1);
      expect(spy).toHaveBeenCalledWith({ queryKey: ['jobs'] });
    } finally {
      vi.useRealTimers();
    }
  });
});
