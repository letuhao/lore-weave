import { describe, it, expect } from 'vitest';
import { wordDiff, alignSideBySide } from '../wordDiff';
import type { DiffLine } from '../../types';

describe('wordDiff', () => {
  it('marks only the changed words, leaves common words unchanged', () => {
    const [left, right] = wordDiff('the quick brown fox', 'the slow brown fox');
    // "the", "brown", "fox" (and the spaces) are common; "quick"/"slow" differ.
    const leftChanged = left.filter((t) => t.changed).map((t) => t.text);
    const rightChanged = right.filter((t) => t.changed).map((t) => t.text);
    expect(leftChanged).toContain('quick');
    expect(rightChanged).toContain('slow');
    expect(leftChanged).not.toContain('brown');
    expect(rightChanged).not.toContain('fox');
  });

  it('splits CJK per-character so the word highlight is granular (no spaces)', () => {
    // /review-impl MED#2: CJK has no spaces — only the changed character should
    // highlight, not the whole line.
    const [left, right] = wordDiff('封神演義', '封神演功');
    expect(left.map((t) => t.text).join('')).toBe('封神演義');
    expect(right.map((t) => t.text).join('')).toBe('封神演功');
    expect(left.filter((t) => t.changed).map((t) => t.text)).toEqual(['義']);
    expect(right.filter((t) => t.changed).map((t) => t.text)).toEqual(['功']);
    // shared prefix chars are unchanged
    expect(left.filter((t) => !t.changed).map((t) => t.text)).toEqual(['封', '神', '演']);
  });

  it('reconstructs each side losslessly (incl whitespace)', () => {
    const a = 'a  b   c';
    const b = 'a b c d';
    const [left, right] = wordDiff(a, b);
    expect(left.map((t) => t.text).join('')).toBe(a);
    expect(right.map((t) => t.text).join('')).toBe(b);
  });
});

describe('alignSideBySide', () => {
  it('equal lines occupy one row on both sides', () => {
    const diff: DiffLine[] = [
      { op: 'equal', text: 'intro' },
      { op: 'equal', text: 'outro' },
    ];
    const rows = alignSideBySide(diff);
    expect(rows).toHaveLength(2);
    expect(rows.every((r) => r.type === 'equal' && r.left && r.right)).toBe(true);
  });

  it('pairs a delete with the following insert into a change row with word tokens', () => {
    const diff: DiffLine[] = [
      { op: 'equal', text: 'intro' },
      { op: 'delete', text: 'old middle' },
      { op: 'insert', text: 'new middle' },
      { op: 'equal', text: 'outro' },
    ];
    const rows = alignSideBySide(diff);
    const change = rows.find((r) => r.type === 'change');
    expect(change).toBeTruthy();
    expect(change!.left?.words).toBeTruthy();
    expect(change!.right?.words).toBeTruthy();
    // "middle" is common between the two → not all tokens are changed
    expect(change!.left!.words!.some((w) => !w.changed)).toBe(true);
  });

  it('unpaired deletes/inserts become one-sided rows', () => {
    const diff: DiffLine[] = [
      { op: 'delete', text: 'gone1' },
      { op: 'delete', text: 'gone2' },
      { op: 'insert', text: 'added' },
    ];
    const rows = alignSideBySide(diff);
    // 2 deletes paired with 1 insert → 1 change row + 1 delete-only row
    expect(rows.filter((r) => r.type === 'change')).toHaveLength(1);
    expect(rows.filter((r) => r.type === 'delete')).toHaveLength(1);
    const del = rows.find((r) => r.type === 'delete');
    expect(del?.left && !del?.right).toBe(true);
  });
});
