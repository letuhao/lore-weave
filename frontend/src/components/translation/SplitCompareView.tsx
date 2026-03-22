import { useEffect, useState } from 'react';
import type { ChapterTranslation } from '@/features/translation/api';
import type { VersionSummary } from '@/features/translation/versionsApi';
import { versionsApi } from '@/features/translation/versionsApi';
import { booksApi } from '@/features/books/api';
import { Skeleton } from '@/components/ui/skeleton';

type Props = {
  token: string;
  bookId: string;
  chapterId: string;
  version: VersionSummary;
  originalLanguage?: string | null;
};

export function SplitCompareView({ token, bookId, chapterId, version, originalLanguage }: Props) {
  const [originalBody, setOriginalBody] = useState<string | null>(null);
  const [ct, setCt] = useState<ChapterTranslation | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      booksApi.getDraft(token, bookId, chapterId).then((d) => setOriginalBody(d.body)),
      versionsApi.getChapterVersion(token, chapterId, version.id).then(setCt),
    ]).finally(() => setLoading(false));
  }, [token, bookId, chapterId, version.id]);

  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-4">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-4">
      <div className="space-y-1">
        <p className="text-xs font-medium text-muted-foreground">
          Original{originalLanguage ? ` (${originalLanguage})` : ''}
        </p>
        <div className="max-h-[70vh] overflow-y-auto whitespace-pre-wrap rounded border bg-muted p-4 text-sm leading-relaxed">
          {originalBody ?? <span className="text-muted-foreground">No draft content</span>}
        </div>
      </div>
      <div className="space-y-1">
        <p className="text-xs font-medium text-muted-foreground">
          {ct?.target_language ?? 'Translation'} v{version.version_num}
          {version.is_active && <span className="ml-1 text-green-600">● Active</span>}
        </p>
        <div className="max-h-[70vh] overflow-y-auto whitespace-pre-wrap rounded border bg-muted p-4 text-sm leading-relaxed">
          {ct?.status === 'completed'
            ? (ct.translated_body ?? '')
            : <span className="text-muted-foreground">{ct?.status ?? 'loading…'}</span>
          }
        </div>
      </div>
    </div>
  );
}
