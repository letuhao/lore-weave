import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

/**
 * Lock the K19f.1 mobile guard in KnowledgePage. There was no
 * existing page-level test before this cycle (post-/review-impl M2)
 * so the guard's three branches — desktop / mobile-non-privacy /
 * mobile-privacy — needed dedicated coverage. A regression that
 * inverted either condition would silently ship mobile users into
 * the desktop shell (or vice versa).
 */

const useIsMobileMock = vi.fn();
vi.mock('@/features/knowledge/hooks/useIsMobile', () => ({
  useIsMobile: () => useIsMobileMock(),
}));

// All tab content components get stubbed — the page only needs to
// pick the right child; the children's own tests cover their
// internals. Without stubs this test would pull in every hook +
// provider the desktop tab tree expects.
vi.mock('@/features/knowledge/components/ProjectsTab', () => ({
  ProjectsTab: () => <div data-testid="stub-projects-tab" />,
}));
vi.mock('@/features/knowledge/components/GlobalBioTab', () => ({
  GlobalBioTab: () => <div data-testid="stub-global-bio-tab" />,
}));
vi.mock('@/features/knowledge/components/ExtractionJobsTab', () => ({
  ExtractionJobsTab: () => <div data-testid="stub-extraction-jobs-tab" />,
}));
vi.mock('@/features/knowledge/components/EntitiesTab', () => ({
  EntitiesTab: () => <div data-testid="stub-entities-tab" />,
}));
vi.mock('@/features/knowledge/components/TimelineTab', () => ({
  TimelineTab: () => <div data-testid="stub-timeline-tab" />,
}));
vi.mock('@/features/knowledge/components/RawDrawersTab', () => ({
  RawDrawersTab: () => <div data-testid="stub-raw-drawers-tab" />,
}));
vi.mock('@/features/knowledge/components/PrivacyTab', () => ({
  PrivacyTab: () => <div data-testid="stub-privacy-tab" />,
}));
vi.mock('@/features/knowledge/components/MobileKnowledgePage', () => ({
  MobileKnowledgePage: () => <div data-testid="stub-mobile-page" />,
  MobilePrivacyShell: () => <div data-testid="stub-mobile-privacy" />,
}));

import { KnowledgePage } from '../KnowledgePage';

function Wrapper({
  initialPath = '/knowledge/projects',
  children,
}: PropsWithChildren<{ initialPath?: string }>) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

function renderAt(initialPath: string) {
  return render(
    <Routes>
      <Route path="/knowledge" element={<KnowledgePage />} />
      <Route path="/knowledge/:tab" element={<KnowledgePage />} />
    </Routes>,
    {
      wrapper: (props) => <Wrapper initialPath={initialPath}>{props.children}</Wrapper>,
    },
  );
}

describe('KnowledgePage mobile guard', () => {
  beforeEach(() => {
    useIsMobileMock.mockReset();
  });

  it('renders the desktop tab shell when not mobile', () => {
    useIsMobileMock.mockReturnValue(false);
    renderAt('/knowledge/projects');
    expect(screen.getByRole('tablist')).toBeTruthy();
    expect(screen.getByTestId('stub-projects-tab')).toBeTruthy();
    // Mobile stubs should NOT mount.
    expect(screen.queryByTestId('stub-mobile-page')).toBeNull();
    expect(screen.queryByTestId('stub-mobile-privacy')).toBeNull();
  });

  it('renders MobileKnowledgePage on mobile for non-privacy routes', () => {
    useIsMobileMock.mockReturnValue(true);
    renderAt('/knowledge/projects');
    expect(screen.getByTestId('stub-mobile-page')).toBeTruthy();
    // Desktop shell should NOT mount.
    expect(screen.queryByRole('tablist')).toBeNull();
    expect(screen.queryByTestId('stub-projects-tab')).toBeNull();
    expect(screen.queryByTestId('stub-mobile-privacy')).toBeNull();
  });

  it('renders MobilePrivacyShell on mobile + /knowledge/privacy (review-impl M1 regression lock)', () => {
    useIsMobileMock.mockReturnValue(true);
    renderAt('/knowledge/privacy');
    expect(screen.getByTestId('stub-mobile-privacy')).toBeTruthy();
    // Neither the desktop tab shell NOR the main mobile page should
    // render here — the Privacy route takes its own bespoke mobile
    // shell so the 7-tab nav doesn't overflow the viewport.
    expect(screen.queryByRole('tablist')).toBeNull();
    expect(screen.queryByTestId('stub-mobile-page')).toBeNull();
    expect(screen.queryByTestId('stub-privacy-tab')).toBeNull();
  });

  it('renders desktop PrivacyTab on /knowledge/privacy when not mobile', () => {
    useIsMobileMock.mockReturnValue(false);
    renderAt('/knowledge/privacy');
    expect(screen.getByRole('tablist')).toBeTruthy();
    expect(screen.getByTestId('stub-privacy-tab')).toBeTruthy();
    expect(screen.queryByTestId('stub-mobile-privacy')).toBeNull();
  });
});
