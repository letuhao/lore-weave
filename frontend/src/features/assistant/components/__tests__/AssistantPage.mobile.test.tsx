// M1 — the assistant surface swaps its SECOND child (mobile dock vs desktop rail) by viewport,
// while <Chat> stays the stable first child. The load-bearing assertion: crossing the breakpoint
// never remounts Chat (SSE / voice / unsaved input survive a rotate) even though the strip/dock
// swap. Chat + the dock are stubbed so the test is about the AssistantPageInner layout wiring.
import { render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { useEffect } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

let chatMountCount = 0;
vi.mock('@/features/chat/Chat', () => ({
  Chat: () => {
    useEffect(() => {
      chatMountCount += 1;
    }, []);
    return <div data-testid="chat-surface" />;
  },
}));
vi.mock('../AssistantHomeStrip', () => ({
  AssistantHomeStrip: () => <div data-testid="desktop-strip" />,
}));
vi.mock('../mobile/MobileAssistantDock', () => ({
  MobileAssistantDock: () => <div data-testid="mobile-dock" />,
}));
vi.mock('../mobile/MobileAssistantHeader', () => ({
  MobileAssistantHeader: () => <div data-testid="mobile-header" />,
}));
vi.mock('../../context/AssistantContext', () => ({
  AssistantProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useAssistant: () => ({
    loading: false,
    error: null,
    provisioned: true,
    bookId: 'book-1',
    projectId: 'proj-1',
    reprovision: () => {},
  }),
}));
// The first-run gate is a separate concern (its own test) — here it's satisfied (already seen),
// so the page falls through to the dock/rail layout this test asserts on. `firstRunState` lets a
// single test flip it to the still-loading case (the FR anti-churn guard).
const firstRunState = { isLoading: false, shouldShow: false };
vi.mock('../../hooks/useAssistantFirstRun', () => ({
  useAssistantFirstRun: () => ({ ...firstRunState, markDone: () => {} }),
}));

import { AssistantPage } from '../AssistantPage';

function installMatchMedia(initial: boolean) {
  const listeners = new Set<(e: { matches: boolean }) => void>();
  let matches = initial;
  const mql = {
    get matches() {
      return matches;
    },
    media: '(max-width: 767px)',
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
      act(() => listeners.forEach((cb) => cb({ matches: v })));
    },
  };
}

describe('AssistantPage — mobile dock vs desktop rail (Chat preserved)', () => {
  beforeEach(() => {
    chatMountCount = 0;
  });

  it('mobile shows the dock, not the desktop rail', () => {
    installMatchMedia(true);
    render(
      <MemoryRouter>
        <AssistantPage />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('mobile-dock')).toBeTruthy();
    expect(screen.queryByTestId('desktop-strip')).toBeNull();
    expect(screen.getByTestId('chat-surface')).toBeTruthy();
  });

  it('on mobile, holds the layout while the first-run flag loads — never mounts Chat then tears it down', () => {
    firstRunState.isLoading = true;
    installMatchMedia(true);
    render(
      <MemoryRouter>
        <AssistantPage />
      </MemoryRouter>,
    );
    // The FR anti-churn guard: no <Chat> (no SSE) while the flag is still resolving.
    expect(screen.getByTestId('assistant-first-run-loading')).toBeTruthy();
    expect(screen.queryByTestId('chat-surface')).toBeNull();
    expect(chatMountCount).toBe(0);
    firstRunState.isLoading = false; // restore for the other tests
  });

  it('desktop shows the rail, not the dock', () => {
    installMatchMedia(false);
    render(
      <MemoryRouter>
        <AssistantPage />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('desktop-strip')).toBeTruthy();
    expect(screen.queryByTestId('mobile-dock')).toBeNull();
  });

  it('crossing the breakpoint swaps dock/rail but NEVER remounts Chat', () => {
    const mm = installMatchMedia(false); // desktop
    render(
      <MemoryRouter>
        <AssistantPage />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('desktop-strip')).toBeTruthy();
    expect(chatMountCount).toBe(1);

    mm.setMatches(true); // → mobile

    expect(screen.getByTestId('mobile-dock')).toBeTruthy();
    expect(screen.queryByTestId('desktop-strip')).toBeNull();
    // Chat is the stable first child — one mount across the swap.
    expect(chatMountCount).toBe(1);
  });
});
