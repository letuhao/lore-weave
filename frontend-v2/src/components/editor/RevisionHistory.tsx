import { useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { Skeleton } from '@/components/shared/Skeleton';

type Revision = { revision_id: string; created_at: string; message?: string };

export function RevisionHistory({ bookId, chapterId, onRestore }: {
  bookId: string; chapterId: string; onRestore: () => void;
}) {
  const { accessToken } = useAuth();
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    booksApi.listRevisions(accessToken, bookId, chapterId, { limit: 20, offset: 0 })
      .then((r) => setRevisions(r.items))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [accessToken, bookId, chapterId]);

  const handleRestore = async (revId: string) => {
    if (!accessToken) return;
    await booksApi.restoreRevision(accessToken, bookId, chapterId, revId);
    onRestore();
  };

  if (loading) return <div className="space-y-2 p-4"><Skeleton className="h-8 w-full" /><Skeleton className="h-8 w-full" /></div>;

  return (
    <div className="flex flex-col">
      <div className="border-b px-4 py-3 text-xs font-semibold text-muted-foreground">
        Revision History · {revisions.length}
      </div>
      <div className="flex-1 overflow-y-auto">
        {revisions.length === 0 && (
          <p className="p-4 text-xs text-muted-foreground">No revisions yet. Save to create one.</p>
        )}
        {revisions.map((r, i) => (
          <div key={r.revision_id} className="border-b px-4 py-3 text-xs hover:bg-card">
            <div className="flex items-center justify-between">
              <span className="font-medium">{i === 0 ? 'Latest' : `v${revisions.length - i}`}</span>
              {i > 0 && (
                <button
                  onClick={() => void handleRestore(r.revision_id)}
                  className="text-primary hover:underline"
                >
                  Restore
                </button>
              )}
            </div>
            {r.message && <p className="mt-0.5 text-muted-foreground">{r.message}</p>}
            <p className="mt-0.5 text-muted-foreground">{new Date(r.created_at).toLocaleString()}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
