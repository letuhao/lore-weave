import { useEffect, useMemo, useState } from 'react';
import { BookOpen, FileText, Search } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Book, type Chapter } from '@/features/books/api';
import { glossaryApi } from '@/features/glossary/api';
import { useEntityKinds } from '@/features/glossary/hooks/useEntityKinds';
import type { GlossaryEntitySummary } from '@/features/glossary/types';
import { cn } from '@/lib/utils';
import type { ContextItem, ContextType } from './types';

type PickerTab = 'book' | 'chapter' | 'glossary';

interface ContextPickerProps {
  attached: ContextItem[];
  onAttach: (item: ContextItem) => void;
  onDetach: (id: string) => void;
  onClose: () => void;
}

export function ContextPicker({ attached, onAttach, onDetach, onClose }: ContextPickerProps) {
  const { accessToken } = useAuth();
  const [tab, setTab] = useState<PickerTab>('book');
  const [search, setSearch] = useState('');

  // ── Data ────────────────────────────────────────────────────────────────

  const [books, setBooks] = useState<Book[]>([]);
  const [chapters, setChapters] = useState<(Chapter & { bookTitle: string })[]>([]);
  const [entities, setEntities] = useState<(GlossaryEntitySummary & { bookTitle: string })[]>([]);
  const { kinds } = useEntityKinds();

  // Glossary filters
  const [glossaryBookId, setGlossaryBookId] = useState('');
  const [glossaryKind, setGlossaryKind] = useState('');

  const attachedIds = useMemo(() => new Set(attached.map((a) => a.id)), [attached]);

  // Fetch books
  useEffect(() => {
    if (!accessToken) return;
    void booksApi.listBooks(accessToken).then((r) => {
      setBooks(r.items);
      if (r.items.length > 0 && !glossaryBookId) {
        setGlossaryBookId(r.items[0].book_id);
      }
    });
  }, [accessToken]);

  // Fetch chapters (all books)
  useEffect(() => {
    if (!accessToken || books.length === 0) return;
    void Promise.all(
      books.map((b) =>
        booksApi
          .listChapters(accessToken, b.book_id, { limit: 100 })
          .then((r) => r.items.map((ch) => ({ ...ch, bookTitle: b.title })))
          .catch(() => []),
      ),
    ).then((results) => setChapters(results.flat()));
  }, [accessToken, books]);

  // Fetch glossary entities (per selected book)
  useEffect(() => {
    if (!accessToken || !glossaryBookId) return;
    const filters: Record<string, string> = {};
    if (glossaryKind) filters.kind_code = glossaryKind;
    void glossaryApi
      .listEntities(
        glossaryBookId,
        {
          kindCodes: glossaryKind ? [glossaryKind] : [],
          status: 'all',
          searchQuery: '',
          limit: 100,
          offset: 0,
        },
        accessToken,
      )
      .then((r) => {
        const bookTitle = books.find((b) => b.book_id === glossaryBookId)?.title ?? '';
        setEntities(r.items.map((e) => ({ ...e, bookTitle })));
      })
      .catch(() => setEntities([]));
  }, [accessToken, glossaryBookId, glossaryKind, books]);

  // ── Filtered items ────────────────────────────────────────────────────────

  const q = search.toLowerCase();

  const filteredBooks = useMemo(
    () => books.filter((b) => !q || b.title.toLowerCase().includes(q)),
    [books, q],
  );

  const filteredChapters = useMemo(
    () =>
      chapters.filter(
        (ch) =>
          !q ||
          (ch.title ?? '').toLowerCase().includes(q) ||
          ch.bookTitle.toLowerCase().includes(q),
      ),
    [chapters, q],
  );

  const filteredEntities = useMemo(
    () =>
      entities.filter(
        (e) =>
          !q ||
          e.display_name.toLowerCase().includes(q) ||
          e.kind.name.toLowerCase().includes(q),
      ),
    [entities, q],
  );

  // ── Toggle attach/detach ──────────────────────────────────────────────────

  function toggleItem(item: ContextItem) {
    if (attachedIds.has(item.id)) {
      onDetach(item.id);
    } else {
      onAttach(item);
    }
  }

  // ── Tab config ────────────────────────────────────────────────────────────

  const TABS: { value: PickerTab; label: string; icon: React.ReactNode }[] = [
    { value: 'book', label: 'Books', icon: <BookOpen className="h-3 w-3" /> },
    { value: 'chapter', label: 'Chapters', icon: <FileText className="h-3 w-3" /> },
    {
      value: 'glossary',
      label: 'Glossary',
      icon: (
        <svg className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 01-1.806-1.741L3.842 10.1a2 2 0 011.075-2.029l1.29-.645a6 6 0 013.86-.517l.318.158a6 6 0 003.86.517l2.387-.477a2 2 0 012.368 2.367l-.402 2.814a2 2 0 01-.77 1.34z" />
        </svg>
      ),
    },
  ];

  // Chapter grouping by book
  const chaptersByBook = useMemo(() => {
    const map = new Map<string, { title: string; chapters: typeof filteredChapters }>();
    for (const ch of filteredChapters) {
      const key = ch.book_id;
      if (!map.has(key)) map.set(key, { title: ch.bookTitle, chapters: [] });
      map.get(key)!.chapters.push(ch);
    }
    return Array.from(map.entries());
  }, [filteredChapters]);

  return (
    <div className="w-[380px] max-h-[70vh] overflow-hidden rounded-xl border border-border bg-card shadow-[0_16px_48px_rgba(0,0,0,0.5)]">
      {/* Tabs */}
      <div className="flex border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => { setTab(t.value); setSearch(''); }}
            className={cn(
              'flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-[12px] font-medium transition-colors',
              tab === t.value
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {/* Glossary filters (only on glossary tab) */}
      {tab === 'glossary' && (
        <div className="flex gap-1.5 border-b border-border px-2.5 py-2">
          <select
            value={glossaryBookId}
            onChange={(e) => setGlossaryBookId(e.target.value)}
            className="flex-1 rounded border border-border bg-input px-2 py-1 text-[11px] text-foreground"
          >
            {books.map((b) => (
              <option key={b.book_id} value={b.book_id}>
                {b.title}
              </option>
            ))}
          </select>
          <select
            value={glossaryKind}
            onChange={(e) => setGlossaryKind(e.target.value)}
            className="w-[100px] rounded border border-border bg-input px-2 py-1 text-[11px] text-muted-foreground"
          >
            <option value="">All kinds</option>
            {kinds.map((k) => (
              <option key={k.kind_id} value={k.code}>
                {k.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Search */}
      <div className="relative border-b border-border">
        <Search className="absolute left-3 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={
            tab === 'book' ? 'Search books...' : tab === 'chapter' ? 'Search chapters...' : 'Search entities...'
          }
          className="w-full border-none bg-transparent py-2 pl-8 pr-3 text-[12px] text-foreground placeholder:text-muted-foreground/60 focus:outline-none"
        />
      </div>

      {/* Items list */}
      <div className="max-h-[240px] overflow-y-auto">
        {/* Books tab */}
        {tab === 'book' &&
          filteredBooks.map((b) => {
            const item: ContextItem = { id: b.book_id, type: 'book', label: b.title };
            const isAttached = attachedIds.has(b.book_id);
            return (
              <button
                key={b.book_id}
                onClick={() => toggleItem(item)}
                className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-card-foreground/5"
              >
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[5px] bg-primary/10 text-primary">
                  <BookOpen className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12px] font-medium">{b.title}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {b.chapter_count} chapters{b.original_language ? ` \u00B7 ${b.original_language}` : ''}
                  </p>
                </div>
                {isAttached && <span className="text-[10px] text-accent">{'\u2713'} attached</span>}
              </button>
            );
          })}

        {/* Chapters tab */}
        {tab === 'chapter' &&
          chaptersByBook.map(([bookId, group]) => (
            <div key={bookId}>
              <div className="bg-background px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {group.title}
              </div>
              {group.chapters.map((ch) => {
                const item: ContextItem = {
                  id: ch.chapter_id,
                  type: 'chapter',
                  label: ch.title || ch.original_filename || '(untitled)',
                  bookId: ch.book_id,
                  chapterId: ch.chapter_id,
                };
                const isAttached = attachedIds.has(ch.chapter_id);
                return (
                  <button
                    key={ch.chapter_id}
                    onClick={() => toggleItem(item)}
                    className={cn(
                      'flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-card-foreground/5',
                      isAttached && 'bg-accent/5',
                    )}
                  >
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[5px] bg-accent/10 text-accent">
                      <FileText className="h-3.5 w-3.5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[12px] font-medium">
                        {ch.title || ch.original_filename || '(untitled)'}
                      </p>
                      <p className="text-[10px] text-muted-foreground">
                        {Math.round(ch.byte_size / 5).toLocaleString()} words
                      </p>
                    </div>
                    {isAttached && <span className="text-[10px] text-accent">{'\u2713'} attached</span>}
                  </button>
                );
              })}
            </div>
          ))}

        {/* Glossary tab */}
        {tab === 'glossary' &&
          filteredEntities.map((e) => {
            const item: ContextItem = {
              id: e.entity_id,
              type: 'glossary',
              label: e.display_name || '(unnamed)',
              bookId: e.book_id,
              kindColor: e.kind.color,
            };
            const isAttached = attachedIds.has(e.entity_id);
            return (
              <button
                key={e.entity_id}
                onClick={() => toggleItem(item)}
                className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-card-foreground/5"
              >
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: e.kind.color }}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12px] font-medium">{e.display_name || '(unnamed)'}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {e.kind.name} {'\u00B7'} {(e as unknown as { attribute_count?: number }).attribute_count ?? ''} {e.bookTitle}
                  </p>
                </div>
                {isAttached && <span className="text-[10px] text-accent">{'\u2713'} attached</span>}
              </button>
            );
          })}

        {/* Empty state */}
        {((tab === 'book' && filteredBooks.length === 0) ||
          (tab === 'chapter' && filteredChapters.length === 0) ||
          (tab === 'glossary' && filteredEntities.length === 0)) && (
          <p className="py-6 text-center text-[11px] text-muted-foreground">
            {search ? 'No matches found.' : 'No items available.'}
          </p>
        )}
      </div>
    </div>
  );
}
