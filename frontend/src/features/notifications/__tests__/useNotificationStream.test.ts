/**
 * Phase 2f — useNotificationStream hook tests.
 *
 * EventSource is mocked with a class that records each constructed
 * instance; tests poke .onopen / .onmessage / .onerror manually to
 * exercise lifecycle states.
 */
import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { useNotificationStream } from '../hooks/useNotificationStream';

type MockESInstance = {
  url: string;
  closed: boolean;
  close: () => void;
  onopen: ((ev: Event) => void) | null;
  onmessage: ((ev: MessageEvent) => void) | null;
  onerror: ((ev: Event) => void) | null;
};

const created: MockESInstance[] = [];

class MockEventSource implements MockESInstance {
  closed = false;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  constructor(public url: string) {
    created.push(this);
  }
  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  created.length = 0;
  vi.stubGlobal('EventSource', MockEventSource);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('useNotificationStream', () => {
  it('does nothing when accessToken is null', () => {
    const { result } = renderHook(() =>
      useNotificationStream(null, () => {}),
    );
    expect(result.current).toBe('idle');
    expect(created).toHaveLength(0);
  });

  it('opens an EventSource and reaches "open" state on connect', async () => {
    const { result } = renderHook(() =>
      useNotificationStream('jwt-token', () => {}),
    );
    expect(created).toHaveLength(1);
    expect(result.current).toBe('connecting');
    expect(created[0].url).toContain('/v1/notifications/stream?token=jwt-token');

    act(() => {
      created[0].onopen?.(new Event('open'));
    });
    expect(result.current).toBe('open');
  });

  it('forwards parsed events to onEvent callback', () => {
    const onEvent = vi.fn();
    renderHook(() => useNotificationStream('t', onEvent));
    act(() => {
      created[0].onopen?.(new Event('open'));
      created[0].onmessage?.({
        data: JSON.stringify({
          job_id: 'j-1',
          owner_user_id: 'u-1',
          operation: 'chat',
          status: 'completed',
        }),
      } as MessageEvent);
    });
    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        job_id: 'j-1',
        operation: 'chat',
        status: 'completed',
      }),
    );
  });

  it('drops malformed JSON without crashing', () => {
    const onEvent = vi.fn();
    renderHook(() => useNotificationStream('t', onEvent));
    act(() => {
      created[0].onmessage?.({ data: 'not-json' } as MessageEvent);
    });
    expect(onEvent).not.toHaveBeenCalled();
  });

  it('reconnects with exponential backoff after error', async () => {
    const { result } = renderHook(() =>
      useNotificationStream('t', () => {}),
    );
    act(() => {
      created[0].onerror?.(new Event('error'));
    });
    expect(result.current).toBe('reconnecting');
    expect(created[0].closed).toBe(true);

    // First reconnect at 1s
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(created).toHaveLength(2);

    // Trigger second error → reconnect at 2s
    act(() => {
      created[1].onerror?.(new Event('error'));
    });
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(created).toHaveLength(3);

    // Third error → 4s
    act(() => {
      created[2].onerror?.(new Event('error'));
    });
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    expect(created).toHaveLength(4);
  });

  it('resets backoff after successful reconnection', async () => {
    renderHook(() => useNotificationStream('t', () => {}));
    // Cycle: error → reconnect → open → error → next reconnect must be 1s again
    act(() => {
      created[0].onerror?.(new Event('error'));
      vi.advanceTimersByTime(1000);
    });
    act(() => {
      created[1].onopen?.(new Event('open'));
    });
    act(() => {
      created[1].onerror?.(new Event('error'));
    });
    // After successful open the backoff resets to 1s.
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(created).toHaveLength(3);
  });

  it('closes EventSource on unmount', () => {
    const { unmount } = renderHook(() =>
      useNotificationStream('t', () => {}),
    );
    unmount();
    expect(created[0].closed).toBe(true);
  });

  it('closes when accessToken transitions to null (logout)', () => {
    const { result, rerender } = renderHook(
      ({ token }: { token: string | null }) =>
        useNotificationStream(token, () => {}),
      { initialProps: { token: 't1' as string | null } },
    );
    expect(created).toHaveLength(1);
    rerender({ token: null });
    expect(result.current).toBe('idle');
    expect(created[0].closed).toBe(true);
  });
});
