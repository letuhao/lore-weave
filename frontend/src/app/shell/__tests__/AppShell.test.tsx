// AppShell — the viewport-remount guard (spec D-MOB-2 / MB1 / MB6). The load-bearing
// assertion: crossing the mobile breakpoint swaps ONLY the chrome, and the feature route
// tree under the single persistent <Outlet/> is PRESERVED — same component instance, state
// intact, mounted exactly once (proxy for "exactly one SSE subscription"). A regression to a
// top-level <Mobile/> : <Desktop/> ternary would remount the subtree and red these tests.
import { render, screen, act, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Heavy desktop chrome — stub it so the test is about the shell, not the Sidebar.
vi.mock('@/components/layout/Sidebar', () => ({
  Sidebar: () => <div data-testid="desktop-sidebar" />,
}));
// i18n: labels resolve to their keys (MobileTabBar is real).
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}));

import { AppShell } from '../AppShell';

// A controllable matchMedia so we can flip the viewport mid-test and fire `change`.
function installMatchMedia(initialMatches: boolean) {
  const listeners = new Set<(e: { matches: boolean }) => void>();
  let matches = initialMatches;
  const mql = {
    get matches() {
      return matches;
    },
    media: '(max-width: 767px)',
    onchange: null,
    addEventListener: (_: string, cb: (e: { matches: boolean }) => void) => listeners.add(cb),
    removeEventListener: (_: string, cb: (e: { matches: boolean }) => void) => listeners.delete(cb),
    addListener: (cb: (e: { matches: boolean }) => void) => listeners.add(cb),
    removeListener: (cb: (e: { matches: boolean }) => void) => listeners.delete(cb),
    dispatchEvent: () => true,
  };
  window.matchMedia = vi.fn().mockImplementation(() => mql) as unknown as typeof window.matchMedia;
  return {
    setMatches(v: boolean) {
      matches = v;
      act(() => {
        listeners.forEach((cb) => cb({ matches: v }));
      });
    },
  };
}

// A stateful, mount-counting probe standing in for a live feature route (e.g. a chat
// stream that subscribes once on mount).
let mountCount = 0;
function Probe() {
  const [n, setN] = useState(0);
  useEffect(() => {
    mountCount += 1;
  }, []);
  return (
    <button data-testid="probe" onClick={() => setN((v) => v + 1)}>
      count:{n}
    </button>
  );
}

function renderShell() {
  return render(
    <MemoryRouter initialEntries={['/probe']}>
      <Routes>
        <Route element={<AppShell variant="dashboard" />}>
          <Route path="/probe" element={<Probe />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('AppShell — chrome-only swap preserves the Outlet subtree', () => {
  beforeEach(() => {
    mountCount = 0;
  });

  it('desktop → mobile flip keeps the SAME feature instance (state intact, mounted once)', () => {
    const mm = installMatchMedia(false); // start desktop
    renderShell();

    // Desktop chrome only.
    expect(screen.getByTestId('desktop-sidebar')).toBeTruthy();
    expect(screen.queryByTestId('mobile-tab-bar')).toBeNull();

    // Build up state in the feature tree.
    const probe = screen.getByTestId('probe');
    fireEvent.click(probe);
    fireEvent.click(probe);
    fireEvent.click(probe);
    expect(screen.getByTestId('probe').textContent).toBe('count:3');

    // Cross the breakpoint into mobile.
    mm.setMatches(true);

    // Chrome swapped…
    expect(screen.queryByTestId('desktop-sidebar')).toBeNull();
    expect(screen.getByTestId('mobile-tab-bar')).toBeTruthy();

    // …but the feature tree is PRESERVED: state survived and it never remounted.
    expect(screen.getByTestId('probe').textContent).toBe('count:3');
    expect(mountCount).toBe(1);
  });

  it('mobile → desktop flip also preserves state and mounts the feature exactly once', () => {
    const mm = installMatchMedia(true); // start mobile
    renderShell();

    expect(screen.getByTestId('mobile-tab-bar')).toBeTruthy();
    expect(screen.queryByTestId('desktop-sidebar')).toBeNull();

    fireEvent.click(screen.getByTestId('probe'));
    fireEvent.click(screen.getByTestId('probe'));
    expect(screen.getByTestId('probe').textContent).toBe('count:2');

    mm.setMatches(false);

    expect(screen.getByTestId('desktop-sidebar')).toBeTruthy();
    expect(screen.queryByTestId('mobile-tab-bar')).toBeNull();
    expect(screen.getByTestId('probe').textContent).toBe('count:2');
    expect(mountCount).toBe(1);
  });

  it('renders exactly one chrome at a time (never both mounted — no double-SSE surface)', () => {
    installMatchMedia(false);
    renderShell();
    const bothDesktop =
      !!screen.queryByTestId('desktop-sidebar') && !!screen.queryByTestId('mobile-tab-bar');
    expect(bothDesktop).toBe(false);
    expect(screen.getByTestId('desktop-sidebar')).toBeTruthy();
  });
});
