import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({
    accessToken: 'tok-test',
    user: { user_id: 'user-42', email: 'a@b', display_name: null, avatar_url: null },
  }),
}));

const listAllJobsMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      listAllJobs: (...args: unknown[]) => listAllJobsMock(...args),
    },
  };
});

import { useExtractionJobs } from '../useExtractionJobs';
import type { ExtractionJobWire } from '../../api';

function wrapper(client?: QueryClient) {
  const qc =
    client ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

function makeJob(overrides: Partial<ExtractionJobWire> = {}): ExtractionJobWire {
  return {
    job_id: 'j1',
    user_id: 'u1',
    project_id: 'p1',
    scope: 'all',
    scope_range: null,
    status: 'running',
    llm_model: 'claude-sonnet-4-6',
    embedding_model: 'bge-m3',
    max_spend_usd: '5.00',
    items_processed: 3,
    items_total: 10,
    cost_spent_usd: '0.50',
    current_cursor: null,
    started_at: '2026-04-19T12:00:00Z',
    paused_at: null,
    completed_at: null,
    created_at: '2026-04-19T12:00:00Z',
    updated_at: '2026-04-19T12:00:00Z',
    error_message: null,
    project_name: null,
    ...overrides,
  };
}

describe('useExtractionJobs', () => {
  beforeEach(() => {
    listAllJobsMock.mockReset();
  });

  it('returns active + history groups from separate API calls', async () => {
    const active = [makeJob({ job_id: 'a1', status: 'running' })];
    const history = [makeJob({ job_id: 'h1', status: 'complete' })];
    listAllJobsMock.mockImplementation(
      async (params: { statusGroup: 'active' | 'history' }) =>
        params.statusGroup === 'active' ? active : history,
    );

    const { result } = renderHook(() => useExtractionJobs(), {
      wrapper: wrapper(),
    });

    await waitFor(() => {
      expect(result.current.active).toHaveLength(1);
      expect(result.current.history).toHaveLength(1);
    });
    expect(result.current.active[0].job_id).toBe('a1');
    expect(result.current.history[0].job_id).toBe('h1');
  });

  it('passes limit=50 to history, no limit to active (BE default 50)', async () => {
    listAllJobsMock.mockResolvedValue([]);
    renderHook(() => useExtractionJobs(), { wrapper: wrapper() });

    await waitFor(() => {
      expect(listAllJobsMock).toHaveBeenCalledWith(
        { statusGroup: 'active' },
        'tok-test',
      );
      expect(listAllJobsMock).toHaveBeenCalledWith(
        { statusGroup: 'history', limit: 50 },
        'tok-test',
      );
    });
  });

  it('surfaces errors from either query via the error field', async () => {
    const boom = new Error('network down');
    listAllJobsMock.mockImplementation(
      async (params: { statusGroup: 'active' | 'history' }) => {
        if (params.statusGroup === 'active') throw boom;
        return [];
      },
    );

    const { result } = renderHook(() => useExtractionJobs(), {
      wrapper: wrapper(),
    });

    await waitFor(() => {
      expect(result.current.error).toBe(boom);
    });
    // review-impl L2: group-specific error is exposed so callers can
    // target the failure without treating both sections as broken.
    expect(result.current.activeError).toBe(boom);
    expect(result.current.historyError).toBeNull();
  });

  it('distinguishes history-only errors from active-only errors', async () => {
    const historyBoom = new Error('history fetch failed');
    listAllJobsMock.mockImplementation(
      async (params: { statusGroup: 'active' | 'history' }) => {
        if (params.statusGroup === 'history') throw historyBoom;
        return [];
      },
    );

    const { result } = renderHook(() => useExtractionJobs(), {
      wrapper: wrapper(),
    });

    await waitFor(() => {
      expect(result.current.historyError).toBe(historyBoom);
    });
    expect(result.current.activeError).toBeNull();
    expect(result.current.error).toBe(historyBoom);
  });
});
