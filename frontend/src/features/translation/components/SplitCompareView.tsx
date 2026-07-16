import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { versionsApi, type ChapterTranslation } from '../api';
import { ContentRenderer } from '@/components/reader/ContentRenderer';
import type { JSONContent } from '@tiptap/react';

interface SplitCompareViewProps {
  bookId: string;
  chapterId: string;
  versionId: string;
  originalLanguage?: string;
  targetLanguage: string;
}

export function SplitCompareView({ bookId, chapterId, versionId, originalLanguage, targetLanguage }: SplitCompareViewProps) {
  const { t } = useTranslation('translation');
  const { accessToken } = useAuth();
  const [originalBody, setOriginalBody] = useState<string | null>(null);
  const [originalBlocks, setOriginalBlocks] = useState<JSONContent[] | null>(null);
  const [translatedBody, setTranslatedBody] = useState<string | null>(null);
  const [translatedBlocks, setTranslatedBlocks] = useState<JSONContent[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!accessToken) return;
    let mounted = true;
    setLoading(true);

    Promise.all([
      booksApi.getDraft(accessToken, bookId, chapterId).catch(() => null),
      versionsApi.getChapterVersion(accessToken, chapterId, versionId).catch(() => null),
    ]).then(([draft, ver]) => {
      if (!mounted) return;
      // Original
      if (draft?.body && typeof draft.body === 'object' && Array.isArray((draft.body as any).content)) {
        setOriginalBlocks((draft.body as any).content);
      }
      setOriginalBody(draft?.text_content || (typeof draft?.body === 'string' ? draft.body : null));
      // Translation
      if (ver?.translated_body_format === 'json' && Array.isArray(ver.translated_body_json)) {
        setTranslatedBlocks(ver.translated_body_json as JSONContent[]);
      }
      setTranslatedBody(ver?.translated_body || null);
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
            {t('compare.original_label', { lang: originalLanguage ?? t('compare.source_fallback') })}
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          {originalBlocks ? (
            <div className="mx-auto max-w-[680px]"><ContentRenderer blocks={originalBlocks} mode="compact" /></div>
          ) : originalBody ? (
            <div className="whitespace-pre-wrap font-serif text-[15px] leading-[2.0] text-foreground/85">{originalBody}</div>
          ) : (
            // S6: a failed getDraft left this pane blank (the translation pane had a fallback,
            // this one did not) — show the same "unavailable" copy instead of empty space.
            <p className="text-sm text-muted-foreground">{t('compare.original_unavailable')}</p>
          )}
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
            {t('compare.translation_label', { lang: targetLanguage })}
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          {translatedBlocks ? (
            <div className="mx-auto max-w-[680px]"><ContentRenderer blocks={translatedBlocks} mode="compact" /></div>
          ) : (
            <div className="whitespace-pre-wrap font-serif text-[15px] leading-[1.9] text-foreground/90">
              {translatedBody || t('compare.no_translated')}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
