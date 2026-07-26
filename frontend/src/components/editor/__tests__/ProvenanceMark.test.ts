import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import { afterEach, describe, expect, it } from 'vitest';
import {
  ProvenanceMark,
  applyProvenanceOver,
  reviewProvenanceAt,
  markAllProvenanceReviewed,
  countUnreviewedProvenance,
  setProvenanceVisible,
} from '../ProvenanceMark';

// Headless editor — locks the AI-provenance mark: a span carrying source/status/
// model round-trips through the doc JSON (so it survives save→reload), clicking an
// unreviewed span flips it to reviewed, and "mark all reviewed" clears the underlay.

let editor: Editor | null = null;
afterEach(() => { editor?.destroy(); editor = null; });

function mk(content: string): Editor {
  editor = new Editor({ element: document.createElement('div'), extensions: [StarterKit, ProvenanceMark], content });
  return editor;
}
const spans = (e: Editor) =>
  [...e.view.dom.querySelectorAll('.provenance-mark')].map((el) => ({
    text: el.textContent, status: el.getAttribute('data-status'), source: el.getAttribute('data-source'),
  }));

describe('ProvenanceMark (T5.3)', () => {
  it('is inert when no prose is marked', () => {
    const e = mk('<p>Hand-written prose.</p>');
    expect(spans(e)).toEqual([]);
    expect(countUnreviewedProvenance(e)).toBe(0);
  });

  it('applyProvenanceOver wraps a range as an unreviewed AI span', () => {
    const e = mk('<p>Hello world.</p>');
    applyProvenanceOver(e, 1, 6, { source: 'ai', status: 'unreviewed', model: 'gpt-4o' });
    expect(spans(e)).toEqual([{ text: 'Hello', status: 'unreviewed', source: 'ai' }]);
    expect(countUnreviewedProvenance(e)).toBe(1);
  });

  it('round-trips the mark + its attrs through the document JSON (survives save/reload)', () => {
    const e = mk('<p>Hello world.</p>');
    applyProvenanceOver(e, 1, 6, { source: 'ai', status: 'unreviewed', model: 'gpt-4o' });
    const json = JSON.stringify(e.getJSON());
    expect(json).toContain('provenance');
    expect(json).toContain('unreviewed');
    expect(json).toContain('gpt-4o');
    // and a fresh editor seeded with that JSON renders the span again
    const e2 = new Editor({ element: document.createElement('div'), extensions: [StarterKit, ProvenanceMark], content: e.getJSON() });
    expect(e2.view.dom.querySelectorAll('.provenance-mark').length).toBe(1);
    e2.destroy();
  });

  it('reviewProvenanceAt flips the covering span to reviewed', () => {
    const e = mk('<p>Hello world.</p>');
    applyProvenanceOver(e, 1, 6, { source: 'ai', status: 'unreviewed' });
    expect(reviewProvenanceAt(e, 3)).toBe(true);
    expect(spans(e)).toEqual([{ text: 'Hello', status: 'reviewed', source: 'ai' }]);
    expect(countUnreviewedProvenance(e)).toBe(0);
  });

  it('reviewProvenanceAt is a no-op outside any span and on an already-reviewed span', () => {
    const e = mk('<p>Hello world.</p>');
    applyProvenanceOver(e, 1, 6, { source: 'ai', status: 'unreviewed' });
    expect(reviewProvenanceAt(e, 10)).toBe(false); // "world" is unmarked
    expect(reviewProvenanceAt(e, 3)).toBe(true);    // first click reviews
    expect(reviewProvenanceAt(e, 3)).toBe(false);   // already reviewed → no-op
  });

  it('markAllProvenanceReviewed flips every unreviewed span and returns the count', () => {
    const e = mk('<p>Hello big world.</p>');
    applyProvenanceOver(e, 1, 6, { source: 'ai', status: 'unreviewed' });   // "Hello"
    applyProvenanceOver(e, 11, 16, { source: 'ai', status: 'unreviewed' }); // "world"
    expect(countUnreviewedProvenance(e)).toBe(2);
    expect(markAllProvenanceReviewed(e)).toBe(2);
    expect(countUnreviewedProvenance(e)).toBe(0);
    expect(spans(e).every((s) => s.status === 'reviewed')).toBe(true);
  });

  it('marks EXACTLY the inserted range when applied after an insert (the handle path)', () => {
    // Mirrors TiptapEditor.insertAtCursor: capture `from`, insert, then mark
    // [from, post-insert selection]. Locks that insertContentAt moves the cursor
    // to the end of the inserted text so the mark covers only the new prose.
    const e = mk('<p>AB.</p>');
    const from = 2; // between "A" and "B"
    e.chain().focus().insertContentAt(from, 'NEW').run();
    const to = e.state.selection.from;
    applyProvenanceOver(e, from, to, { source: 'ai', status: 'unreviewed' });
    expect(spans(e)).toEqual([{ text: 'NEW', status: 'unreviewed', source: 'ai' }]);
    // the original "A"/"B" around it are NOT marked (no over-reach)
    expect(e.view.dom.textContent).toBe('ANEWB.');
  });

  it('helpers are inert (never throw) when the provenance mark is absent from the schema', () => {
    const bare = new Editor({ element: document.createElement('div'), extensions: [StarterKit], content: '<p>hi</p>' });
    expect(() => applyProvenanceOver(bare, 1, 3, { status: 'unreviewed' })).not.toThrow();
    expect(reviewProvenanceAt(bare, 2)).toBe(false);
    expect(markAllProvenanceReviewed(bare)).toBe(0);
    expect(countUnreviewedProvenance(bare)).toBe(0);
    bare.destroy();
  });

  it('setProvenanceVisible toggles the underlay-off class on the editor root', () => {
    const e = mk('<p>Hello world.</p>');
    applyProvenanceOver(e, 1, 6, { source: 'ai', status: 'unreviewed' });
    setProvenanceVisible(e, false);
    expect(e.view.dom.classList.contains('provenance-underlay-off')).toBe(true);
    setProvenanceVisible(e, true);
    expect(e.view.dom.classList.contains('provenance-underlay-off')).toBe(false);
  });
});
