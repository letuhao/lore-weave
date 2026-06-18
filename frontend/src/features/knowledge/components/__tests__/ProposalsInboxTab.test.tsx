import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { ProposalsInboxTab } from '../ProposalsInboxTab';
import * as inboxHook from '../../hooks/useProposalsInbox';
import type { ProposalInbox } from '../../lib/proposalsInbox';

// C11 — ProposalsInboxTab: read-only aggregation of 3 sources with per-origin
// counts, deep-link rows, empty-states, and per-source graceful degrade.
// Route-scoped (G6 — bookId comes from the route project, no select-box).

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, opts?: Record<string, unknown>) =>
      opts && 'title' in opts ? `${k}:${opts.title}` : k,
  }),
}));

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

function mockInbox(value: {
  inbox: ProposalInbox | null;
  isLoading?: boolean;
  isFetching?: boolean;
  error?: Error | null;
}) {
  vi.spyOn(inboxHook, 'useProposalsInbox').mockReturnValue({
    inbox: value.inbox,
    isLoading: value.isLoading ?? false,
    isFetching: value.isFetching ?? false,
    error: value.error ?? null,
    refetch: () => {},
  });
}

const row = (origin: 'glossary' | 'wiki' | 'enrichment', id: string, title: string, url: string) => ({
  id,
  origin,
  title,
  deepLinkUrl: url,
});

describe('ProposalsInboxTab', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('renders all 3 sources merged, with per-origin counts and deep-link rows', () => {
    const gRow = row('glossary', 'g1', '九天明帝经', '/books/b1/glossary');
    const wRow = row('wiki', 'w1', '张若尘', '/books/b1/wiki');
    const eRow = row('enrichment', 'e1', '林妃', '/books/b1/enrichment');
    mockInbox({
      inbox: {
        rows: [gRow, wRow, eRow],
        sources: [
          { origin: 'glossary', rows: [gRow], error: null },
          { origin: 'wiki', rows: [wRow], error: null },
          { origin: 'enrichment', rows: [eRow], error: null },
        ],
      },
    });

    render(<ProposalsInboxTab bookId="b1" />, { wrapper });

    // per-origin counts
    expect(screen.getByTestId('proposals-count-glossary')).toHaveTextContent('1');
    expect(screen.getByTestId('proposals-count-wiki')).toHaveTextContent('1');
    expect(screen.getByTestId('proposals-count-enrichment')).toHaveTextContent('1');

    // each row deep-links to its source's existing review UI route
    expect(screen.getByTestId('proposals-row-glossary-g1')).toHaveAttribute('href', '/books/b1/glossary');
    expect(screen.getByTestId('proposals-row-wiki-w1')).toHaveAttribute('href', '/books/b1/wiki');
    expect(screen.getByTestId('proposals-row-enrichment-e1')).toHaveAttribute('href', '/books/b1/enrichment');

    // titles carried through
    expect(screen.getByTestId('proposals-row-glossary-g1')).toHaveTextContent('九天明帝经');
  });

  it('degrades gracefully: one source erroring shows a source-error chip while the others still render', () => {
    const gRow = row('glossary', 'g1', 'A', '/books/b1/glossary');
    mockInbox({
      inbox: {
        rows: [gRow],
        sources: [
          { origin: 'glossary', rows: [gRow], error: null },
          { origin: 'wiki', rows: [], error: new Error('wiki 503') },
          { origin: 'enrichment', rows: [], error: null },
        ],
      },
    });

    render(<ProposalsInboxTab bookId="b1" />, { wrapper });

    // the down source shows an error chip, NOT a blanked inbox
    expect(screen.getByTestId('proposals-source-error-wiki')).toBeInTheDocument();
    // the healthy source still renders its row
    expect(screen.getByTestId('proposals-row-glossary-g1')).toBeInTheDocument();
    // the empty-but-healthy source shows its per-group empty state
    expect(screen.getByTestId('proposals-group-empty-enrichment')).toBeInTheDocument();
  });

  it('shows the global empty state when all sources are healthy and empty', () => {
    mockInbox({
      inbox: {
        rows: [],
        sources: [
          { origin: 'glossary', rows: [], error: null },
          { origin: 'wiki', rows: [], error: null },
          { origin: 'enrichment', rows: [], error: null },
        ],
      },
    });

    render(<ProposalsInboxTab bookId="b1" />, { wrapper });

    expect(screen.getByTestId('proposals-empty')).toBeInTheDocument();
  });

  it('shows the no-book state when the project has no linked book (no source fetch)', () => {
    mockInbox({ inbox: null });

    render(<ProposalsInboxTab bookId={null} />, { wrapper });

    expect(screen.getByTestId('proposals-no-book')).toBeInTheDocument();
    expect(screen.queryByTestId('proposals-groups')).not.toBeInTheDocument();
  });

  it('renders the loading state while the inbox query is in flight', () => {
    mockInbox({ inbox: null, isLoading: true });

    render(<ProposalsInboxTab bookId="b1" />, { wrapper });

    expect(screen.getByTestId('proposals-loading')).toBeInTheDocument();
  });
});
