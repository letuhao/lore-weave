import { describe, it, expect } from 'vitest';
import { staleChapterIds } from '../TranslationTab';
import type { BookCoverageResponse, CoverageCell } from '@/features/translation/api';

function cell(over: Partial<CoverageCell> = {}): CoverageCell {
  return {
    has_active: true,
    active_version_num: 1,
    latest_version_num: 1,
    latest_status: 'completed',
    version_count: 1,
    is_glossary_stale: false,
    ...over,
  };
}

const cov: BookCoverageResponse = {
  book_id: 'b',
  known_languages: ['vi', 'en'],
  coverage: [
    { chapter_id: 'c1', languages: { vi: cell({ is_glossary_stale: true }), en: cell() } },
    { chapter_id: 'c2', languages: { vi: cell(), en: cell({ is_glossary_stale: true }) } },
    { chapter_id: 'c3', languages: { vi: cell(), en: cell() } },
  ],
};

describe('staleChapterIds (M6b-2)', () => {
  it('collects chapters stale in any visible language + counts stale cells', () => {
    const { ids, cells } = staleChapterIds(cov, ['vi', 'en']);
    expect([...ids].sort()).toEqual(['c1', 'c2']);
    expect(cells).toBe(2);
  });

  it('respects the visible-language filter (en-stale chapter excluded when only vi visible)', () => {
    const { ids, cells } = staleChapterIds(cov, ['vi']);
    expect([...ids]).toEqual(['c1']); // c2 is stale in en only
    expect(cells).toBe(1);
  });

  it('returns empty when nothing is stale', () => {
    const clean: BookCoverageResponse = {
      ...cov,
      coverage: [{ chapter_id: 'c3', languages: { vi: cell(), en: cell() } }],
    };
    const { ids, cells } = staleChapterIds(clean, ['vi', 'en']);
    expect(ids.size).toBe(0);
    expect(cells).toBe(0);
  });

  it('ignores a stale cell whose language is not visible', () => {
    const { cells } = staleChapterIds(cov, []);
    expect(cells).toBe(0);
  });
});
