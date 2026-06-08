import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RawSearchResultCard } from '../RawSearchResultCard';
import type { RawSearchHit } from '../../types';

const lexical: RawSearchHit = {
  chapterId: 'c1', chapterTitle: 'Ch', sortOrder: 1, surface: 'draft',
  matchType: 'lexical', score: 1, snippet: 'x', highlights: [],
  location: { blockIndex: 4, headingContext: null, charStart: 0, charEnd: 1 },
};
// P3-C: semantic hits now carry a real blockIndex too (precise scroll).
const semanticWithBlock: RawSearchHit = {
  chapterId: 'c2', chapterTitle: null, sortOrder: 2, surface: 'canon',
  matchType: 'semantic', score: 0.9, snippet: 'y', highlights: [],
  location: { chunkIndex: 3, blockIndex: 7, headingContext: null, charStart: 0, charEnd: 0 },
};
const semanticNoBlock: RawSearchHit = {
  chapterId: 'c3', chapterTitle: null, sortOrder: 3, surface: 'canon',
  matchType: 'semantic', score: 0.9, snippet: 'z', highlights: [],
  location: { chunkIndex: 3, headingContext: null, charStart: 0, charEnd: 0 },
};

describe('RawSearchResultCard jump-to-source', () => {
  it('passes the blockIndex for a lexical hit (precise scroll)', () => {
    const onJump = vi.fn();
    render(<ul><RawSearchResultCard hit={lexical} onJump={onJump} /></ul>);
    fireEvent.click(screen.getByTestId('raw-search-jump'));
    expect(onJump).toHaveBeenCalledWith('c1', 4);
  });

  it('passes the blockIndex for a semantic hit too (P3-C precise scroll)', () => {
    const onJump = vi.fn();
    render(<ul><RawSearchResultCard hit={semanticWithBlock} onJump={onJump} /></ul>);
    fireEvent.click(screen.getByTestId('raw-search-jump'));
    expect(onJump).toHaveBeenCalledWith('c2', 7);
  });

  it('passes undefined when a semantic hit has no blockIndex (fallback to top)', () => {
    const onJump = vi.fn();
    render(<ul><RawSearchResultCard hit={semanticNoBlock} onJump={onJump} /></ul>);
    fireEvent.click(screen.getByTestId('raw-search-jump'));
    expect(onJump).toHaveBeenCalledWith('c3', undefined);
  });
});
