import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, renderHook } from '@testing-library/react';

// Isolate the shell from its four data panels — stub each to a trivial marker so
// the test exercises only the tab strip + visited/hidden idiom + H0 chip.
vi.mock('../ProposalsPanel', () => ({
  ProposalsPanel: () => <div data-testid="stub-proposals">proposals-panel</div>,
}));
vi.mock('../GapsPanel', () => ({
  GapsPanel: () => <div data-testid="stub-gaps">gaps-panel</div>,
}));
vi.mock('../SourcesPanel', () => ({
  SourcesPanel: () => <div data-testid="stub-sources">sources-panel</div>,
}));
vi.mock('../JobsPanel', () => ({
  JobsPanel: () => <div data-testid="stub-jobs">jobs-panel</div>,
}));
vi.mock('../SettingsPanel', () => ({
  SettingsPanel: () => <div data-testid="stub-settings">settings-panel</div>,
}));
vi.mock('../compose/ComposePanel', () => ({
  ComposePanel: () => <div data-testid="stub-compose">compose-panel</div>,
}));

// LE-065 — the shell reads list totals for the tab count badges; stub them (the
// hooks have their own tests). proposals=7 / sources=5 / jobs=2; gaps via context.
vi.mock('../../hooks/useProposals', () => ({
  useProposals: () => ({ total: 7, items: [], projectIds: [] }),
}));
vi.mock('../../hooks/useEnrichmentSources', () => ({
  useEnrichmentSources: () => ({ total: 5, items: [] }),
}));
vi.mock('../../hooks/useEnrichmentJobs', () => ({
  useEnrichmentJobs: () => ({ total: 2, items: [] }),
}));

import { EnrichmentView } from '../EnrichmentView';
import {
  EnrichmentProvider,
  useEnrichmentContext,
} from '../../context/EnrichmentContext';

function renderView() {
  return render(
    <EnrichmentProvider bookId="book-1">
      <EnrichmentView />
    </EnrichmentProvider>,
  );
}

describe('useEnrichmentContext', () => {
  it('throws when used outside an EnrichmentProvider', () => {
    expect(() => renderHook(() => useEnrichmentContext())).toThrow(
      /must be used within EnrichmentProvider/,
    );
  });

  it('returns the bookId + default state inside the provider', () => {
    const { result } = renderHook(() => useEnrichmentContext(), {
      wrapper: ({ children }) => (
        <EnrichmentProvider bookId="book-1">{children}</EnrichmentProvider>
      ),
    });
    expect(result.current.bookId).toBe('book-1');
    expect(result.current.activePanel).toBe('proposals');
    expect(result.current.selectedProposalId).toBeNull();
    expect(result.current.projectFilter).toBeNull();
  });
});

describe('EnrichmentView', () => {
  it('renders the six tab buttons + the H0 marker', () => {
    renderView();
    expect(screen.getByTestId('enrichment-tab-compose')).toBeInTheDocument();
    expect(screen.getByTestId('enrichment-tab-proposals')).toBeInTheDocument();
    expect(screen.getByTestId('enrichment-tab-gaps')).toBeInTheDocument();
    expect(screen.getByTestId('enrichment-tab-sources')).toBeInTheDocument();
    expect(screen.getByTestId('enrichment-tab-jobs')).toBeInTheDocument();
    expect(screen.getByTestId('enrichment-tab-settings')).toBeInTheDocument();
    expect(screen.getByTestId('enrichment-h0-marker')).toBeInTheDocument();
  });

  it('clicking the compose tab lazy-mounts + reveals the ComposePanel (no count badge)', () => {
    renderView();
    expect(screen.queryByTestId('stub-compose')).toBeNull(); // not visited yet
    fireEvent.click(screen.getByTestId('enrichment-tab-compose'));
    expect(screen.getByTestId('stub-compose').parentElement?.className).not.toContain('hidden');
    expect(screen.queryByTestId('enrichment-tab-count-compose')).toBeNull();
  });

  it('clicking the settings (profile) tab lazy-mounts + reveals the SettingsPanel', () => {
    renderView();
    expect(screen.queryByTestId('stub-settings')).toBeNull(); // not visited yet
    fireEvent.click(screen.getByTestId('enrichment-tab-settings'));
    const settings = screen.getByTestId('stub-settings');
    expect(settings.parentElement?.className).not.toContain('hidden');
    // no count badge on the settings tab
    expect(screen.queryByTestId('enrichment-tab-count-settings')).toBeNull();
  });

  // LE-065 — count badges from the list totals; gaps has no badge until Detect runs.
  it('renders count badges for proposals/sources/jobs but not gaps (null until detect)', () => {
    renderView();
    expect(screen.getByTestId('enrichment-tab-count-proposals')).toHaveTextContent('7');
    expect(screen.getByTestId('enrichment-tab-count-sources')).toHaveTextContent('5');
    expect(screen.getByTestId('enrichment-tab-count-jobs')).toHaveTextContent('2');
    expect(screen.queryByTestId('enrichment-tab-count-gaps')).toBeNull();
  });

  it('starts on the proposals panel (active tab styled, panel visible)', () => {
    renderView();
    expect(screen.getByTestId('enrichment-tab-proposals').className).toContain(
      'border-primary',
    );
    // proposals is the only visited panel at first paint
    const proposals = screen.getByTestId('stub-proposals');
    expect(proposals.parentElement?.className).not.toContain('hidden');
    expect(screen.queryByTestId('stub-gaps')).toBeNull();
  });

  it('clicking the gaps tab lazy-mounts + reveals gaps and hides proposals', () => {
    renderView();
    fireEvent.click(screen.getByTestId('enrichment-tab-gaps'));

    // gaps tab is now the active (primary-styled) one
    expect(screen.getByTestId('enrichment-tab-gaps').className).toContain(
      'border-primary',
    );
    expect(screen.getByTestId('enrichment-tab-proposals').className).toContain(
      'border-transparent',
    );

    // gaps panel is mounted + visible; proposals stays mounted but hidden (no unmount)
    const gaps = screen.getByTestId('stub-gaps');
    expect(gaps.parentElement?.className).not.toContain('hidden');
    const proposals = screen.getByTestId('stub-proposals');
    expect(proposals.parentElement?.className).toContain('hidden');
  });

  it('keeps previously-visited panels mounted when switching away (CSS hidden idiom)', () => {
    renderView();
    fireEvent.click(screen.getByTestId('enrichment-tab-sources'));
    fireEvent.click(screen.getByTestId('enrichment-tab-jobs'));

    // both sources and jobs were visited -> both still in the DOM
    expect(screen.getByTestId('stub-sources')).toBeInTheDocument();
    expect(screen.getByTestId('stub-jobs')).toBeInTheDocument();
    // jobs is active/visible, sources is hidden
    expect(screen.getByTestId('stub-jobs').parentElement?.className).not.toContain(
      'hidden',
    );
    expect(
      screen.getByTestId('stub-sources').parentElement?.className,
    ).toContain('hidden');
  });
});
