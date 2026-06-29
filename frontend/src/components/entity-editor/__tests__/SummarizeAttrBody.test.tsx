import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// #26/#7 — the summarize attribute body: canonical headline + raw-mentions disclosure.

// Local i18n mock: echo keys, interpolate {{count}} so the sources label is assertable.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && 'count' in opts ? `${key}:${opts.count}` : key,
  }),
}));

import { SummarizeAttrBody, countRawMentions } from '../SummarizeAttrBody';

describe('countRawMentions', () => {
  it('counts JSON-array elements, ignoring blanks', () => {
    expect(countRawMentions('["tall","short","scarred"]')).toBe(3);
    expect(countRawMentions('["tall",""," "]')).toBe(1);
  });
  it('treats a non-empty scalar as one mention, empty as zero', () => {
    expect(countRawMentions('a tall warrior')).toBe(1);
    expect(countRawMentions('')).toBe(0);
    expect(countRawMentions('   ')).toBe(0);
  });
  it('falls back to one mention on malformed JSON', () => {
    expect(countRawMentions('[not json')).toBe(1);
  });
});

describe('SummarizeAttrBody', () => {
  const rawCard = <textarea data-testid="raw-card" />;

  it('renders the canonical value as the headline when present', () => {
    render(
      <SummarizeAttrBody
        canonicalValue="a tall, scarred swordsman"
        canonicalDirty={false}
        rawValue='["tall","short","scarred"]'
        rawCard={rawCard}
      />,
    );
    expect(screen.getByText('a tall, scarred swordsman')).toBeInTheDocument();
    expect(screen.getByText('summarize.canonical_label')).toBeInTheDocument();
    // Sources disclosure shows the raw count and still hosts the editable raw card.
    expect(screen.getByText('summarize.sources:3')).toBeInTheDocument();
    expect(screen.getByTestId('raw-card')).toBeInTheDocument();
    // Not dirty → no pending hint.
    expect(screen.queryByText('summarize.pending_dirty')).not.toBeInTheDocument();
  });

  it('shows the re-summarize-pending hint when canonical is dirty', () => {
    render(
      <SummarizeAttrBody
        canonicalValue="old synthesis"
        canonicalDirty
        rawValue='["a","b"]'
        rawCard={rawCard}
      />,
    );
    expect(screen.getByText(/summarize\.pending_dirty/)).toBeInTheDocument();
  });

  it('shows the pending-new hint when there are raw mentions but no canonical yet', () => {
    render(
      <SummarizeAttrBody canonicalValue={null} rawValue='["a","b"]' rawCard={rawCard} />,
    );
    expect(screen.getByText('summarize.pending_new')).toBeInTheDocument();
    expect(screen.getByText('summarize.sources:2')).toBeInTheDocument();
  });

  it('shows the empty hint when there are no mentions and no canonical', () => {
    render(<SummarizeAttrBody canonicalValue={null} rawValue="" rawCard={rawCard} />);
    expect(screen.getByText('summarize.empty')).toBeInTheDocument();
    expect(screen.getByText('summarize.sources:0')).toBeInTheDocument();
  });
});
