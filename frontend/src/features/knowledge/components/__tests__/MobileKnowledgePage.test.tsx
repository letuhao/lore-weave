import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

// Embedded tabs each fire their own network queries on mount.
// We don't care about their internal rendering — just that the
// mobile shell renders them as sections. Stub each tab to a
// minimal marker so we can assert the shell's section layout
// without pulling in every hook + provider the desktop tabs expect.
vi.mock('../GlobalBioTab', () => ({
  GlobalBioTab: () => <div data-testid="stub-global-bio-tab" />,
}));
vi.mock('../ProjectsTab', () => ({
  ProjectsTab: () => <div data-testid="stub-projects-tab" />,
}));
vi.mock('../ExtractionJobsTab', () => ({
  ExtractionJobsTab: () => <div data-testid="stub-extraction-jobs-tab" />,
}));
vi.mock('../PrivacyTab', () => ({
  PrivacyTab: () => <div data-testid="stub-privacy-tab" />,
}));

import { MobileKnowledgePage, MobilePrivacyShell } from '../MobileKnowledgePage';

function Wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <MemoryRouter initialEntries={['/knowledge']}>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

describe('MobileKnowledgePage', () => {
  it('renders the three primary sections stacked (Global + Projects + Jobs)', () => {
    render(<MobileKnowledgePage />, { wrapper: Wrapper });
    expect(screen.getByTestId('mobile-section-global')).toBeTruthy();
    expect(screen.getByTestId('mobile-section-projects')).toBeTruthy();
    expect(screen.getByTestId('mobile-section-jobs')).toBeTruthy();
    // Stub tabs mount inside their sections.
    expect(screen.getByTestId('stub-global-bio-tab')).toBeTruthy();
    expect(screen.getByTestId('stub-projects-tab')).toBeTruthy();
    expect(screen.getByTestId('stub-extraction-jobs-tab')).toBeTruthy();
  });

  it('renders the desktop-only notice for the hidden advanced tabs', () => {
    render(<MobileKnowledgePage />, { wrapper: Wrapper });
    const banner = screen.getByTestId('mobile-desktop-only-banner');
    // Title + body both rendered — i18n mock-bypass returns the key
    // path verbatim, so we just assert non-empty content.
    expect(banner.textContent?.length ?? 0).toBeGreaterThan(0);
  });

  it('renders a privacy link routed to /knowledge/privacy', () => {
    render(<MobileKnowledgePage />, { wrapper: Wrapper });
    const link = screen.getByTestId('mobile-privacy-link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('/knowledge/privacy');
  });
});

describe('MobilePrivacyShell', () => {
  it('renders PrivacyTab without the desktop 7-tab nav and a back link to /knowledge/projects', () => {
    // Review-impl M1 regression lock: before the fix, mobile +
    // activeTab="privacy" fell through to the desktop render which
    // shipped a 7-item nav that overflows a 375px phone. The shell
    // must render JUST the PrivacyTab body + a back-link.
    render(<MobilePrivacyShell />, { wrapper: Wrapper });
    expect(screen.getByTestId('mobile-privacy-shell')).toBeTruthy();
    expect(screen.getByTestId('stub-privacy-tab')).toBeTruthy();
    const back = screen.getByTestId('mobile-privacy-back') as HTMLAnchorElement;
    expect(back.getAttribute('href')).toBe('/knowledge/projects');
    // No desktop tabs nav rendered — no role="tablist" anywhere in
    // the shell. This is the bug the review-impl caught.
    expect(screen.queryByRole('tablist')).toBeNull();
  });
});
