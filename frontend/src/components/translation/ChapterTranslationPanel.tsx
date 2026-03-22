import { useEffect, useState } from 'react';
import { translationApi, type ChapterTranslation } from '../../features/translation/api';
import { Skeleton } from '../ui/skeleton';
import { Alert, AlertDescription } from '../ui/alert';

type Props = {
  token: string;
  jobId: string;
  chapterId: string;
  chapterTitle?: string;
};

export function ChapterTranslationPanel({ token, jobId, chapterId, chapterTitle }: Props) {
  const [ct, setCt] = useState<ChapterTranslation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    translationApi.getChapterTranslation(token, jobId, chapterId)
      .then(setCt)
      .catch((e) => setError(e.message || 'Failed to load'))
      .finally(() => setLoading(false));
  }, [token, jobId, chapterId]);

  const title = chapterTitle || `Chapter ${chapterId.slice(0, 8)}`;

  return (
    <details className="rounded border">
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
        {loading ? title : (
          <>
            {ct?.status === 'completed' && <span className="mr-2 text-green-600">✓</span>}
            {ct?.status === 'failed' && <span className="mr-2 text-red-600">✗</span>}
            {(ct?.status === 'pending' || ct?.status === 'running') && <span className="mr-2 text-muted-foreground">◌</span>}
            {title}
            {ct?.input_tokens != null && ct?.output_tokens != null && (
              <span className="ml-2 text-xs text-muted-foreground">
                · {ct.input_tokens} → {ct.output_tokens} tokens
              </span>
            )}
          </>
        )}
      </summary>

      <div className="px-3 pb-3">
        {loading && <Skeleton className="h-24 w-full" />}
        {!loading && error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {!loading && !error && ct && (
          <>
            {(ct.status === 'pending' || ct.status === 'running') && (
              <p className="text-sm text-muted-foreground">Processing…</p>
            )}
            {ct.status === 'failed' && (
              <Alert variant="destructive">
                <AlertDescription>{ct.error_message || 'Translation failed'}</AlertDescription>
              </Alert>
            )}
            {ct.status === 'completed' && (
              <div className="whitespace-pre-wrap rounded border bg-muted p-3 text-sm max-h-96 overflow-y-auto">
                {ct.translated_body}
              </div>
            )}
          </>
        )}
      </div>
    </details>
  );
}
