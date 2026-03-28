import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, BookOpen, Trash2 } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Book } from '@/features/books/api';
import { LanguagePicker } from '@/components/books/LanguagePicker';
import { VisibilityBadge } from '@/components/books/VisibilityBadge';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { DataTable, FilterToolbar, Pagination, SortDropdown, EmptyState } from '@/components/data';
import type { ColumnDef, SortState } from '@/components/data';

/**
 * V2 BooksPage — Redesigned:
 * - "Create book" moved to a modal dialog (content-first layout)
 * - Full DataTable with search, sort, pagination
 * - Clean toolbar with consistent filter patterns
 */
export function BooksPageV2() {
  const { accessToken } = useAuth();
  const [items, setItems] = useState<Book[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  // Create modal state
  const [createOpen, setCreateOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [originalLanguage, setOriginalLanguage] = useState('');
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  // Table state
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortState | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const load = async () => {
    if (!accessToken) return;
    setIsLoading(true);
    try {
      const res = await booksApi.listBooks(accessToken);
      setItems(res.items);
      setTotal(res.total || res.items.length);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [accessToken]);

  // Client-side filter + sort (API doesn't support these yet)
  const filtered = useMemo(() => {
    let result = items;

    // Search
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(
        (b) => b.title.toLowerCase().includes(q) || b.original_language?.toLowerCase().includes(q),
      );
    }

    // Sort
    if (sort) {
      result = [...result].sort((a, b) => {
        let cmp = 0;
        switch (sort.field) {
          case 'title':
            cmp = a.title.localeCompare(b.title);
            break;
          case 'chapter_count':
            cmp = a.chapter_count - b.chapter_count;
            break;
          case 'original_language':
            cmp = (a.original_language ?? '').localeCompare(b.original_language ?? '');
            break;
          default:
            break;
        }
        return sort.direction === 'desc' ? -cmp : cmp;
      });
    }

    return result;
  }, [items, search, sort]);

  // Paginate
  const pageData = filtered.slice((page - 1) * pageSize, page * pageSize);

  const handleSort = (field: string) => {
    setSort((prev) => {
      if (prev?.field === field) {
        return prev.direction === 'asc' ? { field, direction: 'desc' } : null;
      }
      return { field, direction: 'asc' };
    });
  };

  const onCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!accessToken) return;
    setIsCreating(true);
    try {
      const created = await booksApi.createBook(accessToken, {
        title,
        description: description || undefined,
        original_language: originalLanguage || undefined,
      });
      if (coverFile) {
        await booksApi.uploadCover(accessToken, created.book_id, coverFile);
      }
      setTitle('');
      setDescription('');
      setOriginalLanguage('');
      setCoverFile(null);
      setCreateOpen(false);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsCreating(false);
    }
  };

  // Column definitions
  const columns: ColumnDef<Book>[] = [
    {
      key: 'title',
      header: 'Title',
      sortable: true,
      render: (b) => (
        <Link to={`/books/${b.book_id}`} className="font-medium text-foreground hover:underline">
          {b.title}
        </Link>
      ),
    },
    {
      key: 'original_language',
      header: 'Language',
      sortable: true,
      widthClass: 'w-28',
      hideBelow: 'sm',
      render: (b) => (
        <span className="text-xs text-muted-foreground">{b.original_language || '—'}</span>
      ),
    },
    {
      key: 'chapter_count',
      header: 'Chapters',
      sortable: true,
      widthClass: 'w-24',
      hideBelow: 'sm',
      render: (b) => <span className="text-xs tabular-nums">{b.chapter_count}</span>,
    },
    {
      key: 'visibility',
      header: 'Visibility',
      widthClass: 'w-28',
      hideBelow: 'md',
      render: (b) => <VisibilityBadge visibility={b.visibility} />,
    },
    {
      key: 'lifecycle_state',
      header: 'State',
      widthClass: 'w-24',
      hideBelow: 'lg',
      render: (b) => (
        <Badge variant={b.lifecycle_state === 'active' ? 'success' : 'muted'}>
          {b.lifecycle_state}
        </Badge>
      ),
    },
  ];

  const sortOptions = [
    { field: 'title', label: 'Title' },
    { field: 'chapter_count', label: 'Chapters' },
    { field: 'original_language', label: 'Language' },
  ];

  return (
    <div className="space-y-4">
      {/* ── Page header ───────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">My Books</h1>
          <p className="text-xs text-muted-foreground">
            {total} {total === 1 ? 'book' : 'books'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link to="/books/trash">
              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
              Recycle bin
            </Link>
          </Button>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            New Book
          </Button>
        </div>
      </div>

      {/* ── Toolbar ───────────────────────────────────────────────────────────── */}
      <FilterToolbar
        searchValue={search}
        onSearchChange={(v) => {
          setSearch(v);
          setPage(1);
        }}
        searchPlaceholder="Search books…"
      >
        <SortDropdown sort={sort} options={sortOptions} onSortChange={setSort} />
      </FilterToolbar>

      {/* ── Error ─────────────────────────────────────────────────────────────── */}
      {error && (
        <p className="rounded border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      )}

      {/* ── Table ─────────────────────────────────────────────────────────────── */}
      {!isLoading && pageData.length === 0 ? (
        <EmptyState
          icon={<BookOpen className="h-10 w-10 text-muted-foreground/50" />}
          title={search ? 'No books match your search' : 'No books yet'}
          description={search ? 'Try a different search term.' : 'Create your first book to get started.'}
          filtered={!!search}
          action={
            !search ? { label: 'Create Book', onClick: () => setCreateOpen(true) } : undefined
          }
        />
      ) : (
        <DataTable
          columns={columns}
          data={pageData}
          rowKey={(b) => b.book_id}
          isLoading={isLoading}
          sort={sort}
          onSort={handleSort}
        />
      )}

      {/* ── Pagination ────────────────────────────────────────────────────────── */}
      {filtered.length > 0 && (
        <Pagination
          page={page}
          pageSize={pageSize}
          total={filtered.length}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setPage(1);
          }}
        />
      )}

      {/* ── Create Book Modal ─────────────────────────────────────────────────── */}
      {createOpen && (
        <DialogContent onClose={() => setCreateOpen(false)} className="max-w-md">
          <DialogHeader>
            <DialogTitle>Create New Book</DialogTitle>
          </DialogHeader>

          <form onSubmit={onCreate} className="space-y-4 pt-2">
            <div>
              <label className="mb-1 block text-sm font-medium">Title</label>
              <input
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                placeholder="Book title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                autoFocus
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium">Description</label>
              <textarea
                className="min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                placeholder="Optional description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>

            <LanguagePicker
              value={originalLanguage}
              onChange={setOriginalLanguage}
              label="Original language"
            />

            <div>
              <label className="mb-1 block text-sm font-medium">Cover image</label>
              <input
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm file:border-0 file:bg-transparent file:text-sm file:font-medium"
                type="file"
                accept="image/*"
                onChange={(e) => setCoverFile(e.target.files?.[0] ?? null)}
              />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isCreating}>
                {isCreating ? 'Creating…' : 'Create Book'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      )}
    </div>
  );
}
