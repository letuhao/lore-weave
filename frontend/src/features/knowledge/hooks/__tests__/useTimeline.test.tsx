import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const useAuthMock = vi.fn();
vi.mock('@/auth', () => ({
  useAuth: () => useAuthMock(),
}));

const listTimelineMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      listTimeline: (...args: unknown[]) => listTimelineMock(...args),
    },
  };
});

import { useTimeline } from '../useTimeline';

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

const EVENT_STUB = {
  id: 'ev-1',
  user_id: 'u1',
  project_id: 'p-1',
  title: 'Kai duels Zhao',
  canonical_title: 'kai duels zhao',
  summary: null,
  chapter_id: 'ch-12',
  event_order: 10,
  chronological_order: null,
  participants: ['Kai', 'Zhao'],
  confidence: 0.9,
  source_types: ['book_content'],
  evidence_count: 3,
  mention_count: 5,
  archived_at: null,
  created_at: null,
  updated_at: null,
};

describe('useTimeline', () => {
  beforeEach(() => {
    listTimelineMock.mockReset();
    useAuthMock.mockReset();
    useAuthMock.mockReturnValue({
      accessToken: 'tok-test',
      user: {
        user_id: 'u1',
        email: 'a@b',
        display_name: null,
        avatar_url: null,
      },
    });
  });

  it('passes params through to the API and surfaces events + total', async () => {
    listTimelineMock.mockResolvedValue({
      events: [EVENT_STUB],
      total: 42,
    });
    const params = {
      project_id: 'p-1',
      after_order: 5,
      before_order: 100,
      limit: 25,
      offset: 50,
    };
    const { result } = renderHook(() => useTimeline(params), {
      wrapper: wrapper(),
    });
    await waitFor(() => {
      expect(result.current.events).toHaveLength(1);
    });
    expect(result.current.total).toBe(42);
    expect(listTimelineMock).toHaveBeenCalledWith(params, 'tok-test');
  });

  it('surfaces API errors via the error field', async () => {
    const boom = new Error('timeline load failed');
    listTimelineMock.mockRejectedValue(boom);
    const { result } = renderHook(() => useTimeline({}), {
      wrapper: wrapper(),
    });
    await waitFor(() => {
      expect(result.current.error).toBe(boom);
    });
  });

  it('does not fire when accessToken is null (enabled gate)', async () => {
    // Regression lock against a future refactor that drops
    // `enabled: !!accessToken`. Without the gate, a logged-out render
    // would call `knowledgeApi.listTimeline(params, null!)` and fire a
    // 401 storm.
    useAuthMock.mockReturnValue({
      accessToken: null,
      user: null,
    });
    const { result } = renderHook(() => useTimeline({}), {
      wrapper: wrapper(),
    });
    // Give react-query a tick to surface any (unexpected) in-flight query.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(listTimelineMock).not.toHaveBeenCalled();
    // Hook still returns the empty shape — downstream components rely
    // on this rather than a loading spinner lingering forever.
    expect(result.current.events).toEqual([]);
    expect(result.current.total).toBe(0);
  });

  it('scopes queryKey by userId so logout→login cannot leak cache (K19d β M1 pattern)', async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrap = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    listTimelineMock.mockResolvedValue({ events: [], total: 0 });

    useAuthMock.mockReturnValue({
      accessToken: 'tok-a',
      user: {
        user_id: 'user-A',
        email: 'a@b',
        display_name: null,
        avatar_url: null,
      },
    });
    const { result: r1, unmount } = renderHook(() => useTimeline({}), {
      wrapper: wrap,
    });
    await waitFor(() => {
      expect(r1.current.isLoading).toBe(false);
    });
    unmount();

    useAuthMock.mockReturnValue({
      accessToken: 'tok-b',
      user: {
        user_id: 'user-B',
        email: 'c@d',
        display_name: null,
        avatar_url: null,
      },
    });
    const { result: r2 } = renderHook(() => useTimeline({}), {
      wrapper: wrap,
    });
    await waitFor(() => {
      expect(r2.current.isLoading).toBe(false);
    });

    // Distinct userIds → distinct cache keys → two BE calls.
    expect(listTimelineMock).toHaveBeenCalledTimes(2);
  });

  // C7 (D-K19e-β-02) — stale-offset self-heal. When BE returns 0 events
  // for a non-zero offset but total > 0 (another client's delete shrank
  // the dataset past our page), fire the optional onStaleOffset callback
  // so the parent can reset offset to 0 without manual button click.
  it('fires onStaleOffset when server returns empty for non-zero offset but total > 0', async () => {
    listTimelineMock.mockResolvedValue({ events: [], total: 42 });
    const onStaleOffset = vi.fn();
    renderHook(() => useTimeline({ offset: 100 }, { onStaleOffset }), {
      wrapper: wrapper(),
    });
    await waitFor(() => {
      expect(onStaleOffset).toHaveBeenCalledTimes(1);
    });
  });

  it('does NOT fire onStaleOffset while isLoading is true (first fetch)', async () => {
    // Never resolve — isLoading stays true.
    listTimelineMock.mockReturnValue(new Promise(() => {}));
    const onStaleOffset = vi.fn();
    renderHook(() => useTimeline({ offset: 100 }, { onStaleOffset }), {
      wrapper: wrapper(),
    });
    // Give react-query a tick.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(onStaleOffset).not.toHaveBeenCalled();
  });

  it('does NOT fire onStaleOffset when offset is already 0 (empty dataset, not stale page)', async () => {
    listTimelineMock.mockResolvedValue({ events: [], total: 0 });
    const onStaleOffset = vi.fn();
    const { result } = renderHook(
      () => useTimeline({ offset: 0 }, { onStaleOffset }),
      { wrapper: wrapper() },
    );
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(onStaleOffset).not.toHaveBeenCalled();
  });

  it('does NOT fire onStaleOffset when error is present', async () => {
    listTimelineMock.mockRejectedValue(new Error('boom'));
    const onStaleOffset = vi.fn();
    const { result } = renderHook(
      () => useTimeline({ offset: 100 }, { onStaleOffset }),
      { wrapper: wrapper() },
    );
    await waitFor(() => {
      expect(result.current.error).toBeTruthy();
    });
    expect(onStaleOffset).not.toHaveBeenCalled();
  });

  it('does not crash when options arg is omitted under stale-offset conditions (backward-compat)', async () => {
    // C7 /review-impl [L5]: single-arg call site must survive the
    // guard `if (onStaleOffset && ...)`. Before this test, no lock on
    // the options-omitted happy path — a future refactor that removed
    // the `onStaleOffset &&` check would throw undefined().
    listTimelineMock.mockResolvedValue({ events: [], total: 42 });
    const { result } = renderHook(() => useTimeline({ offset: 100 }), {
      wrapper: wrapper(),
    });
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.total).toBe(42);
    expect(result.current.events).toEqual([]);
  });
});
