import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ChapterImportReview } from '../ChapterImportReview';
import type { ParsedChapter } from '../parseChapters';

const make = (n: number): ParsedChapter[] =>
  Array.from({ length: n }, (_, i) => ({
    id: `c${i}`,
    filename: `${i + 1}.txt`,
    title: `T${i + 1}`,
    size: 1024,
    included: true,
  }));

const baseProps = {
  onSetIncluded: vi.fn(),
  onSetTitle: vi.fn(),
  onSetAllIncluded: vi.fn(),
};

describe('ChapterImportReview pagination', () => {
  it('pages through a large list (50/pg) — page 2 shows the next slice', () => {
    render(<ChapterImportReview chapters={make(120)} {...baseProps} />);

    // Page 1: first chapter visible, page-2 chapter not yet rendered.
    expect(screen.getByDisplayValue('T1')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('T51')).toBeNull();

    fireEvent.click(screen.getByLabelText('Next page'));

    // Page 2: row 51 (start offset) now visible, page-1 chapter gone.
    expect(screen.getByDisplayValue('T51')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('T1')).toBeNull();
  });

  it('no pager for a single page', () => {
    render(<ChapterImportReview chapters={make(10)} {...baseProps} />);
    expect(screen.queryByLabelText('Next page')).toBeNull();
  });
});
