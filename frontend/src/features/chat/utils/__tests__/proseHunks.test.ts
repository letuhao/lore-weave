import { describe, expect, it } from 'vitest';
import { splitSentences, buildHunks, reconstruct } from '../proseHunks';

describe('splitSentences', () => {
  it('splits Latin prose on sentence boundaries', () => {
    expect(splitSentences('Hi there. Bye now.')).toEqual(['Hi there.', 'Bye now.']);
  });

  it('keeps closing quotes with the sentence', () => {
    expect(splitSentences('"Run!" she said. He froze.')).toEqual(['"Run!" she said.', 'He froze.']);
  });

  it('splits CJK prose with no trailing space', () => {
    expect(splitSentences('你好。世界！再见？')).toEqual(['你好。', '世界！', '再见？']);
  });

  it('A7 (ML-3): does not split a Vietnamese lowercase-diacritic dialogue tag', () => {
    // `ông` starts with `ô` (not [a-z]); the old ASCII guard split it wrongly.
    // \p{Ll} guards any lowercase continuation, so the tag stays one unit.
    expect(splitSentences('«Chạy!» ông nói. Hắn đứng im.')).toEqual([
      '«Chạy!» ông nói.',
      'Hắn đứng im.',
    ]);
  });

  it('A7: still splits when a Vietnamese sentence genuinely ends (capitalized next)', () => {
    expect(splitSentences('Nó chạy đi. Hắn cười.')).toEqual(['Nó chạy đi.', 'Hắn cười.']);
  });

  it('A7: \\p{Ll} is script-universal — guards a Cyrillic lowercase dialogue tag too', () => {
    // "«Бежать!» она сказала." — `она` is Cyrillic lowercase (not [a-z]); the
    // fix guards every cased script, not just Vietnamese.
    expect(splitSentences('«Бежать!» она сказала. Он замер.')).toEqual([
      '«Бежать!» она сказала.',
      'Он замер.',
    ]);
  });

  it('splits on paragraph newlines', () => {
    expect(splitSentences('First para\n\nSecond para')).toEqual(['First para', 'Second para']);
  });

  it('a single sentence is one unit', () => {
    expect(splitSentences('Just one line here')).toEqual(['Just one line here']);
  });

  it('drops empty units and trims', () => {
    expect(splitSentences('  A.   B.  ')).toEqual(['A.', 'B.']);
  });
});

const texts = (units: { text: string }[]) => units.map((u) => u.text);

describe('buildHunks', () => {
  it('an unchanged middle sentence separates two hunks', () => {
    // old: A B C  ·  new: X B Y  → change[A→X], ctx[B], change[C→Y]
    const m = buildHunks('A. B. C.', 'X. B. Y.');
    expect(m.hunks).toHaveLength(2);
    expect(texts(m.hunks[0].oldUnits)).toEqual(['A.']);
    expect(texts(m.hunks[0].newUnits)).toEqual(['X.']);
    expect(texts(m.hunks[1].oldUnits)).toEqual(['C.']);
    expect(texts(m.hunks[1].newUnits)).toEqual(['Y.']);
    // segments interleave: hunk, ctx(B), hunk
    expect(m.segments.map((s) => s.kind)).toEqual(['hunk', 'ctx', 'hunk']);
  });

  it('a pure insertion is a hunk with empty oldUnits', () => {
    const m = buildHunks('A. C.', 'A. B. C.');
    expect(m.hunks).toHaveLength(1);
    expect(texts(m.hunks[0].oldUnits)).toEqual([]);
    expect(texts(m.hunks[0].newUnits)).toEqual(['B.']);
  });

  it('a pure deletion is a hunk with empty newUnits', () => {
    const m = buildHunks('A. B. C.', 'A. C.');
    expect(m.hunks).toHaveLength(1);
    expect(texts(m.hunks[0].oldUnits)).toEqual(['B.']);
    expect(texts(m.hunks[0].newUnits)).toEqual([]);
  });

  it('identical text yields no hunks', () => {
    const m = buildHunks('A. B.', 'A. B.');
    expect(m.hunks).toHaveLength(0);
  });
});

describe('reconstruct', () => {
  const m = buildHunks('A. B. C.', 'X. B. Y.');

  it('accept all → the full new text (space-joined)', () => {
    const out = reconstruct(m, new Set([0, 1]));
    expect(out).toBe('X. B. Y.');
  });

  it('reject all → the original old text (space-joined)', () => {
    const out = reconstruct(m, new Set());
    expect(out).toBe('A. B. C.');
  });

  it('mixed: accept first hunk, reject second', () => {
    const out = reconstruct(m, new Set([0]));
    expect(out).toBe('X. B. C.');
  });

  it('rejecting a pure-insertion hunk drops the added sentence', () => {
    const ins = buildHunks('A. C.', 'A. B. C.');
    expect(reconstruct(ins, new Set())).toBe('A. C.');
    expect(reconstruct(ins, new Set([0]))).toBe('A. B. C.');
  });

  it('preserves paragraph breaks in the NEW proposal on a partial accept', () => {
    // old is one space-joined span (as ProseMirror hands it); new has a paragraph
    // break. Accepting the first hunk and rejecting the second must NOT flatten
    // the surviving newline into a single space.
    const m = buildHunks('A. B. C.', 'X.\n\nB. Y.');
    // hunk0: A→X, ctx: B, hunk1: C→Y
    const out = reconstruct(m, new Set([0])); // accept X, reject Y (keep C)
    expect(out).toBe('X.\n\nB. C.');
  });
});
