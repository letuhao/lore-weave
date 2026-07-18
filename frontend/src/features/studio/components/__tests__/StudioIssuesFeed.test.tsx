import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

// S-10 O3 — the Issues feed: ranked problem rows, each deep-linking to the panel that owns the fix.
const openPanel = vi.hoisted(() => vi.fn());
const diag = vi.hoisted(() => vi.fn());
vi.mock('../../host/StudioHostProvider', () => ({
  useStudioHost: () => ({ bookId: 'b1', openPanel }),
}));
vi.mock('../../hooks/useBookDiagnostics', () => ({
  useBookDiagnostics: () => diag(),
}));

import { StudioIssuesFeed } from '../StudioIssuesFeed';

const base = {
  items: [], counts: {}, total: 0, refsCapped: false, warnings: [] as string[],
  isLoading: false, isError: false, error: null, refetch: vi.fn(),
};

beforeEach(() => { openPanel.mockReset(); diag.mockReturnValue(base); });

describe('StudioIssuesFeed (O3)', () => {
  it('renders ranked rows and deep-links a row to the panel that owns the fix', () => {
    diag.mockReturnValue({
      ...base,
      total: 2,
      items: [
        { kind: 'broken_canon_rule', severity: 'error', title: 'canon rule broken: "no magic"' },
        { kind: 'index_stale', severity: 'warn', title: '3 chapters have a stale prose index' },
      ],
    });
    render(<StudioIssuesFeed />);
    expect(screen.getByTestId('studio-issue-broken_canon_rule')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('studio-issue-broken_canon_rule'));
    // broken_canon_rule → quality-canon-rules, focused, book-scoped
    expect(openPanel).toHaveBeenCalledWith('quality-canon-rules', { focus: true, params: { bookId: 'b1' } });
  });

  it('surfaces source warnings (absent, not zero)', () => {
    diag.mockReturnValue({ ...base, warnings: ['conformance + index staleness could not be computed'] });
    render(<StudioIssuesFeed />);
    expect(screen.getByTestId('studio-issues-warning')).toHaveTextContent('conformance');
  });

  it('shows a clean empty state when nothing is wrong', () => {
    render(<StudioIssuesFeed />);
    expect(screen.getByTestId('studio-issues-empty')).toBeInTheDocument();
  });

  it('shows an error state when the read fails', () => {
    diag.mockReturnValue({ ...base, isError: true });
    render(<StudioIssuesFeed />);
    expect(screen.getByTestId('studio-issues-error')).toBeInTheDocument();
  });
});
