import type { Book, Chapter } from '@/features/books/api';

export type TrashType = 'book' | 'chapter' | 'glossary' | 'chat';

export interface TrashItem {
  id: string;
  type: TrashType;
  title: string;
  badge: string;
  context?: string;
  deletedAt: string;
  iconColor?: string;
  bookId?: string;
  raw: any;
}

export function bookToTrashItem(book: Book): TrashItem {
  return {
    id: book.book_id,
    type: 'book',
    title: book.title,
    badge: `${book.chapter_count ?? 0} chapter${book.chapter_count !== 1 ? 's' : ''}`,
    context: book.original_language ?? undefined,
    deletedAt: book.updated_at ?? book.created_at ?? new Date().toISOString(),
    raw: book,
  };
}

export function chapterToTrashItem(chapter: Chapter, bookTitle?: string): TrashItem {
  const words = Math.round((chapter.byte_size ?? 0) / 5);
  const wordLabel = words > 0 ? `${words.toLocaleString()} words` : 'empty';
  return {
    id: chapter.chapter_id,
    type: 'chapter',
    title: chapter.title || '(untitled)',
    badge: wordLabel,
    context: bookTitle ? `from ${bookTitle}` : chapter.original_language ?? undefined,
    deletedAt: chapter.trashed_at ?? chapter.updated_at ?? chapter.created_at ?? new Date().toISOString(),
    bookId: chapter.book_id,
    raw: chapter,
  };
}

export interface EntityTrashItem {
  entity_id: string;
  book_id: string;
  display_name: string;
  kind_name: string;
  kind_color: string;
  deleted_at: string;
}

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

export interface ChatSession {
  session_id: string;
  title: string;
  message_count: number;
  status: string;
  model_source?: string;
  updated_at: string;
}

export function chatSessionToTrashItem(session: ChatSession): TrashItem {
  return {
    id: session.session_id,
    type: 'chat',
    title: session.title || '(untitled)',
    badge: `${session.message_count} message${session.message_count !== 1 ? 's' : ''}`,
    context: session.model_source === 'user_model' ? 'My Model' : 'Platform',
    deletedAt: session.updated_at,
    raw: session,
  };
}
