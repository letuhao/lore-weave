import { describe, it, expect } from 'vitest';
import { buildContextBlock, formatChapter, tiptapDocToText } from '../formatContext';
import type { ContextItem } from '../types';

// Regression: the chapter context block must never render "[object Object]".
// Root cause (C5-era): resolveAndSend passed raw Tiptap JSON (an object) as the
// chapter body; formatChapter string-concatenated it. Fix: use the server's
// text_content, and coerce any object body via tiptapDocToText.

const DOC = {
  type: 'doc',
  content: [
    { type: 'paragraph', content: [{ type: 'text', text: 'The rain fell over the city.' }] },
    { type: 'paragraph', content: [{ type: 'text', text: 'Neon blurred in the puddles.' }] },
  ],
};

describe('tiptapDocToText', () => {
  it('extracts plain text from a Tiptap doc, blocks separated by blank lines', () => {
    expect(tiptapDocToText(DOC)).toBe('The rain fell over the city.\n\nNeon blurred in the puddles.');
  });

  it('returns empty string for non-doc input', () => {
    expect(tiptapDocToText(null)).toBe('');
    expect(tiptapDocToText('already text')).toBe('');
    expect(tiptapDocToText({})).toBe('');
  });
});

describe('formatChapter', () => {
  it('formats a plain-string body', () => {
    expect(formatChapter('Ch.3', 'Hello world')).toBe('Chapter: "Ch.3"\nHello world');
  });

  it('never emits [object Object] when given raw Tiptap JSON', () => {
    const out = formatChapter('Ch.3', DOC);
    expect(out).not.toContain('[object Object]');
    expect(out).toContain('The rain fell over the city.');
  });
});

describe('buildContextBlock — chapter', () => {
  it('renders chapter text, not [object Object]', () => {
    const items: ContextItem[] = [
      { id: 'c1', type: 'chapter', label: 'Ch.3', bookId: 'b1', chapterId: 'c1' },
    ];
    // chapterBody is the resolved plain text (post-fix it comes from text_content)
    const resolved = new Map([['c1', { chapterBody: 'The rain fell.' }]]);
    const block = buildContextBlock(items, resolved);
    expect(block).toContain('[Chapter: Ch.3]');
    expect(block).toContain('The rain fell.');
    expect(block).not.toContain('[object Object]');
  });
});
