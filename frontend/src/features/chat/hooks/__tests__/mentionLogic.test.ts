import { describe, it, expect } from 'vitest';
import {
  detectMention,
  rankCandidates,
  removeMentionText,
  buildMentionCandidates,
  MENTION_VISIBLE_CAP,
  type MentionCandidate,
} from '../useMentionPicker';

const cand = (label: string, id = label): MentionCandidate => ({ id, type: 'book', label });

describe('detectMention', () => {
  it('detects @ at the start of input', () => {
    expect(detectMention('@', 1)).toEqual({ start: 0, query: '' });
    expect(detectMention('@Lâm', 4)).toEqual({ start: 0, query: 'Lâm' });
  });

  it('detects @ after whitespace', () => {
    expect(detectMention('hello @Lâm', 10)).toEqual({ start: 6, query: 'Lâm' });
    expect(detectMention('a\n@ch', 5)).toEqual({ start: 2, query: 'ch' });
  });

  it('does NOT trigger inside a word or email', () => {
    expect(detectMention('a@b', 3)).toBeNull();
    expect(detectMention('mail me at foo@bar.com', 22)).toBeNull();
  });

  it('does not cross line breaks (mention is per-line)', () => {
    expect(detectMention('@Lâm\nsecond', 11)).toBeNull();
  });

  it('uses the @ closest to the caret', () => {
    expect(detectMention('@a @b', 5)).toEqual({ start: 3, query: 'b' });
  });

  it('allows spaces inside the query (multi-word names)', () => {
    expect(detectMention('@Lâm Tuyệt', 10)).toEqual({ start: 0, query: 'Lâm Tuyệt' });
  });

  it('returns null when the caret is before/at the @', () => {
    expect(detectMention('@abc', 0)).toBeNull();
  });

  it('caps runaway queries (abandoned @ far behind the caret)', () => {
    const long = '@' + 'x'.repeat(60);
    expect(detectMention(long, long.length)).toBeNull();
  });
});

describe('rankCandidates', () => {
  it('ranks startsWith above contains', () => {
    const list = [cand('Hồ Lâm'), cand('Lâm Tuyệt'), cand('Other')];
    const ranked = rankCandidates(list, 'lâm');
    expect(ranked.map((c) => c.label)).toEqual(['Lâm Tuyệt', 'Hồ Lâm']);
  });

  it('is case-insensitive and drops non-matches', () => {
    const ranked = rankCandidates([cand('Alpha'), cand('beta')], 'ALP');
    expect(ranked.map((c) => c.label)).toEqual(['Alpha']);
  });

  it('caps at MENTION_VISIBLE_CAP', () => {
    const list = Array.from({ length: 20 }, (_, i) => cand(`Book ${i}`, String(i)));
    expect(rankCandidates(list, '')).toHaveLength(MENTION_VISIBLE_CAP);
    expect(rankCandidates(list, 'book')).toHaveLength(MENTION_VISIBLE_CAP);
  });

  it('returns the first candidates for an empty query', () => {
    const list = [cand('A'), cand('B')];
    expect(rankCandidates(list, '')).toEqual(list);
  });
});

describe('removeMentionText', () => {
  it('removes the @query from the value and places the caret at the @ position', () => {
    expect(removeMentionText('hello @Lâm world', 6, 10)).toEqual({
      value: 'hello  world',
      caret: 6,
    });
  });

  it('handles a mention at the end of input', () => {
    expect(removeMentionText('ask @ch', 4, 7)).toEqual({ value: 'ask ', caret: 4 });
  });
});

describe('buildMentionCandidates', () => {
  it('flattens books/chapters/entities preserving the ContextItem attach shape', () => {
    const books = [{ book_id: 'b1', title: 'Book One' }] as never;
    const chapters = [
      { chapter_id: 'c1', book_id: 'b1', title: '', original_filename: 'ch1.txt', bookTitle: 'Book One' },
    ] as never;
    const entities = [
      { entity_id: 'e1', book_id: 'b1', display_name: 'Lâm', kind: { name: 'Character', color: '#f00' } },
    ] as never;
    const out = buildMentionCandidates(books, chapters, entities, '(untitled)');
    expect(out).toEqual([
      { id: 'b1', type: 'book', label: 'Book One' },
      { id: 'c1', type: 'chapter', label: 'ch1.txt', detail: 'Book One', bookId: 'b1', chapterId: 'c1' },
      { id: 'e1', type: 'glossary', label: 'Lâm', detail: 'Character', bookId: 'b1', kindColor: '#f00' },
    ]);
  });

  it('falls back to the untitled label', () => {
    const chapters = [{ chapter_id: 'c1', book_id: 'b1', title: '', original_filename: '', bookTitle: 'B' }] as never;
    const out = buildMentionCandidates([], chapters, [], '(untitled)');
    expect(out[0].label).toBe('(untitled)');
  });
});
