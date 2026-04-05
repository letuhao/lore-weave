import type { JSONContent } from '@tiptap/react';

/** Recursively extract plain text from a Tiptap node */
export function extractText(node: JSONContent): string {
  if (node.type === 'text') return node.text || '';
  if (node.type === 'hardBreak') return '\n';
  // Atom nodes with no children — extract meaningful text from attrs
  if (node.type === 'imageBlock') return (node.attrs?.alt as string) || '';
  if (node.type === 'videoBlock') return (node.attrs?.alt as string) || (node.attrs?.caption as string) || '';
  if (!node.content) return '';
  return node.content
    .map(child => extractText(child))
    .join(node.type === 'listItem' ? '\n' : '');
}

/** Add _text snapshot to each top-level block for the chapter_blocks trigger.
 *  Also strips transient attrs (_mode) that shouldn't be persisted. */
export function addTextSnapshots(doc: JSONContent): JSONContent {
  if (!doc.content) return doc;
  return {
    ...doc,
    content: doc.content.map(block => {
      const cleaned = { ...block, _text: extractText(block) };
      if (cleaned.attrs) {
        const { _mode, ...rest } = cleaned.attrs as any;
        cleaned.attrs = rest;
      }
      return cleaned;
    }),
  };
}
