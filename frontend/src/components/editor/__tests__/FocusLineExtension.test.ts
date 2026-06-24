import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import { afterEach, describe, expect, it } from 'vitest';
import { FocusLineExtension } from '../FocusLineExtension';

// Locks the load-bearing decoration logic (the part that broke once during the
// T5.1 smoke: a foreign class on a PM-managed <p> is stripped on re-render, so the
// `.focusline` mark MUST be a PM node Decoration). Headless editor — no React.

let editor: Editor | null = null;
afterEach(() => { editor?.destroy(); editor = null; });

function mk(content: string): Editor {
  editor = new Editor({
    element: document.createElement('div'),
    extensions: [StarterKit, FocusLineExtension],
    content,
  });
  return editor;
}

const focuslines = (e: Editor) =>
  [...e.view.dom.querySelectorAll('.focusline')].map((el) => el.textContent);

describe('FocusLineExtension (T5.1)', () => {
  it('marks exactly the top-level block containing the collapsed caret', () => {
    const e = mk('<p>first</p><p>second</p><p>third</p>');
    e.commands.setTextSelection(2); // inside the 1st paragraph
    expect(focuslines(e)).toEqual(['first']);
  });

  it('moves the mark when the caret moves to another block', () => {
    const e = mk('<p>alpha</p><p>beta</p>');
    e.commands.setTextSelection(2);
    expect(focuslines(e)).toEqual(['alpha']);
    // jump the caret into the 2nd paragraph (end of doc)
    e.commands.focus('end');
    expect(focuslines(e)).toEqual(['beta']);
  });

  it('marks NO block when the selection spans multiple blocks', () => {
    const e = mk('<p>aaa</p><p>bbb</p>');
    e.commands.setTextSelection({ from: 2, to: 7 }); // across the boundary
    expect(focuslines(e)).toEqual([]);
  });

  it('applies the mark as a ProseMirror decoration, not a persisted attribute', () => {
    // the decoration must NOT serialize into the document JSON (it's view-only)
    const e = mk('<p>hello</p>');
    e.commands.setTextSelection(2);
    expect(focuslines(e)).toEqual(['hello']);
    expect(JSON.stringify(e.getJSON())).not.toContain('focusline');
  });
});
