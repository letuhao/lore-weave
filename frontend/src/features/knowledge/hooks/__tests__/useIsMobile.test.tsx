import { describe, it, expect, afterEach, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useIsMobile } from '../useIsMobile';

/**
 * jsdom doesn't ship ``window.matchMedia``; each test installs a
 * minimal polyfill via ``Object.defineProperty`` so we don't pollute
 * the global vitest setup file. The polyfill records registered
 * listeners so tests can simulate a viewport change by firing
 * ``change`` manually.
 */

interface MockMediaQueryList {
  matches: boolean;
  media: string;
  addEventListener: (type: 'change', fn: (e: MediaQueryListEvent) => void) => void;
  removeEventListener: (type: 'change', fn: (e: MediaQueryListEvent) => void) => void;
  dispatchEvent: (event: MediaQueryListEvent) => boolean;
  /** back-compat aliases jsdom still expects on the returned object */
  addListener: (fn: (e: MediaQueryListEvent) => void) => void;
  removeListener: (fn: (e: MediaQueryListEvent) => void) => void;
  onchange: ((this: MediaQueryList, ev: MediaQueryListEvent) => void) | null;
}

function installMatchMediaMock(initialMatches: boolean): {
  setMatches: (next: boolean) => void;
  restore: () => void;
} {
  const listeners = new Set<(e: MediaQueryListEvent) => void>();
  let matches = initialMatches;

  const mql: MockMediaQueryList = {
    get matches() {
      return matches;
    },
    media: '',
    addEventListener: (_type, fn) => listeners.add(fn),
    removeEventListener: (_type, fn) => listeners.delete(fn),
    dispatchEvent: () => true,
    addListener: (fn) => listeners.add(fn),
    removeListener: (fn) => listeners.delete(fn),
    onchange: null,
  };

  const matchMediaMock = vi.fn().mockImplementation((query: string) => {
    mql.media = query;
    return mql as unknown as MediaQueryList;
  });

  const descriptor = Object.getOwnPropertyDescriptor(window, 'matchMedia');
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: matchMediaMock,
  });

  return {
    setMatches(next: boolean) {
      matches = next;
      const event = { matches: next, media: mql.media } as MediaQueryListEvent;
      listeners.forEach((fn) => fn(event));
    },
    restore() {
      if (descriptor) {
        Object.defineProperty(window, 'matchMedia', descriptor);
      } else {
        // jsdom default: matchMedia doesn't exist — delete to clean up.
        delete (window as { matchMedia?: unknown }).matchMedia;
      }
    },
  };
}

describe('useIsMobile', () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
  });

  it('returns false when window.matchMedia is unavailable', () => {
    const original = Object.getOwnPropertyDescriptor(window, 'matchMedia');
    // Simulate a runtime without matchMedia (older jsdom, SSR, etc.).
    delete (window as { matchMedia?: unknown }).matchMedia;
    restore = () => {
      if (original) Object.defineProperty(window, 'matchMedia', original);
    };
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);
  });

  it('returns the initial matchMedia.matches synchronously on first render', () => {
    const mock = installMatchMediaMock(true);
    restore = mock.restore;
    const { result } = renderHook(() => useIsMobile());
    // No FOUC — the synchronous readInitial returns true before the
    // useEffect runs, so the first render sees the right value.
    expect(result.current).toBe(true);
  });

  it('updates when the MediaQueryList fires a change event', () => {
    const mock = installMatchMediaMock(false);
    restore = mock.restore;
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);
    act(() => {
      mock.setMatches(true);
    });
    expect(result.current).toBe(true);
    act(() => {
      mock.setMatches(false);
    });
    expect(result.current).toBe(false);
  });
});
