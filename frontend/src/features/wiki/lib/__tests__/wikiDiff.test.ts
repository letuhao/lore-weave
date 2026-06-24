import { describe, it, expect } from 'vitest';
import { asAiRegenEnvelope, tiptapToLines, diffLines } from '../wikiDiff';

const doc = (lines: string[]) => ({
  type: 'doc',
  content: lines.map((l) => ({ type: 'paragraph', content: [{ type: 'text', text: l }] })),
});

describe('asAiRegenEnvelope', () => {
  it('detects the AI-regen envelope (body_json + generation_status)', () => {
    expect(
      asAiRegenEnvelope({ body_json: { type: 'doc' }, generation_status: 'generated' }),
    ).not.toBeNull();
  });
  it('rejects a plain field diff, a body-only object, and null', () => {
    expect(asAiRegenEnvelope({ before: 'x', after: 'y' })).toBeNull();
    expect(asAiRegenEnvelope({ body_json: { type: 'doc' } })).toBeNull(); // no status
    expect(asAiRegenEnvelope(null)).toBeNull();
  });
});

describe('tiptapToLines', () => {
  it('emits one trimmed line per top-level block, dropping empties', () => {
    expect(tiptapToLines(doc(['a', '  ', 'b']))).toEqual(['a', 'b']);
  });
  it('expands list items into separate lines', () => {
    const d = {
      type: 'doc',
      content: [
        {
          type: 'bulletList',
          content: [
            { type: 'listItem', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'i1' }] }] },
            { type: 'listItem', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'i2' }] }] },
          ],
        },
      ],
    };
    expect(tiptapToLines(d)).toEqual(['i1', 'i2']);
  });
  it('returns [] for non-doc input', () => {
    expect(tiptapToLines(null)).toEqual([]);
    expect(tiptapToLines({})).toEqual([]);
  });
});

describe('diffLines', () => {
  it('marks unchanged / removed / added', () => {
    expect(diffLines(['keep', 'old'], ['keep', 'new'])).toEqual([
      { type: 'ctx', text: 'keep' },
      { type: 'del', text: 'old' },
      { type: 'add', text: 'new' },
    ]);
  });
  it('all added when old is empty, all removed when new is empty', () => {
    expect(diffLines([], ['a', 'b'])).toEqual([
      { type: 'add', text: 'a' },
      { type: 'add', text: 'b' },
    ]);
    expect(diffLines(['a'], [])).toEqual([{ type: 'del', text: 'a' }]);
  });
  it('identical inputs are all context', () => {
    expect(diffLines(['x', 'y'], ['x', 'y'])).toEqual([
      { type: 'ctx', text: 'x' },
      { type: 'ctx', text: 'y' },
    ]);
  });
});
