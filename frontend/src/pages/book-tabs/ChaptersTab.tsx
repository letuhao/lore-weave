import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Pencil, Download, Trash2, Upload, Sparkles, Languages } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { DataTable, type Column } from '@/components/data/DataTable';
import { FormDialog, ConfirmDialog, EmptyState, Pagination, StatusBadge } from '@/components/shared';
import { LanguageDisplay } from '@/components/shared/LanguageDisplay';
import { Skeleton } from '@/components/shared/Skeleton';
import { ImportDialog } from '@/components/import/ImportDialog';
import { ExtractionWizard } from '@/features/extraction/ExtractionWizard';

interface ChaptersTabProps {
  bookId: string;
}

export function ChaptersTab({ bookId }: ChaptersTabProps) {
  const { t } = useTranslation('books');
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
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

  // Extraction wizard
  const [extractChapterId, setExtractChapterId] = useState<string | null>(null);

  // Trash dialog
  const [trashTarget, setTrashTarget] = useState<Chapter | null>(null);

  const { data, isLoading: loading } = useQuery({
    queryKey: ['chapters', bookId, offset],
    queryFn: () => booksApi.listChapters(accessToken!, bookId, { lifecycle_state: 'active', limit, offset }),
    enabled: !!accessToken,
  });

  const chapters = data?.items ?? [];
  const total = data?.total ?? 0;

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['chapters', bookId] });

  const handleCreate = async () => {
    if (!accessToken || !newLang) return;
    setCreating(true);
    try {
      const created = await booksApi.createChapterEditor(accessToken, bookId, {
        title: newTitle || undefined,
        original_language: newLang,
        body: newBody || undefined,
      });
      invalidate(); // Clear cache so chapter list refetches when user navigates back
      setCreateOpen(false);
      setNewTitle('');
      setNewLang('');
      setNewBody('');
      // #16 1.5 — same rationale as the row-click/pencil-icon flip below: a newly created chapter
      // opens in Studio, not the legacy editor.
      navigate(`/books/${bookId}/studio?chapter=${created.chapter_id}`);
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
      invalidate();
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
      toast.success(t('chapters.exported'));
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
      header: t('chapters.col.title'),
      render: (ch) => (
        <span data-testid="chapter-title-cell" className="font-medium">{ch.title || ch.original_filename}</span>
      ),
    },
    {
      key: 'language',
      header: t('chapters.col.language'),
      className: 'w-32',
      render: (ch) => <LanguageDisplay code={ch.original_language} />,
    },
    {
      key: 'status',
      header: t('chapters.col.status'),
      className: 'w-24',
      render: (ch) => <StatusBadge variant={ch.lifecycle_state} />,
    },
    {
      key: 'updated',
      header: t('chapters.col.updated'),
      className: 'w-32 text-xs text-muted-foreground',
      render: (ch) => ch.draft_updated_at
        ? new Date(ch.draft_updated_at).toLocaleDateString()
        : '—',
    },
    {
      key: 'actions',
      header: '',
      className: 'w-36 text-right',
      render: (ch) => (
        <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
          {/* #16 1.5 — opens the Writing Studio focused on this chapter, not the legacy editor
              route (spec 16 M3: Phase 1 data-safety parity reached, so Studio is no longer
              strictly worse). The legacy route stays reachable directly by URL until Phase 4. */}
          <Link
            to={`/books/${bookId}/studio?chapter=${ch.chapter_id}`}
            className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            title={t('chapters.action.edit')}
          >
            <Pencil className="h-3.5 w-3.5" />
          </Link>
          <Link
            to={`/books/${bookId}/chapters/${ch.chapter_id}/translations`}
            className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            title={t('chapters.action.translations')}
          >
            <Languages className="h-3.5 w-3.5" />
          </Link>
          <button
            onClick={() => setExtractChapterId(ch.chapter_id)}
            className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary"
            title={t('chapters.action.extract')}
          >
            <Sparkles className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => void handleDownload(ch)}
            className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            title={t('chapters.action.download')}
          >
            <Download className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => setTrashTarget(ch)}
            className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
            title={t('chapters.action.trash')}
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
          {t('chapters.count', { count: total })}
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setImportOpen(true)}
            className="inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <Upload className="h-3.5 w-3.5" />
            {t('chapters.import')}
          </button>
          <button
            onClick={() => setCreateOpen(true)}
            data-testid="chapter-add-button"
            className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <Plus className="h-3.5 w-3.5" />
            {t('chapters.new')}
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
          title={t('chapters.empty.title')}
          description={t('chapters.empty.description')}
          action={
            <button
              onClick={() => setCreateOpen(true)}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
            >
              <Plus className="h-4 w-4" />
              {t('chapters.new')}
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
          onRowClick={(ch) => navigate(`/books/${bookId}/studio?chapter=${ch.chapter_id}`)}
        />
      )}

      <Pagination total={total} limit={limit} offset={offset} onChange={setOffset} />

      {/* Create dialog */}
      <FormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        title={t('chapters.create.title')}
        description={t('chapters.create.description')}
        footer={
          <>
            <button onClick={() => setCreateOpen(false)} data-testid="chapter-create-cancel" className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-secondary">
              {t('common.cancel', { ns: 'common' })}
            </button>
            <button
              onClick={() => void handleCreate()}
              disabled={creating || !newLang}
              data-testid="chapter-create-submit"
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {t('common.create', { ns: 'common' })}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('chapters.create.title_label')}</label>
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder={t('chapters.create.title_placeholder')}
              data-testid="chapter-title-input"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('chapters.create.language_label')} <span className="text-destructive">*</span></label>
            <input
              value={newLang}
              onChange={(e) => setNewLang(e.target.value)}
              placeholder="ja, en, vi, zh-TW..."
              data-testid="chapter-language-input"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
              required
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('chapters.create.body_label')}</label>
            <textarea
              value={newBody}
              onChange={(e) => setNewBody(e.target.value)}
              placeholder={t('chapters.create.body_placeholder')}
              rows={4}
              data-testid="chapter-body-input"
              className="w-full resize-none rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
            />
          </div>
        </div>
      </FormDialog>

      {/* Trash confirm */}
      <ConfirmDialog
        open={!!trashTarget}
        onOpenChange={(open) => { if (!open) setTrashTarget(null); }}
        title={t('chapters.trash_confirm.title')}
        description={t('chapters.trash_confirm.description', { title: trashTarget?.title || trashTarget?.original_filename })}
        confirmLabel={t('chapters.trash_confirm.confirm')}
        variant="destructive"
        onConfirm={() => void handleTrash()}
      />

      {/* Import dialog */}
      <ImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        bookId={bookId}
        onImported={() => invalidate()}
      />

      <ExtractionWizard
        // Remount per chapter so useExtractionState's useState initializer re-seeds
        // chapterIds from preselectedChapterIds. Without this key the wizard mounts
        // once (closed, preselected=undefined → chapterIds=[]) and the later prop is
        // ignored, so extraction ran over 0 chapters (F-1).
        key={extractChapterId ?? 'closed'}
        open={!!extractChapterId}
        onOpenChange={(open) => { if (!open) setExtractChapterId(null); }}
        bookId={bookId}
        mode="single"
        preselectedChapterIds={extractChapterId ? [extractChapterId] : undefined}
      />
    </div>
  );
}
