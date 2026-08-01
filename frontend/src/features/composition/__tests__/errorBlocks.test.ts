// The OFFSET BRIDGE (atom-edit Phase D, D3d).
//
// These tests exist because a mark computed in the wrong coordinate space is the worst failure
// this feature has: it points at the wrong prose, the co-writer edits a passage the author never
// complained about, and everything reports success. The editor works in ProseMirror positions;
// the server stores offsets into the FLATTENED text. Nothing downstream can detect a mismatch —
// only these assertions can.
import { describe, expect, it } from 'vitest';

import {
  flatSpanToPM, flattenDoc, fingerprintText, resolveBlockRange, selectionToSpan,
} from '../errorBlocks';

/** The exact flattening the backend performs: each top-level block's `_text`, blank-line joined.
 *  Written out independently here rather than importing the helper, so the test would still catch
 *  `flattenDoc` being changed to something else. */
function backendFlatten(blocks: string[]): string {
  return blocks.join('\n\n');
}

const para = (text: string) => ({
  type: 'paragraph', content: [{ type: 'text', text }],
});

/** A minimal stand-in for the bits of the Tiptap editor `selectionToSpan` reads. Real ProseMirror
 *  position arithmetic: each top-level block occupies 1 (open) + len + 1 (close) positions, so
 *  block i's content starts at sum(len_j + 2 for j<i) + 1. */
function fakeEditor(texts: string[], sel: { blockIndex: number; offset: number; length: number }) {
  const starts: number[] = [];
  let pos = 0;
  for (const t of texts) {
    starts.push(pos + 1);
    pos += t.length + 2;
  }
  const from = starts[sel.blockIndex] + sel.offset;
  const to = from + sel.length;
  return {
    getJSON: () => ({ type: 'doc', content: texts.map(para) }),
    state: {
      selection: { from, to },
      doc: {
        resolve: (p: number) => {
          let idx = 0;
          for (let i = 0; i < starts.length; i++) if (p >= starts[i]) idx = i;
          return { depth: 1, index: () => idx, start: () => starts[idx] };
        },
        textBetween: (a: number, b: number) => {
          const t = texts[sel.blockIndex];
          const s = a - starts[sel.blockIndex];
          return t.slice(s, s + (b - a));
        },
      },
    },
  } as never;
}

const REPEATED = [
  'Elara opened the ledger.',
  'She nodded.',
  'The hall went quiet.',
  'She nodded.',
  'Ash drifted past the window.',
];

describe('flattenDoc', () => {
  it('matches the backend flattening byte for byte', () => {
    const doc = { type: 'doc', content: REPEATED.map(para) };
    expect(flattenDoc(doc)).toBe(backendFlatten(REPEATED));
  });

  it('keeps an empty paragraph as an empty block, not a dropped one', () => {
    // The server emits {paragraph, _text:''} for a blank block. Dropping it here would shift
    // every subsequent offset by two characters against the stored text.
    const doc = { type: 'doc', content: [para('A'), { type: 'paragraph' }, para('B')] };
    expect(flattenDoc(doc)).toBe('A\n\n\n\nB');
  });
});

describe('fingerprintText', () => {
  it('is stable for identical text', () => {
    expect(fingerprintText('a\n\nb')).toBe(fingerprintText('a\n\nb'));
  });

  it('CHANGES when the flattening changes — the whole point of storing it', () => {
    expect(fingerprintText('a\n\nb')).not.toBe(fingerprintText('ab'));
  });

  it('distinguishes a transposition (not just a character sum)', () => {
    expect(fingerprintText('ab')).not.toBe(fingerprintText('ba'));
  });
});

describe('selectionToSpan', () => {
  const flat = backendFlatten(REPEATED);

  it('produces offsets that slice the SELECTED text out of the flattened doc', () => {
    const ed = fakeEditor(REPEATED, { blockIndex: 2, offset: 0, length: 20 });
    const span = selectionToSpan(ed)!;
    expect(span.quote).toBe('The hall went quiet.');
    expect(flat.slice(span.start, span.end)).toBe(span.quote);
  });

  it('disambiguates a REPEATED line by block index, not by text search', () => {
    // The core of it. "She nodded." appears twice; marking the SECOND must not produce the
    // first one's offsets, or the co-writer's fix lands on the wrong paragraph.
    const first = selectionToSpan(fakeEditor(REPEATED, { blockIndex: 1, offset: 0, length: 11 }))!;
    const second = selectionToSpan(fakeEditor(REPEATED, { blockIndex: 3, offset: 0, length: 11 }))!;

    expect(first.quote).toBe('She nodded.');
    expect(second.quote).toBe('She nodded.');
    expect(second.start).not.toBe(first.start);
    expect(flat.slice(first.start, first.end)).toBe('She nodded.');
    expect(flat.slice(second.start, second.end)).toBe('She nodded.');
    expect(first.start).toBe(flat.indexOf('She nodded.'));
    expect(second.start).toBe(flat.lastIndexOf('She nodded.'));
  });

  it('handles a mid-block selection', () => {
    const ed = fakeEditor(REPEATED, { blockIndex: 0, offset: 6, length: 4 });
    const span = selectionToSpan(ed)!;
    expect(span.quote).toBe('open');
    expect(flat.slice(span.start, span.end)).toBe('open');
  });

  it('marks the FIRST block correctly (offset 0 is a real answer, not a fallback)', () => {
    const ed = fakeEditor(REPEATED, { blockIndex: 0, offset: 0, length: 5 });
    const span = selectionToSpan(ed)!;
    expect(span.start).toBe(0);
    expect(flat.slice(span.start, span.end)).toBe('Elara');
  });

  it('refuses an empty selection', () => {
    expect(selectionToSpan(fakeEditor(REPEATED, { blockIndex: 1, offset: 0, length: 0 }))).toBeNull();
  });

  it('refuses a whitespace-only selection — it could never be re-anchored', () => {
    expect(selectionToSpan(fakeEditor(['a   b'], { blockIndex: 0, offset: 1, length: 3 }))).toBeNull();
  });

  it('carries the fingerprint of the doc the offsets were computed against', () => {
    const ed = fakeEditor(REPEATED, { blockIndex: 2, offset: 0, length: 20 });
    expect(selectionToSpan(ed)!.fingerprint).toBe(fingerprintText(flat));
  });
});

// ── the INVERSE mapping: stored offsets → a ProseMirror range to decorate ──

/** A stand-in for a PM doc. Block i occupies 1 (open) + len + 1 (close) positions, so its
 *  content starts at sum(len_j + 2 for j<i) + 1 — the real ProseMirror arithmetic. */
function fakeDoc(texts: string[]) {
  const starts: number[] = [];
  let pos = 0;
  for (const t of texts) { starts.push(pos + 1); pos += t.length + 2; }
  return {
    childCount: texts.length,
    child: (i: number) => ({ textContent: texts[i], nodeSize: texts[i].length + 2 }),
    textBetween: (from: number, to: number) => {
      for (let i = 0; i < texts.length; i++) {
        const s = starts[i];
        if (from >= s && from <= s + texts[i].length) {
          return texts[i].slice(from - s, from - s + (to - from));
        }
      }
      return '';
    },
  };
}

function blockRow(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'b1', project_id: 'p', chapter_id: 'c', job_id: null,
    start_offset: 0, end_offset: 5, quote: 'Elara', source_fingerprint: 'f',
    source: 'human', kind: 'continuity', note: 'n', desired: null,
    status: 'open', version: 1, ...over,
  } as never;
}

describe('flatSpanToPM (the inverse of selectionToSpan)', () => {
  it('round-trips: a span produced from a selection maps back to text that slices the same', () => {
    const doc = fakeDoc(REPEATED);
    const flat = backendFlatten(REPEATED);
    const start = flat.lastIndexOf('She nodded.');           // the SECOND occurrence
    const range = flatSpanToPM(doc, start, start + 'She nodded.'.length)!;
    expect(doc.textBetween(range.from, range.to)).toBe('She nodded.');
  });

  it('maps the FIRST and SECOND occurrence of a repeated line to DIFFERENT positions', () => {
    const doc = fakeDoc(REPEATED);
    const flat = backendFlatten(REPEATED);
    const a = flatSpanToPM(doc, flat.indexOf('She nodded.'), flat.indexOf('She nodded.') + 11)!;
    const b = flatSpanToPM(doc, flat.lastIndexOf('She nodded.'), flat.lastIndexOf('She nodded.') + 11)!;
    expect(a.from).not.toBe(b.from);
    expect(doc.textBetween(a.from, a.to)).toBe('She nodded.');
    expect(doc.textBetween(b.from, b.to)).toBe('She nodded.');
  });

  it('refuses a span that runs past a block boundary rather than truncating it', () => {
    // Truncating would highlight LESS than the author marked, silently.
    const doc = fakeDoc(REPEATED);
    expect(flatSpanToPM(doc, 0, 40)).toBeNull();
  });

  it('refuses an out-of-range or inverted span', () => {
    const doc = fakeDoc(REPEATED);
    expect(flatSpanToPM(doc, 99999, 100000)).toBeNull();
    expect(flatSpanToPM(doc, 10, 5)).toBeNull();
  });
});

describe('resolveBlockRange', () => {
  it('resolves a block whose quote still matches', () => {
    const doc = fakeDoc(REPEATED);
    const r = resolveBlockRange(doc, blockRow({ start_offset: 0, end_offset: 5, quote: 'Elara' }));
    expect(r).not.toBeNull();
    expect(doc.textBetween(r!.from, r!.to)).toBe('Elara');
  });

  it('returns null when the offsets no longer hold the quote — never decorates blind', () => {
    // A highlight over the WRONG words is worse than none: it tells the author their complaint
    // is attached to prose it is not attached to.
    const doc = fakeDoc(REPEATED);
    expect(resolveBlockRange(doc, blockRow({ start_offset: 0, end_offset: 5, quote: 'Wrong' }))).toBeNull();
  });
});
