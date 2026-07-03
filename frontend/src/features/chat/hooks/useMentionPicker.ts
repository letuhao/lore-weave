import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Book } from '@/features/books/api';
import type { ContextItem } from '../context/types';
import {
  useContextCandidates,
  type ChapterCandidate,
  type EntityCandidate,
} from './useContextCandidates';

// ── Pure logic (exported for tests) ──────────────────────────────────────────

/** A candidate is a ContextItem; `detail` carries the secondary line (book / kind name). */
export type MentionCandidate = ContextItem;

export interface MentionState {
  /** Index of the `@` character in the input value */
  start: number;
  /** Text between the `@` and the caret */
  query: string;
}

const MAX_QUERY_LENGTH = 50;
export const MENTION_VISIBLE_CAP = 8;

/**
 * Detect an active @-mention at the caret. The `@` must be at the start of the
 * input or preceded by whitespace (never inside a word or an email), on the
 * same line as the caret.
 */
export function detectMention(value: string, caret: number): MentionState | null {
  for (let i = caret - 1; i >= 0; i--) {
    const ch = value[i];
    if (ch === '\n' || ch === '\r') return null;
    if (ch === '@') {
      if (i > 0 && !/\s/.test(value[i - 1])) return null; // inside a word / email
      const query = value.slice(i + 1, caret);
      if (query.length > MAX_QUERY_LENGTH) return null;
      return { start: i, query };
    }
  }
  return null;
}

/** Rank candidates for a query: name startsWith beats contains; cap the visible list. */
export function rankCandidates(
  candidates: MentionCandidate[],
  query: string,
  cap = MENTION_VISIBLE_CAP,
): MentionCandidate[] {
  const q = query.trim().toLowerCase();
  if (!q) return candidates.slice(0, cap);
  const starts: MentionCandidate[] = [];
  const contains: MentionCandidate[] = [];
  for (const c of candidates) {
    const label = c.label.toLowerCase();
    if (label.startsWith(q)) starts.push(c);
    else if (label.includes(q)) contains.push(c);
  }
  return [...starts, ...contains].slice(0, cap);
}

/** Remove the `@query` text ([start, end)) from the value; caret lands where the `@` was. */
export function removeMentionText(
  value: string,
  start: number,
  end: number,
): { value: string; caret: number } {
  return { value: value.slice(0, start) + value.slice(end), caret: start };
}

/** Flatten books/chapters/entities into a single mention candidate list. */
export function buildMentionCandidates(
  books: Book[],
  chapters: ChapterCandidate[],
  entities: EntityCandidate[],
  untitledLabel: string,
): MentionCandidate[] {
  return [
    ...books.map((b) => ({ id: b.book_id, type: 'book' as const, label: b.title })),
    ...chapters.map((ch) => ({
      id: ch.chapter_id,
      type: 'chapter' as const,
      label: ch.title || ch.original_filename || untitledLabel,
      detail: ch.bookTitle,
      bookId: ch.book_id,
      chapterId: ch.chapter_id,
    })),
    ...entities.map((e) => ({
      id: e.entity_id,
      type: 'glossary' as const,
      label: e.display_name || untitledLabel,
      detail: e.kind.name,
      bookId: e.book_id,
      kindColor: e.kind.color,
    })),
  ];
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export interface UseMentionPickerArgs {
  /** Current input value (owned by the parent input state) */
  value: string;
  /** Attach seam — same handler the ContextPicker uses */
  onAttach: (item: ContextItem) => void;
  /** Called with the input value after the `@query` text is removed on attach */
  onValueChange: (next: string) => void;
  /** Optional textarea ref for caret/focus restoration after attach */
  textareaRef?: React.RefObject<HTMLTextAreaElement | null>;
}

/**
 * Inline @-mention context attach. Owns trigger detection, candidate loading
 * (lazy — armed on first `@`), filtering/ranking, keyboard selection, and the
 * attach action (attach + strip the `@query` from the input).
 */
export function useMentionPicker({ value, onAttach, onValueChange, textareaRef }: UseMentionPickerArgs) {
  const { t } = useTranslation('chat');
  const [mention, setMention] = useState<MentionState | null>(null);
  /** `@` start index the user dismissed with Esc — stay closed for that token */
  const [dismissedStart, setDismissedStart] = useState<number | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  /** Sticky: becomes true on the first `@` trigger and starts candidate fetching */
  const [armed, setArmed] = useState(false);
  const caretRef = useRef(0);

  const { books, chapters, entities } = useContextCandidates({
    enabled: armed,
    glossaryAllBooks: true,
  });

  const candidates = useMemo(
    () => buildMentionCandidates(books, chapters, entities, t('context.untitled')),
    [books, chapters, entities, t],
  );

  const filtered = useMemo(
    () => (mention ? rankCandidates(candidates, mention.query) : []),
    [candidates, mention],
  );

  const open = mention !== null && mention.start !== dismissedStart && filtered.length > 0;

  /** Wire to the textarea's onChange AND onSelect (caret moves close/open the popover). */
  function syncFromInput(el: { value: string; selectionStart: number | null }) {
    const caret = el.selectionStart ?? el.value.length;
    caretRef.current = caret;
    const next = detectMention(el.value, caret);
    if (next && !armed) setArmed(true);
    if (next === null || (dismissedStart !== null && dismissedStart !== next.start)) {
      setDismissedStart(null);
    }
    if (next?.query !== mention?.query || next?.start !== mention?.start) setSelectedIndex(0);
    setMention(next);
  }

  /** Attach a candidate and strip the `@query` text from the input. */
  function attachCandidate(candidate: MentionCandidate) {
    if (!mention) return;
    onAttach(candidate);
    const next = removeMentionText(value, mention.start, Math.max(caretRef.current, mention.start));
    onValueChange(next.value);
    setMention(null);
    setDismissedStart(null);
    setSelectedIndex(0);
    const el = textareaRef?.current;
    if (el) {
      requestAnimationFrame(() => {
        el.focus();
        el.setSelectionRange(next.caret, next.caret);
      });
    }
  }

  /** Returns true when the key was consumed by the popover (caller must not send). */
  function handleKeyDown(e: React.KeyboardEvent): boolean {
    if (!open || !mention) return false;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
      return true;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
      return true;
    }
    if ((e.key === 'Enter' && !e.shiftKey) || e.key === 'Tab') {
      e.preventDefault();
      const candidate = filtered[selectedIndex] ?? filtered[0];
      if (candidate) attachCandidate(candidate);
      return true;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      setDismissedStart(mention.start);
      return true;
    }
    return false;
  }

  return { open, filtered, selectedIndex, setSelectedIndex, syncFromInput, handleKeyDown, attachCandidate };
}
