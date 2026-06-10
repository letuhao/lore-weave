import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';

// i18n mock: return the key (with n interpolated) so assertions don't depend on copy.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) =>
      o && o.n != null ? `${k}:${o.n}` : k,
  }),
}));

import { CitationChip } from '../CitationChip';
import { CitationProvider } from '../CitationContext';
import { InlineRenderer } from '../InlineRenderer';

const ATTRS = {
  n: 1,
  cite_id: 'P1',
  source_type: 'passage',
  chapter_id: 'ch1',
  block_index: 4,
  score: 0.9,
  snippet: 'Harker traveled to Transylvania',
};

function renderChip(bookId?: string) {
  return render(
    <MemoryRouter>
      <CitationProvider bookId={bookId}>
        <CitationChip attrs={ATTRS}>[1]</CitationChip>
      </CitationProvider>
    </MemoryRouter>,
  );
}

describe('CitationChip (wiki-llm M7a)', () => {
  it('renders [n] and opens a popover with the cited snippet (no fetch)', () => {
    renderChip('book-1');
    const chip = screen.getByRole('button');
    expect(chip.textContent).toBe('[1]');
    fireEvent.click(chip);
    expect(screen.getByText('Harker traveled to Transylvania')).toBeTruthy();
  });

  it('builds a precise jump-to-source link when book + chapter are known', () => {
    renderChip('book-1');
    fireEvent.click(screen.getByRole('button'));
    const link = screen.getByRole('link') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('/books/book-1/chapters/ch1/read?block=4');
  });

  it('shows a relevance % for an in-range score and hides a misleading out-of-range one', () => {
    const { unmount } = render(
      <MemoryRouter>
        <CitationProvider bookId="b">
          <CitationChip attrs={{ ...ATTRS, score: 0.9 }}>[1]</CitationChip>
        </CitationProvider>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText('90%')).toBeTruthy();
    unmount();

    render(
      <MemoryRouter>
        <CitationProvider bookId="b">
          <CitationChip attrs={{ ...ATTRS, score: 1.5 }}>[1]</CitationChip>
        </CitationProvider>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button'));
    expect(screen.queryByText('150%')).toBeNull(); // out-of-range score not rendered
  });

  it('degrades to popover-only (no jump link) when there is no book context', () => {
    renderChip(undefined);
    fireEvent.click(screen.getByRole('button'));
    expect(screen.queryByRole('link')).toBeNull();
    // the snippet still shows, so the claim stays auditable
    expect(screen.getByText('Harker traveled to Transylvania')).toBeTruthy();
  });

  it('InlineRenderer renders a body citation as a SUPERSCRIPT chip (citation + superscript marks)', () => {
    render(
      <MemoryRouter>
        <CitationProvider bookId="b">
          <InlineRenderer
            content={[
              {
                type: 'text',
                text: '[1]',
                marks: [{ type: 'citation', attrs: ATTRS }, { type: 'superscript' }],
              },
            ]}
          />
        </CitationProvider>
      </MemoryRouter>,
    );
    const chip = screen.getByRole('button');
    expect(chip.textContent).toBe('[1]');
    // body citation is superscript-wrapped (the mapper's separate superscript mark)
    expect(chip.closest('sup')).not.toBeNull();
  });

  it('InlineRenderer renders a References citation FULL-SIZE with the label intact (citation-only mark)', () => {
    render(
      <MemoryRouter>
        <CitationProvider bookId="b">
          <InlineRenderer
            content={[
              {
                type: 'text',
                text: '[1] Harker traveled to Transylvania',
                marks: [{ type: 'citation', attrs: ATTRS }],
              },
            ]}
          />
        </CitationProvider>
      </MemoryRouter>,
    );
    const chip = screen.getByRole('button');
    // the label text is preserved (NOT replaced by just "[n]"), and not superscript
    expect(chip.textContent).toBe('[1] Harker traveled to Transylvania');
    expect(chip.closest('sup')).toBeNull();
  });
});
