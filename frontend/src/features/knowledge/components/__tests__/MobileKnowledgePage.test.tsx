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
vi.mock('../PrivacyTab', () => ({
  PrivacyTab: () => <div data-testid="stub-privacy-tab" />,
}));
// K19f β — GlobalMobile replaces the embedded GlobalBioTab.
vi.mock('../mobile/GlobalMobile', () => ({
  GlobalMobile: () => <div data-testid="stub-global-mobile" />,
}));
// K19f γ — ProjectsMobile replaces the embedded ProjectsTab.
vi.mock('../mobile/ProjectsMobile', () => ({
  ProjectsMobile: () => <div data-testid="stub-projects-mobile" />,
}));
// K19f δ — JobsMobile replaces the embedded ExtractionJobsTab.
vi.mock('../mobile/JobsMobile', () => ({
  JobsMobile: () => <div data-testid="stub-jobs-mobile" />,
}));

import { MobileKnowledgePage, MobilePrivacyShell } from '../MobileKnowledgePage';
import { TOUCH_TARGET_CLASS } from '../../lib/touchTarget';

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
    // Mobile variants mount inside their sections.
    expect(screen.getByTestId('stub-global-mobile')).toBeTruthy();
    expect(screen.getByTestId('stub-projects-mobile')).toBeTruthy();
    expect(screen.getByTestId('stub-jobs-mobile')).toBeTruthy();
  });

  it('renders the desktop-only notice for the hidden advanced tabs', () => {
    render(<MobileKnowledgePage />, { wrapper: Wrapper });
    const banner = screen.getByTestId('mobile-desktop-only-banner');
    // Title + body both rendered — i18n mock-bypass returns the key
    // path verbatim, so we just assert non-empty content.
    expect(banner.textContent?.length ?? 0).toBeGreaterThan(0);
  });

  it('renders a privacy link routed to /knowledge/privacy + applies TOUCH_TARGET_CLASS (K19f.5)', () => {
    render(<MobileKnowledgePage />, { wrapper: Wrapper });
    const link = screen.getByTestId('mobile-privacy-link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('/knowledge/privacy');
    // K19f.5 audit: the footer link must meet the 44px minimum tap
    // target. A regression removing TOUCH_TARGET_CLASS would ship a
    // ~18-20px tall link that thumbs miss on a phone. Import the
    // constant so the invariant (not the raw string) is what's
    // asserted — if the constant value changes (e.g. to Tailwind's
    // `min-h-11` shorthand), the test stays valid.
    expect(link.className).toContain(TOUCH_TARGET_CLASS);
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
    // K19f.5 audit: back link must meet the 44px minimum tap target.
    expect(back.className).toContain(TOUCH_TARGET_CLASS);
    // No desktop tabs nav rendered — no role="tablist" anywhere in
    // the shell. This is the bug the review-impl caught.
    expect(screen.queryByRole('tablist')).toBeNull();
  });
});
