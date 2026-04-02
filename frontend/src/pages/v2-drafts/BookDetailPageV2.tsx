import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Plus,
  Upload,
  FileText,
  Pencil,
  Languages,
  Trash2,
  BookOpen,
  Share2,
} from 'lucide-react';
import { SharingTab } from '@/features/sharing/SharingTab';
import { useAuth } from '@/auth';
import { booksApi, type Book, type Chapter } from '@/features/books/api';
import { LanguagePicker } from '@/components/books/LanguagePicker';
import { VisibilityBadge } from '@/components/books/VisibilityBadge';
import { LanguageStatusDots } from '@/components/translation/LanguageStatusDots';
import { versionsApi, type ChapterCoverage } from '@/features/translation/versionsApi';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Select } from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from '@/components/ui/dropdown-menu';
import { DataTable, FilterToolbar, Pagination, SortDropdown, EmptyState, ViewToggle } from '@/components/data';
import type { ColumnDef, SortState, ViewMode } from '@/components/data';

/**
 * V2 BookDetailPage — Redesigned:
 * - Tabs: Overview | Chapters (instead of everything stacked)
 * - Create chapter via modal (not inline forms)
 * - Chapter list uses DataTable with proper filters, sort, pagination
 * - Row actions in dropdown menus
 */
export function BookDetailPageV2() {
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const { bookId = '' } = useParams();

  const [book, setBook] = useState<Book | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [coverage, setCoverage] = useState<ChapterCoverage[]>([]);

  // Table state
  const [activeTab, setActiveTab] = useState('chapters');
  const [search, setSearch] = useState('');
  const [langFilter, setLangFilter] = useState('');
  const [lifecycleFilter, setLifecycleFilter] = useState('active');
  const [sort, setSort] = useState<SortState | null>({ field: 'sort_order', direction: 'asc' });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [view, setView] = useState<ViewMode>('table');

  // Create modal state
  const [createMode, setCreateMode] = useState<'editor' | 'upload' | null>(null);
  const [newTitle, setNewTitle] = useState('');
  const [newLang, setNewLang] = useState('');
  const [newFile, setNewFile] = useState<File | null>(null);
  const [editorBody, setEditorBody] = useState('');

  const load = async () => {
    if (!accessToken || !bookId) return;
    setIsLoading(true);
    try {
      const [b, ch, sharing] = await Promise.all([
        booksApi.getBook(accessToken, bookId),
        booksApi.listChapters(accessToken, bookId, {
          lifecycle_state: lifecycleFilter || undefined,
          limit: 200,
        }),
        booksApi.getSharing(accessToken, bookId).catch(() => null),
      ]);
      setBook(sharing ? { ...b, visibility: sharing.visibility } : b);
      setChapters(ch.items);
      setTotal(ch.total);
      setError('');
      versionsApi
        .getBookCoverage(accessToken!, bookId)
        .then((r) => setCoverage(r.coverage))
        .catch(() => {});
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [accessToken, bookId, lifecycleFilter]);

  // Client-side filter + sort
  const filtered = useMemo(() => {
    let result = chapters;

    if (search) {
      const q = search.toLowerCase();
      result = result.filter(
        (c) =>
          c.title?.toLowerCase().includes(q) || c.original_filename.toLowerCase().includes(q),
      );
    }
    if (langFilter) {
      result = result.filter((c) => c.original_language === langFilter);
    }

    if (sort) {
      result = [...result].sort((a, b) => {
        let cmp = 0;
        switch (sort.field) {
          case 'sort_order':
            cmp = a.sort_order - b.sort_order;
            break;
          case 'title':
            cmp = (a.title ?? a.original_filename).localeCompare(b.title ?? b.original_filename);
            break;
          case 'original_language':
            cmp = a.original_language.localeCompare(b.original_language);
            break;
          default:
            break;
        }
        return sort.direction === 'desc' ? -cmp : cmp;
      });
    }

    return result;
  }, [chapters, search, langFilter, sort]);

  const pageData = filtered.slice((page - 1) * pageSize, page * pageSize);

  const handleSort = (field: string) => {
    setSort((prev) => {
      if (prev?.field === field) {
        return prev.direction === 'asc' ? { field, direction: 'desc' } : null;
      }
      return { field, direction: 'asc' };
    });
  };

  // Unique languages from chapters
  const languages = useMemo(
    () => [...new Set(chapters.map((c) => c.original_language))].sort(),
    [chapters],
  );

  // Active filter chips
  const activeFilters = [
    ...(langFilter
      ? [{ label: `Language: ${langFilter}`, onRemove: () => setLangFilter('') }]
      : []),
    ...(lifecycleFilter !== 'active'
      ? [{ label: `State: ${lifecycleFilter}`, onRemove: () => setLifecycleFilter('active') }]
      : []),
  ];

  async function uploadChapter(e: FormEvent) {
    e.preventDefault();
    if (!accessToken || !bookId || !newFile || !newLang) return;
    try {
      await booksApi.createChapterUpload(accessToken, bookId, {
        file: newFile,
        original_language: newLang,
        title: newTitle || undefined,
      });
      resetCreateForm();
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function createFromEditor(e: FormEvent) {
    e.preventDefault();
    if (!accessToken || !bookId || !newLang) return;
    try {
      const created = await booksApi.createChapterEditor(accessToken, bookId, {
        title: newTitle || undefined,
        original_language: newLang,
        body: editorBody || undefined,
      });
      resetCreateForm();
      navigate(`/books/${bookId}/chapters/${created.chapter_id}/edit`);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  function resetCreateForm() {
    setCreateMode(null);
    setNewTitle('');
    setNewLang('');
    setNewFile(null);
    setEditorBody('');
  }

  async function trashChapter(chapterId: string) {
    if (!accessToken || !bookId) return;
    await booksApi.trashChapter(accessToken, bookId, chapterId);
    await load();
  }

  async function handleToggleLifecycle(chapterId: string, currentState: Chapter['lifecycle_state']) {
    if (!accessToken || !bookId) return;
    // Optimistic update
    setChapters((prev) =>
      prev.map((c) =>
        c.chapter_id === chapterId
          ? { ...c, lifecycle_state: currentState === 'active' ? 'trashed' : 'active' }
          : c,
      ),
    );
    try {
      if (currentState === 'active') {
        await booksApi.trashChapter(accessToken, bookId, chapterId);
      } else {
        await booksApi.restoreChapter(accessToken, bookId, chapterId);
      }
    } catch (err) {
      setError((err as Error).message);
      await load(); // revert on failure
    }
  }

  // Column definitions
  const columns: ColumnDef<Chapter>[] = [
    {
      key: 'sort_order',
      header: '#',
      sortable: true,
      widthClass: 'w-14',
      render: (c) => <span className="text-xs tabular-nums text-muted-foreground">{c.sort_order}</span>,
    },
    {
      key: 'title',
      header: 'Title',
      sortable: true,
      render: (c) => {
        const chapterCoverage = coverage.find((cv) => cv.chapter_id === c.chapter_id);
        return (
          <div className="flex items-center justify-between gap-2">
            <Link
              to={`/books/${bookId}/chapters/${c.chapter_id}/edit`}
              className="font-medium text-foreground hover:underline"
            >
              {c.title || c.original_filename}
            </Link>
            {chapterCoverage && (
              <LanguageStatusDots
                bookId={bookId}
                chapterId={c.chapter_id}
                coverage={chapterCoverage.languages}
              />
            )}
          </div>
        );
      },
    },
    {
      key: 'original_language',
      header: 'Language',
      sortable: true,
      widthClass: 'w-24',
      hideBelow: 'sm',
      render: (c) => <span className="text-xs">{c.original_language}</span>,
    },
    {
      key: 'actions',
      header: '',
      widthClass: 'w-36',
      render: (c) => (
        <div className="flex items-center justify-end gap-1">
          {/* Active toggle */}
          <button
            onClick={() => void handleToggleLifecycle(c.chapter_id, c.lifecycle_state)}
            title={c.lifecycle_state === 'active' ? 'Click to archive' : 'Click to restore'}
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors ${
              c.lifecycle_state === 'active'
                ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-900/30 dark:text-emerald-400'
                : 'bg-muted text-muted-foreground hover:bg-muted/80'
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                c.lifecycle_state === 'active' ? 'bg-emerald-500' : 'bg-muted-foreground/50'
              }`}
            />
            {c.lifecycle_state === 'active' ? 'active' : c.lifecycle_state}
          </button>
          {/* Edit */}
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            title="Edit chapter"
            onClick={() => navigate(`/books/${bookId}/chapters/${c.chapter_id}/edit`)}
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          {/* Delete */}
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
            title="Move to trash"
            onClick={() => void trashChapter(c.chapter_id)}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      ),
    },
  ];

  const sortOptions = [
    { field: 'sort_order', label: 'Order' },
    { field: 'title', label: 'Title' },
    { field: 'original_language', label: 'Language' },
  ];

  if (!book && !isLoading) {
    return <p className="text-sm text-muted-foreground">{error || 'Loading…'}</p>;
  }

  return (
    <div className="space-y-5">
      {/* ── Book Header ───────────────────────────────────────────────────────── */}
      {book && (
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-semibold">{book.title}</h1>
              <VisibilityBadge visibility={book.visibility} />
            </div>
            <p className="text-xs text-muted-foreground">
              {book.original_language || 'No language set'} · {total} chapters · {book.lifecycle_state}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" asChild>
              <Link to={`/books/${bookId}/sharing`}>
                <Share2 className="mr-1.5 h-3.5 w-3.5" /> Sharing
              </Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to={`/books/${bookId}/translation`}>
                <Languages className="mr-1.5 h-3.5 w-3.5" /> Translation
              </Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to={`/books/${bookId}/glossary`}>
                <BookOpen className="mr-1.5 h-3.5 w-3.5" /> Glossary
              </Link>
            </Button>
          </div>
        </div>
      )}

      {/* ── Tabs ──────────────────────────────────────────────────────────────── */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="chapters">Chapters</TabsTrigger>
          <TabsTrigger value="sharing">Sharing</TabsTrigger>
          <TabsTrigger value="overview">Overview</TabsTrigger>
        </TabsList>

        {/* ── Chapters Tab ────────────────────────────────────────────────────── */}
        <TabsContent value="chapters" className="space-y-4">
          {/* Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <FilterToolbar
              searchValue={search}
              onSearchChange={(v) => {
                setSearch(v);
                setPage(1);
              }}
              searchPlaceholder="Search chapters…"
              activeFilters={activeFilters}
              onClearAll={() => {
                setLangFilter('');
                setLifecycleFilter('active');
              }}
            >
              {/* Language filter */}
              {languages.length > 1 && (
                <Select
                  value={langFilter}
                  onChange={(e) => {
                    setLangFilter(e.target.value);
                    setPage(1);
                  }}
                  className="h-8 w-auto text-xs"
                >
                  <option value="">All languages</option>
                  {languages.map((lang) => (
                    <option key={lang} value={lang}>
                      {lang}
                    </option>
                  ))}
                </Select>
              )}

              {/* Lifecycle filter */}
              <Select
                value={lifecycleFilter}
                onChange={(e) => {
                  setLifecycleFilter(e.target.value);
                  setPage(1);
                }}
                className="h-8 w-auto text-xs"
              >
                <option value="active">Active</option>
                <option value="trashed">Trashed</option>
                <option value="purge_pending">Purge pending</option>
              </Select>

              <SortDropdown sort={sort} options={sortOptions} onSortChange={setSort} />
              <ViewToggle view={view} onViewChange={setView} />
            </FilterToolbar>

            {/* Add chapter button */}
            <DropdownMenu>
              <DropdownMenuTrigger className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90">
                <Plus className="h-3.5 w-3.5" /> Add Chapter
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setCreateMode('editor')}>
                  <FileText className="mr-2 h-3.5 w-3.5" /> Create in editor
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setCreateMode('upload')}>
                  <Upload className="mr-2 h-3.5 w-3.5" /> Upload file (.txt)
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          {/* Chapter content */}
          {!isLoading && pageData.length === 0 ? (
            <EmptyState
              title={search || langFilter ? 'No chapters match your filters' : 'No chapters yet'}
              description={
                search || langFilter
                  ? 'Try adjusting your filters.'
                  : 'Add your first chapter to get started.'
              }
              filtered={!!(search || langFilter)}
              action={
                !search && !langFilter
                  ? { label: 'Add Chapter', onClick: () => setCreateMode('editor') }
                  : undefined
              }
            />
          ) : view === 'table' ? (
            <DataTable
              columns={columns}
              data={pageData}
              rowKey={(c) => c.chapter_id}
              isLoading={isLoading}
              sort={sort}
              onSort={handleSort}
            />
          ) : (
            /* ── Grid view ── */
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {isLoading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className="space-y-3 rounded-lg border p-4">
                      <Skeleton className="h-3 w-10 rounded" />
                      <Skeleton className="h-4 w-3/4 rounded" />
                      <Skeleton className="h-3 w-1/2 rounded" />
                    </div>
                  ))
                : pageData.map((c) => {
                    const chapterCoverage = coverage.find((cv) => cv.chapter_id === c.chapter_id);
                    return (
                      <div
                        key={c.chapter_id}
                        className="group flex flex-col gap-2 rounded-lg border bg-card p-4 transition-shadow hover:shadow-md"
                      >
                        {/* Top row: order + state + actions */}
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs tabular-nums text-muted-foreground">
                            #{c.sort_order}
                          </span>
                          <div className="flex items-center gap-1">
                            {/* Active toggle */}
                            <button
                              onClick={() => void handleToggleLifecycle(c.chapter_id, c.lifecycle_state)}
                              title={c.lifecycle_state === 'active' ? 'Click to archive' : 'Click to restore'}
                              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors ${
                                c.lifecycle_state === 'active'
                                  ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-900/30 dark:text-emerald-400'
                                  : 'bg-muted text-muted-foreground hover:bg-muted/80'
                              }`}
                            >
                              <span
                                className={`h-1.5 w-1.5 rounded-full ${
                                  c.lifecycle_state === 'active' ? 'bg-emerald-500' : 'bg-muted-foreground/50'
                                }`}
                              />
                              {c.lifecycle_state === 'active' ? 'active' : c.lifecycle_state}
                            </button>
                            {/* Edit */}
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-6 w-6 p-0"
                              title="Edit chapter"
                              onClick={() => navigate(`/books/${bookId}/chapters/${c.chapter_id}/edit`)}
                            >
                              <Pencil className="h-3 w-3" />
                            </Button>
                            {/* Delete */}
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                              title="Move to trash"
                              onClick={() => void trashChapter(c.chapter_id)}
                            >
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          </div>
                        </div>

                        {/* Title */}
                        <Link
                          to={`/books/${bookId}/chapters/${c.chapter_id}/edit`}
                          className="text-sm font-medium leading-snug group-hover:underline"
                        >
                          {c.title || c.original_filename}
                        </Link>

                        {/* Bottom row: language + translation coverage */}
                        <div className="mt-auto flex items-center justify-between pt-1">
                          <span className="text-xs text-muted-foreground">
                            {c.original_language}
                          </span>
                          {chapterCoverage && (
                            <LanguageStatusDots
                              bookId={bookId}
                              chapterId={c.chapter_id}
                              coverage={chapterCoverage.languages}
                            />
                          )}
                        </div>
                      </div>
                    );
                  })}
            </div>
          )}

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
        </TabsContent>

        {/* ── Sharing Tab ─────────────────────────────────────────────────────── */}
        <TabsContent value="sharing" className="space-y-4">
          <SharingTab bookId={bookId} />
        </TabsContent>

        {/* ── Overview Tab ────────────────────────────────────────────────────── */}
        <TabsContent value="overview" className="space-y-4">
          {book && (
            <div className="max-w-xl space-y-4 rounded-md border p-5">
              <div>
                <label className="text-xs font-medium text-muted-foreground">Title</label>
                <p className="text-sm font-medium">{book.title}</p>
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground">Description</label>
                <p className="text-sm">{book.description || '—'}</p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Language</label>
                  <p className="text-sm">{book.original_language || '—'}</p>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Visibility</label>
                  <div className="mt-0.5">
                    <VisibilityBadge visibility={book.visibility} />
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Chapters</label>
                  <p className="text-sm">{total}</p>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">State</label>
                  <p className="text-sm">{book.lifecycle_state}</p>
                </div>
              </div>
              <div className="border-t pt-3">
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={async () => {
                    if (!accessToken) return;
                    await booksApi.trashBook(accessToken, bookId);
                    await load();
                  }}
                >
                  <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Move book to trash
                </Button>
              </div>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* ── Create Chapter Modal ──────────────────────────────────────────────── */}
      {createMode && (
        <DialogContent onClose={resetCreateForm} className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {createMode === 'editor' ? 'Create Chapter in Editor' : 'Upload Chapter File'}
            </DialogTitle>
          </DialogHeader>

          <form
            onSubmit={createMode === 'editor' ? createFromEditor : uploadChapter}
            className="space-y-4 pt-2"
          >
            <div>
              <label className="mb-1 block text-sm font-medium">Chapter title</label>
              <input
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                placeholder="Chapter title"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                autoFocus
              />
            </div>

            <LanguagePicker
              value={newLang}
              onChange={setNewLang}
              label="Original language"
              required
            />

            {createMode === 'editor' && (
              <div>
                <label className="mb-1 block text-sm font-medium">Initial draft</label>
                <textarea
                  className="min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  placeholder="Start writing… (optional)"
                  value={editorBody}
                  onChange={(e) => setEditorBody(e.target.value)}
                />
              </div>
            )}

            {createMode === 'upload' && (
              <div>
                <label className="mb-1 block text-sm font-medium">File</label>
                <input
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm file:border-0 file:bg-transparent file:text-sm file:font-medium"
                  type="file"
                  accept=".txt,text/plain"
                  onChange={(e) => setNewFile(e.target.files?.[0] ?? null)}
                  required
                />
              </div>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={resetCreateForm}>
                Cancel
              </Button>
              <Button type="submit">
                {createMode === 'editor' ? 'Create & Open Editor' : 'Upload'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
