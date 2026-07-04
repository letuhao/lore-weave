import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// A mutable route param so a test can simulate an in-session book switch (same route,
// different :bookId — React Router keeps the page mounted).
const route = vi.hoisted(() => ({ bookId: 'b1' }));
vi.mock('react-router-dom', async (orig) => {
  const m = await orig<typeof import('react-router-dom')>();
  return { ...m, useParams: () => ({ bookId: route.bookId }) };
});
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/features/books/api', () => ({
  booksApi: { getBook: () => Promise.resolve({ title: 'Book', original_language: 'en' }) },
}));

// The manuscript navigator fetches (react-query); stub it so the page-frame test stays chrome-only.
vi.mock('@/features/studio/manuscript/ManuscriptNavigator', () => ({
  ManuscriptNavigator: () => <div data-testid="manuscript-nav-stub" />,
}));

// Palettes are covered by their own suites; stub them here (QuickOpen pulls react-query via the
// shared jump hook — out of scope for this chrome-only frame test).
vi.mock('@/features/studio/palette/QuickOpen', () => ({ QuickOpen: () => null }));
vi.mock('@/features/studio/palette/CommandPalette', () => ({ CommandPalette: () => null }));

// #12 — the hoist resolves the composition Work (react-query) for scenes[]; chrome-only test →
// no Work, no QueryClient needed.
vi.mock('@/features/composition/hooks/useWork', () => ({ useWorkResolution: () => ({ data: null }) }));
// #16 2.10 — progress-reporting also calls react-query's useQueryClient() internally; stub it
// out for the same "chrome-only test, no QueryClient" reason as useWork above.
vi.mock('@/features/composition/hooks/useProgress', () => ({
  useReportProgress: () => vi.fn(),
  useEnsureBaseline: () => vi.fn(),
}));

// The dock is mocked to COUNT mounts — D4: chrome changes must never remount it (a remount
// drops in-flight panel state); a book switch, conversely, MUST remount it (fresh per-book).
const dockMounts = vi.hoisted(() => ({ n: 0 }));
vi.mock('@/features/studio/components/StudioDock', () => ({
  StudioDock: () => {
    React.useEffect(() => { dockMounts.n += 1; }, []);
    return <div data-testid="dock" />;
  },
}));

// #16 1.5 — the deep-link seam: ChaptersTab's row-click/pencil-icon navigate to
// /books/:id/studio?chapter=<id> instead of the legacy editor route. Spy on the host action the
// URL param should trigger, rather than asserting on ManuscriptUnitProvider internals.
const focusManuscriptUnit = vi.hoisted(() => vi.fn());
vi.mock('@/features/studio/host/StudioHostProvider', async (orig) => {
  const m = await orig<typeof import('@/features/studio/host/StudioHostProvider')>();
  return {
    ...m,
    useStudioHost: () => ({ ...m.useStudioHost(), focusManuscriptUnit }),
  };
});

import { WritingStudioPage } from '../WritingStudioPage';

const renderPage = (initialEntries: string[] = ['/']) => render(
  <MemoryRouter initialEntries={initialEntries}><WritingStudioPage /></MemoryRouter>,
);

beforeEach(() => { localStorage.clear(); dockMounts.n = 0; route.bookId = 'b1'; focusManuscriptUnit.mockClear(); });

describe('WritingStudioPage', () => {
  it('D4: mounts the dock exactly once across activity switch + bottom toggle + collapse', () => {
    renderPage();
    expect(dockMounts.n).toBe(1);
    fireEvent.click(screen.getByTestId('studio-activity-bible'));   // switch navigator
    fireEvent.click(screen.getByTestId('studio-toggle-bottom'));    // toggle bottom panel
    fireEvent.click(screen.getByTestId('studio-activity-bible'));   // collapse sidebar
    expect(dockMounts.n).toBe(1);
    expect(screen.getByTestId('dock')).toBeTruthy();
  });

  it('remounts cleanly on an in-session book switch (key={bookId}) so per-book state re-derives', () => {
    const { rerender } = renderPage();
    expect(dockMounts.n).toBe(1);
    // Simulate /books/b1/studio → /books/b2/studio without a full reload.
    route.bookId = 'b2';
    rerender(<MemoryRouter><WritingStudioPage /></MemoryRouter>);
    // The keyed StudioFrame remounts → dock re-created for the new book (guards review-impl #1/#2).
    expect(dockMounts.n).toBe(2);
  });

  // #16 1.5 — the deep-link seam ChaptersTab's row-click/pencil-icon rely on.
  it('a ?chapter= query param focuses that manuscript unit on mount', () => {
    renderPage(['/books/b1/studio?chapter=ch-42']);
    expect(focusManuscriptUnit).toHaveBeenCalledWith('ch-42');
  });

  it('no ?chapter= param means no auto-focus (studio opens to Welcome as before)', () => {
    renderPage(['/books/b1/studio']);
    expect(focusManuscriptUnit).not.toHaveBeenCalled();
  });
});
