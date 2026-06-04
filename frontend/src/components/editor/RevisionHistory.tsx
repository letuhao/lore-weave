import { useEffect, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { X, RotateCcw, GitCompare } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { Skeleton } from '@/components/shared/Skeleton';
import { ConfirmDialog } from '@/components/shared';
import { ContentRenderer } from '@/components/reader/ContentRenderer';
import type { JSONContent } from '@tiptap/react';

type Revision = { revision_id: string; created_at: string; message?: string };
type PreviewState = { revision: Revision; blocks: JSONContent[] } | null;

/** Convert flat text to paragraph blocks (fallback for old plain-text revisions) */
function textToBlocks(text: string): JSONContent[] {
  return text.split(/\n\n+/).filter(Boolean).map((p) => ({
    type: 'paragraph',
    content: [{ type: 'text', text: p }],
  }));
}

export function RevisionHistory({ bookId, chapterId, onRestore }: {
  bookId: string; chapterId: string; onRestore: () => void;
}) {
  const { t } = useTranslation('editor');
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<PreviewState>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [restoreTarget, setRestoreTarget] = useState<Revision | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    booksApi.listRevisions(accessToken, bookId, chapterId, { limit: 20, offset: 0 })
      .then((r) => setRevisions(r.items))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [accessToken, bookId, chapterId]);

  const handleView = async (rev: Revision) => {
    if (!accessToken) return;
    setPreviewLoading(true);
    try {
      const data = await booksApi.getRevision(accessToken, bookId, chapterId, rev.revision_id);
      // Prefer Tiptap JSON body; fall back to text_content for old revisions
      const body = data.body as JSONContent | null;
      const blocks = body?.content ?? (data.text_content ? textToBlocks(data.text_content) : []);
      setPreview({ revision: rev, blocks });
    } catch { /* ignore */ }
    setPreviewLoading(false);
  };

  const handleRestore = async () => {
    if (!accessToken || !restoreTarget) return;
    try {
      await booksApi.restoreRevision(accessToken, bookId, chapterId, restoreTarget.revision_id);
      setRestoreTarget(null);
      setPreview(null);
      toast.success(t('revision.restored'));
      onRestore();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  if (loading) {
    return (
      <div className="space-y-2 p-4">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-3/4" />
      </div>
    );
  }

  // — History list —
  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-shrink-0 items-center justify-between gap-2 border-b px-4 py-3 text-xs font-semibold text-muted-foreground">
        <span>{t('revision.header', { count: revisions.length })}</span>
        {revisions.length >= 2 && (
          <button
            onClick={() => navigate(`/books/${bookId}/chapters/${chapterId}/compare`)}
            className="inline-flex items-center gap-1 rounded-md border px-2 py-1 font-normal hover:text-primary"
          >
            <GitCompare className="h-3 w-3" /> {t('compare.open', { defaultValue: 'Compare' })}
          </button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto">
        {revisions.length === 0 && (
          <p className="p-4 text-xs text-muted-foreground italic">{t('revision.empty')}</p>
        )}
        {revisions.map((r, i) => (
          <div key={r.revision_id} className="border-b px-4 py-3 text-xs hover:bg-card">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">{i === 0 ? t('revision.current') : `v${revisions.length - i}`}</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => void handleView(r)}
                  disabled={previewLoading}
                  className="text-muted-foreground hover:text-foreground"
                >
                  {t('revision.view')}
                </button>
                {i > 0 && (
                  <button
                    onClick={() => setRestoreTarget(r)}
                    className="text-primary hover:underline"
                  >
                    {t('revision.restore')}
                  </button>
                )}
              </div>
            </div>
            {r.message && <p className="mt-0.5 text-muted-foreground">{r.message}</p>}
            <p className="mt-0.5 text-muted-foreground">{new Date(r.created_at).toLocaleString()}</p>
          </div>
        ))}
      </div>

      <ConfirmDialog
        open={!!restoreTarget}
        onOpenChange={(open) => { if (!open) setRestoreTarget(null); }}
        title={t('revision.confirm_title')}
        description={t('revision.confirm_desc')}
        confirmLabel={t('revision.restore')}
        variant="destructive"
        onConfirm={() => void handleRestore()}
      />

      {/* Esc to close preview */}
      {preview && <EscListener onEsc={() => setPreview(null)} />}

      {/* Full-screen preview overlay */}
      {preview && (
        <div className="fixed inset-0 z-50 flex flex-col bg-background">
          {/* Preview toolbar */}
          <div className="flex h-12 flex-shrink-0 items-center justify-between border-b bg-card px-4">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setPreview(null)}
                className="rounded p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
                title={t('revision.close_preview')}
              >
                <X className="h-4 w-4" />
              </button>
              <div>
                <p className="text-xs font-medium">
                  {t('revision.preview')}
                  <span className="ml-2 text-muted-foreground font-normal">
                    {new Date(preview.revision.created_at).toLocaleString()}
                  </span>
                </p>
                {preview.revision.message && (
                  <p className="text-[10px] text-muted-foreground">{preview.revision.message}</p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setRestoreTarget(preview.revision)}
                className="inline-flex items-center gap-1.5 rounded-md border border-primary/40 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                {t('revision.restore_version')}
              </button>
            </div>
          </div>

          {/* Reading area — ContentRenderer in compact mode */}
          <div className="flex flex-1 justify-center overflow-y-auto px-6 py-10">
            <div className="w-full max-w-4xl">
              {preview.blocks.length > 0 ? (
                <ContentRenderer blocks={preview.blocks} mode="compact" />
              ) : (
                <p className="text-center text-sm text-muted-foreground italic">{t('revision.empty_revision')}</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function EscListener({ onEsc }: { onEsc: () => void }) {
  const handler = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onEsc();
  }, [onEsc]);

  useEffect(() => {
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [handler]);

  return null;
}
