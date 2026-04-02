// ── Universal Trash Item ──────────────────────────────────────────────────────
// Normalized shape for rendering TrashCard across all trash types.

import type { Book } from '@/features/books/api';
import type { EntityTrashItem } from '@/features/glossary/types';

export type TrashType = 'book' | 'glossary';

export interface TrashItem {
  id: string;
  type: TrashType;
  title: string;
  badge: string;
  context?: string;
  deletedAt: string;
  /** Kind dot color (glossary entities only) */
  iconColor?: string;
  /** Original API object for restore/purge calls */
  raw: Book | EntityTrashItem;
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
