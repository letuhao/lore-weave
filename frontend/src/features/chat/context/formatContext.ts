import type { Book, Chapter } from '@/features/books/api';
import type { GlossaryEntity } from '@/features/glossary/types';
import { CONTEXT_MARKER_START, CONTEXT_MARKER_END, type ContextItem } from './types';

/** Format a Book as context text */
function formatBook(book: Book): string {
  const parts = [`Book: "${book.title}"`];
  if (book.description) parts.push(`Description: ${book.description}`);
  if (book.summary) parts.push(`Summary: ${book.summary}`);
  if (book.original_language) parts.push(`Language: ${book.original_language}`);
  return parts.join('\n');
}

/** Recursively extract plain text from a Tiptap/ProseMirror doc JSON.
 *  Returns '' for anything that isn't a doc. Top-level blocks are joined with
 *  blank lines so paragraphs stay separated. Defensive fallback for when the
 *  server's pre-extracted `text_content` is missing. */
export function tiptapDocToText(doc: unknown): string {
  function nodeText(node: unknown): string {
    if (!node || typeof node !== 'object') return '';
    const n = node as { text?: unknown; content?: unknown };
    if (typeof n.text === 'string') return n.text;
    if (Array.isArray(n.content)) return n.content.map(nodeText).join('');
    return '';
  }
  if (!doc || typeof doc !== 'object') return '';
  const content = (doc as { content?: unknown }).content;
  if (!Array.isArray(content)) return '';
  return content.map(nodeText).join('\n\n').replace(/\n{3,}/g, '\n\n').trim();
}

/** Format a Chapter draft as context text. `body` should be plain text; an
 *  object (raw Tiptap JSON) is coerced via tiptapDocToText so it can never
 *  stringify to "[object Object]" (the C5-era bug). */
function formatChapter(title: string, body: unknown): string {
  const text = typeof body === 'string' ? body : tiptapDocToText(body);
  const header = `Chapter: "${title}"`;
  // Truncate very large chapters to ~8000 chars (~2000 tokens)
  const MAX_CHARS = 8000;
  if (text.length > MAX_CHARS) {
    return `${header}\n${text.slice(0, MAX_CHARS)}\n[... truncated, ${text.length - MAX_CHARS} chars omitted]`;
  }
  return `${header}\n${text}`;
}

/** Format a Glossary entity as context text */
function formatEntity(entity: GlossaryEntity): string {
  const parts = [
    `Entity: "${entity.display_name}" (${entity.kind.name})`,
  ];
  for (const av of entity.attribute_values ?? []) {
    if (av.original_value) {
      parts.push(`  ${av.attribute_def.name}: ${av.original_value}`);
    }
  }
  return parts.join('\n');
}

/** Build the full context block to prepend to user message */
export function buildContextBlock(
  items: ContextItem[],
  resolvedData: Map<string, { book?: Book; chapterBody?: string; entity?: GlossaryEntity }>,
): string {
  if (items.length === 0) return '';

  // Header line with labels: [Book: Title] [Chapter: Ch.3]
  const labels = items.map((it) => `[${capitalize(it.type)}: ${it.label}]`).join(' ');

  // Body: formatted context for each item
  const sections: string[] = [];
  for (const item of items) {
    const data = resolvedData.get(item.id);
    if (!data) continue;

    if (item.type === 'book' && data.book) {
      sections.push(formatBook(data.book));
    } else if (item.type === 'chapter' && data.chapterBody !== undefined) {
      sections.push(formatChapter(item.label, data.chapterBody));
    } else if (item.type === 'glossary' && data.entity) {
      sections.push(formatEntity(data.entity));
    }
  }

  if (sections.length === 0) return '';

  return (
    CONTEXT_MARKER_START +
    labels +
    '\n\n' +
    sections.join('\n\n') +
    CONTEXT_MARKER_END
  );
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export { formatBook, formatChapter, formatEntity };
