import { useEffect, useState } from 'react';
import { X, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { Skeleton } from '@/components/shared/Skeleton';
import { ConfirmDialog } from '@/components/shared';
import { ChapterReadView } from '@/components/shared/ChapterReadView';

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
    try {
      await booksApi.restoreRevision(accessToken, bookId, chapterId, restoreTarget.revision_id);
      setRestoreTarget(null);
      setPreview(null);
      toast.success('Revision restored');
      onRestore();
    } catch (e) {
      toast.error((e as Error).message);
    }
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

      {/* Full-screen preview overlay — rendered via fixed positioning so it
          escapes the constrained 300px right panel */}
      {preview && (
        <div className="fixed inset-0 z-50 flex flex-col bg-background">
          {/* Preview toolbar */}
          <div className="flex h-12 flex-shrink-0 items-center justify-between border-b bg-card px-4">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setPreview(null)}
                className="rounded p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
                title="Close preview"
              >
                <X className="h-4 w-4" />
              </button>
              <div>
                <p className="text-xs font-medium">
                  Revision preview
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
              <span className="text-[10px] text-muted-foreground">
                {wordCount(preview.body).toLocaleString()} words
              </span>
              <button
                onClick={() => setRestoreTarget(preview.revision)}
                className="inline-flex items-center gap-1.5 rounded-md border border-primary/40 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Restore this version
              </button>
            </div>
          </div>

          {/* Reading area — same layout as ReaderPage */}
          <div className="flex flex-1 justify-center overflow-y-auto px-6 py-10">
            <ChapterReadView body={preview.body} />
          </div>
        </div>
      )}
    </div>
  );
}
