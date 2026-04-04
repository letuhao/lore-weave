import { useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { versionsApi, type ChapterTranslation } from '../api';

interface SplitCompareViewProps {
  bookId: string;
  chapterId: string;
  versionId: string;
  originalLanguage?: string;
  targetLanguage: string;
}

export function SplitCompareView({ bookId, chapterId, versionId, originalLanguage, targetLanguage }: SplitCompareViewProps) {
  const { accessToken } = useAuth();
  const [originalBody, setOriginalBody] = useState<string | null>(null);
  const [translatedBody, setTranslatedBody] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!accessToken) return;
    let mounted = true;
    setLoading(true);

    Promise.all([
      booksApi.getDraft(accessToken, bookId, chapterId)
        .then((d) => d.text_content || (typeof d.body === 'string' ? d.body : JSON.stringify(d.body)))
        .catch(() => '(Failed to load original)'),
      versionsApi.getChapterVersion(accessToken, chapterId, versionId)
        .then((v) => v.translated_body || '(No translated content)')
        .catch(() => '(Failed to load translation)'),
    ]).then(([orig, trans]) => {
      if (mounted) {
        setOriginalBody(orig);
        setTranslatedBody(trans);
      }
    }).finally(() => {
      if (mounted) setLoading(false);
    });

    return () => { mounted = false; };
  }, [accessToken, bookId, chapterId, versionId]);

  if (loading) {
    return (
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 p-6"><div className="h-64 animate-pulse rounded bg-muted" /></div>
        <div className="w-px bg-border" />
        <div className="flex-1 p-6"><div className="h-64 animate-pulse rounded bg-muted" /></div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Original pane */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="shrink-0 border-b border-border bg-card px-4 py-2.5">
          <p className="text-[11px] font-semibold text-primary">
            Original &mdash; {originalLanguage ?? 'Source'}
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          <div className="whitespace-pre-wrap font-serif text-[15px] leading-[2.0] text-foreground/85">
            {originalBody}
          </div>
        </div>
      </div>

      {/* Divider */}
      <div className="relative w-px shrink-0 bg-border">
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded-full border border-border bg-card px-2 py-0.5 text-[9px] text-muted-foreground">
          {originalLanguage ?? '?'} &rarr; {targetLanguage}
        </div>
      </div>

      {/* Translation pane */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="shrink-0 border-b border-border bg-card px-4 py-2.5">
          <p className="text-[11px] font-semibold text-accent">
            Translation &mdash; {targetLanguage}
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          <div className="whitespace-pre-wrap font-serif text-[15px] leading-[1.9] text-foreground/90">
            {translatedBody}
          </div>
        </div>
      </div>
    </div>
  );
}
