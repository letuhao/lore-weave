// ── Universal Trash Item ──────────────────────────────────────────────────────
// Normalized shape for rendering TrashCard across all trash types.

import type { Book, Chapter } from '@/features/books/api';
import type { EntityTrashItem } from '@/features/glossary/types';
import type { ChatSession } from '@/features/chat-v2/types';

export type TrashType = 'book' | 'chapter' | 'glossary' | 'chat';

export interface TrashItem {
  id: string;
  type: TrashType;
  title: string;
  badge: string;
  context?: string;
  deletedAt: string;
  /** Kind dot color (glossary entities only) */
  iconColor?: string;
  /** Book ID needed for chapter restore/purge calls */
  bookId?: string;
  /** Original API object for restore/purge calls */
  raw: Book | Chapter | EntityTrashItem | ChatSession;
}

/** Normalize a trashed Book into a TrashItem */
export function bookToTrashItem(book: Book): TrashItem {
  return {
    id: book.book_id,
    type: 'book',
    title: book.title,
    badge: `${book.chapter_count} chapter${book.chapter_count !== 1 ? 's' : ''}`,
    context: book.original_language ?? undefined,
    deletedAt: book.updated_at ?? book.created_at ?? new Date().toISOString(),
    raw: book,
  };
}

/** Normalize a trashed Chapter into a TrashItem */
export function chapterToTrashItem(chapter: Chapter, bookTitle?: string): TrashItem {
  // Approximate word count from byte_size (avg 5 bytes/word for UTF-8 text)
  const words = Math.round(chapter.byte_size / 5);
  const wordLabel = words > 0 ? `${words.toLocaleString()} words` : 'empty';
  return {
    id: chapter.chapter_id,
    type: 'chapter',
    title: chapter.title || chapter.original_filename || '(untitled)',
    badge: wordLabel,
    context: bookTitle ? `from ${bookTitle}` : chapter.original_language ?? undefined,
    deletedAt: chapter.trashed_at ?? chapter.updated_at ?? chapter.created_at ?? new Date().toISOString(),
    bookId: chapter.book_id,
    raw: chapter,
  };
}

/** Normalize a trashed GlossaryEntity into a TrashItem */
export function glossaryToTrashItem(item: EntityTrashItem, bookTitle?: string): TrashItem {
  return {
    id: item.entity_id,
    type: 'glossary',
    title: item.display_name || '(unnamed)',
    badge: item.kind_name,
    context: bookTitle ? `from ${bookTitle}` : undefined,
    deletedAt: item.deleted_at,
    iconColor: item.kind_color,
    raw: item,
  };
}

/** Normalize an archived ChatSession into a TrashItem */
export function chatSessionToTrashItem(session: ChatSession): TrashItem {
  return {
    id: session.session_id,
    type: 'chat',
    title: session.title,
    badge: `${session.message_count} message${session.message_count !== 1 ? 's' : ''}`,
    context: session.model_source === 'user_model' ? 'My Model' : 'Platform',
    deletedAt: session.updated_at,
    raw: session,
  };
}
