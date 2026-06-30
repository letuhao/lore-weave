import { useTranslation } from 'react-i18next';
import { Languages, Loader2 } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { getLanguageName } from '@/lib/languages';
import { glossaryApi } from '@/features/glossary/api';
import { booksApi } from '@/features/books/api';
import { useGlossaryDisplayLanguage } from '@/features/glossary/hooks/useGlossaryDisplayLanguage';
import { useAsOf } from '../context/AsOfContext';
import { useCanonical, useCanonicalTranslation } from '../hooks/useTemporalReads';
import type { TemporalSurfaceProps } from './CanonicalCard';

// X6c — Per-episode / as-of translation (spec §6B/§7.6). Shows the entity's AS-OF folded canonical
// translated into the reader's display language, on-demand + cached immutable per (content,lang).
// The display language is the SAME per-book preference the glossary browser uses
// (useGlossaryDisplayLanguage) → the two stay in lockstep. When the reader picks the book's
// original/as-authored language, apiDisplayLanguage is undefined → the original canonical shows
// (no LLM). Otherwise the KAL translates via translation-service (BYOK, provider-registry).

export function EpisodeTranslationPanel({ bookId, entityId }: TemporalSurfaceProps) {
  const { t } = useTranslation('knowledge');
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const { asOf } = useAsOf();

  const bookQuery = useQuery({
    queryKey: ['book-orig-lang', userId, bookId],
    queryFn: () => booksApi.getBook(accessToken!, bookId),
    enabled: !!accessToken && !!bookId,
    staleTime: 60_000,
  });
  const bookOriginalLanguage = bookQuery.data?.original_language ?? undefined;

  const { displayLanguage, setDisplayLanguage, apiDisplayLanguage } = useGlossaryDisplayLanguage(
    bookId,
    bookOriginalLanguage,
  );

  const { data: langs } = useQuery({
    queryKey: ['glossary-translation-languages', userId, bookId],
    queryFn: () => glossaryApi.listTranslationLanguages(bookId, accessToken!),
    enabled: !!accessToken && !!bookId,
    staleTime: 60_000,
  });

  // Gate translation until the book's original language is known — otherwise a saved display-pref
  // that equals the source language would briefly fire a wasteful same-language translate before
  // bookOriginalLanguage loads (apiDisplayLanguage can't yet tell it IS the source).
  const effLang = bookQuery.isLoading ? undefined : apiDisplayLanguage;
  const showingTranslation = !!effLang;
  const original = useCanonical(bookId, entityId, asOf);
  const tr = useCanonicalTranslation(bookId, entityId, effLang, asOf);

  // Selector options: the original/as-authored option + each translation language with coverage.
  const options: { code: string; label: string }[] = [
    {
      code: bookOriginalLanguage ?? '',
      label: t('temporal.translation.langOriginal', {
        lang: bookOriginalLanguage
          ? getLanguageName(bookOriginalLanguage)
          : t('temporal.translation.asAuthored', 'as authored'),
        defaultValue: 'Original ({{lang}})',
      }),
    },
  ];
  const seen = new Set(options.map((o) => o.code));
  for (const code of langs?.languages ?? []) {
    if (seen.has(code)) continue;
    seen.add(code);
    options.push({ code, label: getLanguageName(code) });
  }
  if (displayLanguage && !seen.has(displayLanguage)) {
    options.push({ code: displayLanguage, label: getLanguageName(displayLanguage) });
  }

  const asOfLabel =
    asOf === undefined || asOf < 0
      ? t('temporal.translation.asOfHead', 'latest')
      : t('temporal.translation.asOfChapter', { n: asOf, defaultValue: 'chapter {{n}}' });

  return (
    <section data-testid="episode-translation" className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground">
        <Languages className="h-3 w-3" aria-hidden />
        <span>{t('temporal.translation.title', 'Per-episode context')}</span>
        <span className="text-foreground/60" data-testid="episode-translation-asof">
          {t('temporal.translation.asOfLabel', { label: asOfLabel, defaultValue: 'as of {{label}}' })}
        </span>
        <select
          data-testid="episode-translation-language"
          aria-label={t('temporal.translation.languageLabel', 'Display language')}
          value={displayLanguage}
          onChange={(e) => setDisplayLanguage(e.target.value)}
          className="ml-auto h-7 rounded-md border bg-background px-1.5 text-[11px] normal-case tracking-normal focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
        >
          {options.map((o) => (
            <option key={o.code} value={o.code}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {showingTranslation ? (
        <TranslationBody t={t} tr={tr} />
      ) : (
        <OriginalBody t={t} original={original} />
      )}
    </section>
  );
}

function OriginalBody({
  t,
  original,
}: {
  t: ReturnType<typeof useTranslation>['t'];
  original: ReturnType<typeof useCanonical>;
}) {
  if (original.isLoading) return <Skeleton />;
  if (original.error) return <ErrorNote t={t} message={original.error.message} />;
  const content = original.canonical?.content?.trim() ?? '';
  if (!content) return <EmptyNote t={t} />;
  return (
    <p className="whitespace-pre-wrap text-[12px] leading-relaxed" data-testid="episode-translation-content">
      {content}
    </p>
  );
}

function TranslationBody({
  t,
  tr,
}: {
  t: ReturnType<typeof useTranslation>['t'];
  tr: ReturnType<typeof useCanonicalTranslation>;
}) {
  if (tr.isLoading) return <Skeleton />;
  if (tr.error) return <ErrorNote t={t} message={tr.error.message} />;
  const data = tr.translation;
  if (!data || data.status === 'unbuildable') return <EmptyNote t={t} />;
  const content = data.content?.trim() ?? '';

  if (data.status === 'ready') {
    return (
      <div className="space-y-1.5">
        <span
          className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground"
          data-testid="episode-translation-badge"
        >
          {data.cached
            ? t('temporal.translation.badgeCached', 'translated · cached')
            : t('temporal.translation.badgeFresh', 'translated')}
        </span>
        {content ? (
          <p className="whitespace-pre-wrap text-[12px] leading-relaxed" data-testid="episode-translation-content">
            {content}
          </p>
        ) : (
          <EmptyNote t={t} />
        )}
      </div>
    );
  }

  if (data.status === 'failed') {
    const msg =
      data.error_code === 'no_model'
        ? t('temporal.translation.failNoModel', 'No translation model set. Choose one in Translation Settings to see the translated context.')
        : data.error_code === 'quota'
          ? t('temporal.translation.failQuota', 'Translation is unavailable — provider quota exhausted.')
          : t('temporal.translation.failProvider', 'Translation failed. Showing the original context for now.');
    return (
      <div className="space-y-1.5" data-testid="episode-translation-failed">
        <p className="rounded-md border border-dashed px-2.5 py-1.5 text-[10px] text-muted-foreground">{msg}</p>
        {content && (
          <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-foreground/90" data-testid="episode-translation-content">
            {content}
          </p>
        )}
      </div>
    );
  }

  // status === 'translating' — the single-flight fill is running; the hook polls. Show the
  // original content with a translating indicator (the translated text swaps in on the next poll).
  return (
    <div className="space-y-1.5" data-testid="episode-translation-translating">
      <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
        {t('temporal.translation.translating', 'Translating… first view may take a moment')}
      </span>
      {content && (
        <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-foreground/70" data-testid="episode-translation-content">
          {content}
        </p>
      )}
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-2" data-testid="episode-translation-loading">
      {[0, 1].map((i) => (
        <div key={i} className="h-4 animate-pulse rounded bg-muted/40" />
      ))}
    </div>
  );
}

function ErrorNote({ t, message }: { t: ReturnType<typeof useTranslation>['t']; message: string }) {
  return (
    <div
      role="alert"
      className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
      data-testid="episode-translation-error"
    >
      {t('temporal.translation.error', { error: message, defaultValue: 'Failed to load context: {{error}}' })}
    </div>
  );
}

function EmptyNote({ t }: { t: ReturnType<typeof useTranslation>['t'] }) {
  return (
    <p
      className="rounded-md border border-dashed px-3 py-4 text-center text-[12px] text-muted-foreground"
      data-testid="episode-translation-empty"
    >
      {t('temporal.translation.empty', 'No as-of context available for this point in the story.')}
    </p>
  );
}
