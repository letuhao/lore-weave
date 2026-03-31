import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Plus, Pencil, Download, Trash2, Upload } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { DataTable, type Column } from '@/components/data/DataTable';
import { FormDialog, ConfirmDialog, EmptyState, Pagination, StatusBadge } from '@/components/shared';
import { LanguageDisplay } from '@/components/shared/LanguageDisplay';
import { Skeleton } from '@/components/shared/Skeleton';
import { ImportDialog } from '@/components/import/ImportDialog';

interface ChaptersTabProps {
  bookId: string;
}

export function ChaptersTab({ bookId }: ChaptersTabProps) {
  const { t } = useTranslation();
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const limit = 20;

  // Create dialog
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newLang, setNewLang] = useState('');
  const [newBody, setNewBody] = useState('');

  // Import dialog
  const [importOpen, setImportOpen] = useState(false);

  // Trash dialog
  const [trashTarget, setTrashTarget] = useState<Chapter | null>(null);

  const load = async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const res = await booksApi.listChapters(accessToken, bookId, {
        lifecycle_state: 'active',
        limit,
        offset,
      });
      setChapters(res.items);
      setTotal(res.total);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { void load(); }, [accessToken, bookId, offset]);

  const handleCreate = async () => {
    if (!accessToken || !newLang) return;
    setCreating(true);
    try {
      const created = await booksApi.createChapterEditor(accessToken, bookId, {
        title: newTitle || undefined,
        original_language: newLang,
        body: newBody || undefined,
      });
      setCreateOpen(false);
      setNewTitle('');
      setNewLang('');
      setNewBody('');
      navigate(`/books/${bookId}/chapters/${created.chapter_id}/edit`);
    } catch (e) {
      toast.error((e as Error).message);
    }
    setCreating(false);
  };

  const handleTrash = async () => {
    if (!accessToken || !trashTarget) return;
    try {
      await booksApi.trashChapter(accessToken, bookId, trashTarget.chapter_id);
      setTrashTarget(null);
      await load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const handleDownload = async (ch: Chapter) => {
    if (!accessToken) return;
    try {
      const blob = await booksApi.downloadRaw(accessToken, bookId, ch.chapter_id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${ch.title || ch.original_filename}.txt`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Chapter exported');
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const columns: Column<Chapter>[] = [
    {
      key: 'order',
      header: '#',
      className: 'w-12 text-muted-foreground font-mono text-xs',
      render: (ch) => ch.sort_order,
    },
    {
      key: 'title',
      header: 'Title',
      render: (ch) => (
        <span className="font-medium">{ch.title || ch.original_filename}</span>
      ),
    },
    {
      key: 'language',
      header: 'Language',
      className: 'w-32',
      render: (ch) => <LanguageDisplay code={ch.original_language} />,
    },
    {
      key: 'status',
      header: 'Status',
      className: 'w-24',
      render: (ch) => <StatusBadge variant={ch.lifecycle_state} />,
    },
    {
      key: 'updated',
      header: 'Updated',
      className: 'w-32 text-xs text-muted-foreground',
      render: (ch) => ch.draft_updated_at
        ? new Date(ch.draft_updated_at).toLocaleDateString()
        : '—',
    },
    {
      key: 'actions',
      header: '',
      className: 'w-28 text-right',
      render: (ch) => (
        <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
          <Link
            to={`/books/${bookId}/chapters/${ch.chapter_id}/edit`}
            className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            title="Edit"
          >
            <Pencil className="h-3.5 w-3.5" />
          </Link>
          <button
            onClick={() => void handleDownload(ch)}
            className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            title="Download"
          >
            <Download className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => setTrashTarget(ch)}
            className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
            title="Trash"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {total} {total === 1 ? 'chapter' : 'chapters'}
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setImportOpen(true)}
            className="inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <Upload className="h-3.5 w-3.5" />
            Import
          </button>
          <button
            onClick={() => setCreateOpen(true)}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <Plus className="h-3.5 w-3.5" />
            New Chapter
          </button>
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex gap-4 rounded border p-4">
              <Skeleton className="h-4 w-8" />
              <Skeleton className="h-4 flex-1" />
              <Skeleton className="h-4 w-20" />
            </div>
          ))}
        </div>
      )}

      {/* Empty */}
      {!loading && chapters.length === 0 && (
        <EmptyState
          icon={Pencil}
          title="No chapters yet"
          description="Create your first chapter to start writing."
          action={
            <button
              onClick={() => setCreateOpen(true)}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
            >
              <Plus className="h-4 w-4" />
              New Chapter
            </button>
          }
        />
      )}

      {/* Table */}
      {!loading && chapters.length > 0 && (
        <DataTable
          columns={columns}
          data={chapters}
          rowKey={(ch) => ch.chapter_id}
          onRowClick={(ch) => navigate(`/books/${bookId}/chapters/${ch.chapter_id}/edit`)}
        />
      )}

      <Pagination total={total} limit={limit} offset={offset} onChange={setOffset} />

      {/* Create dialog */}
      <FormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        title="New Chapter"
        description="Create a new chapter in the editor."
        footer={
          <>
            <button onClick={() => setCreateOpen(false)} className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-secondary">
              {t('common.cancel')}
            </button>
            <button
              onClick={() => void handleCreate()}
              disabled={creating || !newLang}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {t('common.create')}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Title</label>
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Chapter title (optional)"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Language <span className="text-destructive">*</span></label>
            <input
              value={newLang}
              onChange={(e) => setNewLang(e.target.value)}
              placeholder="ja, en, vi, zh-TW..."
              className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
              required
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Initial draft</label>
            <textarea
              value={newBody}
              onChange={(e) => setNewBody(e.target.value)}
              placeholder="Start writing... (optional)"
              rows={4}
              className="w-full resize-none rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
            />
          </div>
        </div>
      </FormDialog>

      {/* Trash confirm */}
      <ConfirmDialog
        open={!!trashTarget}
        onOpenChange={(open) => { if (!open) setTrashTarget(null); }}
        title="Move chapter to trash?"
        description={`"${trashTarget?.title || trashTarget?.original_filename}" will be moved to trash.`}
        confirmLabel="Move to Trash"
        variant="destructive"
        onConfirm={() => void handleTrash()}
      />

      {/* Import dialog */}
      <ImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        bookId={bookId}
        onImported={() => void load()}
      />
    </div>
  );
}
