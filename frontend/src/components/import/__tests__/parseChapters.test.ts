import { describe, it, expect } from 'vitest';
import { naturalCompare, parseChapterTitle, filterTxtFiles } from '../parseChapters';

describe('naturalCompare', () => {
  it('orders by leading numeric prefix, not lexicographically', () => {
    const names = ['0010-x.txt', '0002-y.txt', '0001-z.txt', '0100-w.txt'];
    expect([...names].sort(naturalCompare)).toEqual([
      '0001-z.txt', '0002-y.txt', '0010-x.txt', '0100-w.txt',
    ]);
  });

  it('handles non-zero-padded numbers numerically', () => {
    const names = ['10.txt', '2.txt', '1.txt'];
    expect([...names].sort(naturalCompare)).toEqual(['1.txt', '2.txt', '10.txt']);
  });

  it('falls back to locale compare when no numeric prefix', () => {
    expect(naturalCompare('beta.txt', 'alpha.txt')).toBeGreaterThan(0);
  });
});

describe('parseChapterTitle', () => {
  it('extracts the title from a CJK chapter header', () => {
    expect(parseChapterTitle('0001-八百年后.txt', '第1章 八百年后\n\nbody')).toBe('八百年后');
  });

  it('handles spaced headers and other markers', () => {
    expect(parseChapterTitle('x.txt', '第 12 回   標題  \n...')).toBe('標題');
  });

  it('uses the first non-empty content line when no header', () => {
    expect(parseChapterTitle('x.txt', '\n\nJust a line\nmore')).toBe('Just a line');
  });

  it('falls back to filename-after-dash when content is empty', () => {
    expect(parseChapterTitle('0007-天心剑法.txt', '')).toBe('天心剑法');
  });
});

describe('filterTxtFiles', () => {
  it('keeps only .txt (folder picks include everything)', () => {
    const f = (name: string) => new File(['x'], name, { type: 'text/plain' });
    const kept = filterTxtFiles([f('a.txt'), f('b.docx'), f('c.TXT'), f('d.jpg')]);
    expect(kept.map((x) => x.name)).toEqual(['a.txt', 'c.TXT']);
  });
});
