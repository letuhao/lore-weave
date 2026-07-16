import { describe, expect, it } from 'vitest';
import { lineDiff, isUnchanged } from '../lineDiff';

describe('lineDiff', () => {
  it('marks identical text as all-context', () => {
    const rows = lineDiff('a\nb\nc', 'a\nb\nc');
    expect(rows.every((r) => r.type === 'ctx')).toBe(true);
    expect(rows.map((r) => r.text)).toEqual(['a', 'b', 'c']);
  });

  it('marks a changed middle line as del then add, keeping context', () => {
    const rows = lineDiff('a\nOLD\nc', 'a\nNEW\nc');
    expect(rows).toEqual([
      { type: 'ctx', text: 'a' },
      { type: 'del', text: 'OLD' },
      { type: 'add', text: 'NEW' },
      { type: 'ctx', text: 'c' },
    ]);
  });

  it('marks pure additions and pure deletions', () => {
    expect(lineDiff('a', 'a\nb')).toEqual([
      { type: 'ctx', text: 'a' },
      { type: 'add', text: 'b' },
    ]);
    expect(lineDiff('a\nb', 'a')).toEqual([
      { type: 'ctx', text: 'a' },
      { type: 'del', text: 'b' },
    ]);
  });

  it('ignores a trailing newline (no phantom empty row)', () => {
    expect(isUnchanged('a\nb\n', 'a\nb')).toBe(true);
    expect(lineDiff('a\n', 'a').every((r) => r.type === 'ctx')).toBe(true);
  });

  it('isUnchanged distinguishes real changes', () => {
    expect(isUnchanged('a\nb', 'a\nB')).toBe(false);
  });
});
