import { useEffect, useState } from 'react';
import { ArrowLeft, RotateCcw } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { Skeleton } from '@/components/shared/Skeleton';
import { ConfirmDialog } from '@/components/shared';

type Revision = { revision_id: string; created_at: string; message?: string };
type PreviewState = { revision: Revision; body: string } | null;

export function RevisionHistory({ bookId, chapterId, onRestore }: {
  bookId: string; chapterId: string; onRestore: () => void;
}) {
  const { accessToken } = useAuth();
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
      setPreview({ revision: rev, body: data.body });
    } catch { /* ignore */ }
    setPreviewLoading(false);
  };

  const handleRestore = async () => {
    if (!accessToken || !restoreTarget) return;
    await booksApi.restoreRevision(accessToken, bookId, chapterId, restoreTarget.revision_id);
    setRestoreTarget(null);
    setPreview(null);
    onRestore();
  };

  const wordCount = (text: string) =>
    text.trim() ? text.trim().split(/\s+/).length : 0;

  if (loading) {
    return (
      <div className="space-y-2 p-4">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-3/4" />
      </div>
    );
  }

  // — Preview pane —
  if (preview) {
    return (
      <div className="flex h-full flex-col">
        <div className="flex flex-shrink-0 items-center gap-2 border-b px-3 py-2">
          <button
            onClick={() => setPreview(null)}
            className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
            title="Back to history"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
          </button>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium">
              {new Date(preview.revision.created_at).toLocaleString()}
            </p>
            {preview.revision.message && (
              <p className="truncate text-[10px] text-muted-foreground">{preview.revision.message}</p>
            )}
          </div>
          <button
            onClick={() => setRestoreTarget(preview.revision)}
            className="flex items-center gap-1 rounded-md border border-primary/40 px-2 py-1 text-[10px] font-medium text-primary hover:bg-primary/10"
            title="Restore this version"
          >
            <RotateCcw className="h-3 w-3" />
            Restore
          </button>
        </div>
        <div className="flex-shrink-0 border-b px-3 py-1.5">
          <span className="text-[10px] text-muted-foreground">
            {wordCount(preview.body).toLocaleString()} words
          </span>
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-3">
          <pre className="whitespace-pre-wrap font-sans text-xs leading-[1.8] text-foreground/80">
            {preview.body || <span className="italic text-muted-foreground">Empty revision</span>}
          </pre>
        </div>

        <ConfirmDialog
          open={!!restoreTarget}
          onOpenChange={(open) => { if (!open) setRestoreTarget(null); }}
          title="Restore this revision?"
          description="This will overwrite your current draft with this older version and create a new revision entry. This cannot be undone."
          confirmLabel="Restore"
          variant="destructive"
          onConfirm={() => void handleRestore()}
        />
      </div>
    );
  }

  // — History list —
  return (
    <div className="flex h-full flex-col">
      <div className="flex-shrink-0 border-b px-4 py-3 text-xs font-semibold text-muted-foreground">
        Revision History · {revisions.length}
      </div>
      <div className="flex-1 overflow-y-auto">
        {revisions.length === 0 && (
          <p className="p-4 text-xs text-muted-foreground italic">No revisions yet. Save to create one.</p>
        )}
        {revisions.map((r, i) => (
          <div key={r.revision_id} className="border-b px-4 py-3 text-xs hover:bg-card">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">{i === 0 ? 'Current' : `v${revisions.length - i}`}</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => void handleView(r)}
                  disabled={previewLoading}
                  className="text-muted-foreground hover:text-foreground"
                >
                  View
                </button>
                {i > 0 && (
                  <button
                    onClick={() => setRestoreTarget(r)}
                    className="text-primary hover:underline"
                  >
                    Restore
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
        title="Restore this revision?"
        description="This will overwrite your current draft with this older version and create a new revision entry. This cannot be undone."
        confirmLabel="Restore"
        variant="destructive"
        onConfirm={() => void handleRestore()}
      />
    </div>
  );
}
