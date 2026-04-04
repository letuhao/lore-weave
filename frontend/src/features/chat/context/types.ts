// ── Chat Context Types ────────────────────────────────────────────────────────

export type ContextType = 'book' | 'chapter' | 'glossary';

export interface ContextItem {
  id: string;
  type: ContextType;
  label: string;
  /** Secondary info shown in pill tooltip */
  detail?: string;
  /** Book ID (for chapter/glossary items) */
  bookId?: string;
  /** Chapter ID (for getDraft calls) */
  chapterId?: string;
  /** Glossary kind color */
  kindColor?: string;
}

/** Marker prefix injected into message content to identify context */
export const CONTEXT_MARKER_START = '---CONTEXT---\n';
export const CONTEXT_MARKER_END = '\n---END CONTEXT---\n\n';

/** Check if a message has context attached */
export function hasContext(content: string): boolean {
  return content.startsWith(CONTEXT_MARKER_START);
}

/** Extract the user's actual message (without context block) */
export function extractUserMessage(content: string): string {
  if (!hasContext(content)) return content;
  const endIdx = content.indexOf(CONTEXT_MARKER_END);
  if (endIdx === -1) return content;
  return content.slice(endIdx + CONTEXT_MARKER_END.length);
}

/** Extract context summary labels from a message */
export function extractContextLabels(content: string): string[] {
  if (!hasContext(content)) return [];
  const endIdx = content.indexOf(CONTEXT_MARKER_END);
  if (endIdx === -1) return [];
  const block = content.slice(CONTEXT_MARKER_START.length, endIdx);
  // Extract [Type: Label] patterns from first line
  const firstLine = block.split('\n')[0] ?? '';
  const matches = firstLine.match(/\[(\w+): ([^\]]+)\]/g);
  return matches ?? [];
}
