import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Search, BookOpen, Clock, ChevronRight } from 'lucide-react';
import type { JSONContent } from '@tiptap/react';
import { useAuth } from '@/auth';
import { wikiApi } from '@/features/wiki/api';
import type { WikiArticleListItem, WikiArticleDetail, WikiInfoboxAttr } from '@/features/wiki/types';
import { ContentRenderer } from '@/components/reader/ContentRenderer';
import { Skeleton } from '@/components/shared/Skeleton';
import { EmptyState } from '@/components/shared';
import { cn } from '@/lib/utils';

/* ── Infobox ─────────────────────────────────────────────────────────────── */

function WikiInfobox({ attrs, kindName, displayName }: {
  attrs: WikiInfoboxAttr[];
  kindName: string;
  displayName: string;
}) {
  const { t } = useTranslation('wiki');
  const visibleAttrs = attrs.filter(a => a.original_value || a.translations.length > 0);
  if (visibleAttrs.length === 0) return null;

  return (
    <div className="float-right ml-5 mb-4 w-[260px] rounded-lg border bg-background p-4">
      <div className="mb-3 text-center">
        <div className="mx-auto mb-2 flex h-16 w-16 items-center justify-center rounded-lg border bg-gradient-to-br from-amber-900/30 to-amber-950/20">
          <span className="font-serif text-2xl text-primary">{displayName.charAt(0)}</span>
        </div>
        <span className="font-serif text-sm font-semibold">{displayName}</span>
        <br />
        <span className="text-[11px] text-muted-foreground">{kindName}</span>
      </div>
      {visibleAttrs.map(attr => (
        <div key={attr.attr_value_id} className="flex border-b border-border py-1.5 text-xs last:border-b-0">
          <span className="w-[90px] shrink-0 font-medium text-muted-foreground">
            {attr.attribute_def.name}
          </span>
          <span>{attr.original_value || attr.translations[0]?.value || ''}</span>
        </div>
      ))}
    </div>
  );
}

/* ── Table of Contents ───────────────────────────────────────────────────── */

function extractHeadings(bodyJson: Record<string, unknown>): { text: string; level: number; id: string }[] {
  const content = (bodyJson as { content?: JSONContent[] }).content;
  if (!content) return [];
  return content
    .filter(node => node.type === 'heading')
    .map((node, i) => {
      const text = (node.content as JSONContent[] | undefined)
        ?.map(c => (c as { text?: string }).text || '')
        .join('') || '';
      const level = (node.attrs as { level?: number })?.level ?? 2;
      return { text, level, id: `heading-${i}` };
    });
}

function WikiToC({ headings }: { headings: { text: string; level: number; id: string }[] }) {
  const { t } = useTranslation('wiki');
  if (headings.length === 0) return null;

  return (
    <div className="rounded-lg border bg-card">
      <div className="border-b px-3 py-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('onThisPage')}
        </span>
      </div>
      <div className="py-1">
        {headings.map(h => (
          <a
            key={h.id}
            href={`#${h.id}`}
            className={cn(
              'block border-l-2 border-transparent px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-card-hover hover:text-foreground',
              h.level > 2 && 'pl-6 text-[11px]',
            )}
          >
            {h.text}
          </a>
        ))}
      </div>
    </div>
  );
}

/* ── Sidebar article list ────────────────────────────────────────────────── */

function WikiSidebar({ articles, selectedId, onSelect, kinds, kindFilter, onKindFilter, search, onSearch, total, t }: {
  articles: WikiArticleListItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  kinds: { code: string; name: string; icon: string; color: string }[];
  kindFilter: string;
  onKindFilter: (k: string) => void;
  search: string;
  onSearch: (s: string) => void;
  total: number;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  const grouped = useMemo(() => {
    const groups: Record<string, WikiArticleListItem[]> = {};
    for (const a of articles) {
      const key = a.kind.name;
      if (!groups[key]) groups[key] = [];
      groups[key].push(a);
    }
    return groups;
  }, [articles]);

  return (
    <div className="flex h-full flex-col rounded-l-lg border-r bg-card">
      {/* Header */}
      <div className="border-b p-3">
        <div className="mb-1 flex items-center gap-1.5">
          <BookOpen className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs font-semibold">{t('title')}</span>
        </div>
        <span className="text-[10px] text-muted-foreground">
          {t('articles', { count: total })}
        </span>
        <div className="relative mt-2">
          <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
          <input
            className="h-7 w-full rounded-md border bg-background pl-6 pr-2 text-[11px] placeholder:text-muted-foreground/40 focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
            placeholder={t('search')}
            value={search}
            onChange={e => onSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Kind filter chips */}
      {kinds.length > 1 && (
        <div className="flex flex-wrap gap-1 border-b px-3 py-2">
          <button
            onClick={() => onKindFilter('')}
            className={cn(
              'rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors',
              !kindFilter ? 'bg-primary/15 text-primary' : 'bg-secondary text-muted-foreground hover:text-foreground',
            )}
          >
            {t('allKinds')}
          </button>
          {kinds.map(k => (
            <button
              key={k.code}
              onClick={() => onKindFilter(k.code === kindFilter ? '' : k.code)}
              className={cn(
                'rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors',
                kindFilter === k.code ? 'text-primary' : 'text-muted-foreground hover:text-foreground',
              )}
              style={kindFilter === k.code ? { backgroundColor: k.color + '18', color: k.color } : { backgroundColor: 'var(--secondary)' }}
            >
              {k.icon} {k.name}
            </button>
          ))}
        </div>
      )}

      {/* Article list grouped by kind */}
      <div className="flex-1 overflow-y-auto py-1">
        {Object.entries(grouped).map(([kindName, items]) => (
          <div key={kindName}>
            <div className="px-3 pb-1 pt-2 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">
              {kindName}
            </div>
            {items.map(a => (
              <button
                key={a.article_id}
                onClick={() => onSelect(a.article_id)}
                className={cn(
                  'flex w-full items-center gap-2 border-b border-border px-3 py-2 text-left text-[13px] transition-colors last:border-b-0',
                  selectedId === a.article_id
                    ? 'border-l-2 border-l-primary bg-primary/8'
                    : 'hover:bg-card-hover',
                )}
              >
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: a.kind.color }}
                />
                <span className={cn('truncate', selectedId === a.article_id && 'font-medium')}>
                  {a.display_name || 'Untitled'}
                </span>
                {a.status === 'draft' && (
                  <span className="ml-auto shrink-0 rounded-full bg-amber-400/12 px-1.5 py-0.5 text-[9px] font-medium text-amber-400">
                    {t('draft')}
                  </span>
                )}
              </button>
            ))}
          </div>
        ))}
        {articles.length === 0 && (
          <div className="p-4 text-center text-xs text-muted-foreground">
            {search ? t('noMatch') : t('noArticles')}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Article view ────────────────────────────────────────────────────────── */

function WikiArticleView({ bookId, articleId }: { bookId: string; articleId: string }) {
  const { accessToken } = useAuth();
  const { t } = useTranslation('wiki');

  const { data: article, isLoading } = useQuery({
    queryKey: ['wiki-article', bookId, articleId],
    queryFn: () => wikiApi.getArticle(bookId, articleId, accessToken!),
    enabled: !!accessToken && !!articleId,
  });

  if (isLoading) {
    return (
      <div className="p-6">
        <Skeleton className="mb-4 h-8 w-48" />
        <Skeleton className="mb-2 h-4 w-full" />
        <Skeleton className="mb-2 h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    );
  }

  if (!article) return null;

  const headings = extractHeadings(article.body_json);
  const blocks = (article.body_json as { content?: JSONContent[] }).content ?? [];
  const hasContent = blocks.length > 0;
  const updatedDate = new Date(article.updated_at).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  });

  return (
    <div className="flex gap-0">
      {/* Article body */}
      <div className="min-w-0 flex-1 border-x">
        {/* Header */}
        <div className="px-6 pt-5">
          <div className="mb-1 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="font-serif text-xl font-semibold">{article.display_name}</h2>
              <span
                className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
                style={{ backgroundColor: article.kind.color + '18', color: article.kind.color }}
              >
                {article.kind.name}
              </span>
            </div>
            <div className="flex gap-1">
              <button className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium hover:bg-secondary">
                <Clock className="h-3 w-3" />
                {t('history')}
              </button>
            </div>
          </div>
          <p className="mb-4 text-[11px] text-muted-foreground">
            {t('lastEdited')} {updatedDate} &middot; {t('revisions', { count: article.revision_count })}
          </p>
        </div>

        {/* Body */}
        <div className="px-6 pb-6">
          {article.infobox.length > 0 && (
            <WikiInfobox
              attrs={article.infobox}
              kindName={article.kind.name}
              displayName={article.display_name}
            />
          )}

          {hasContent ? (
            <div className="wiki-article-body">
              <ContentRenderer blocks={blocks} mode="full" />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground italic">{t('noContent')}</p>
          )}

          <div className="clear-both" />
        </div>
      </div>

      {/* Right: ToC */}
      {headings.length > 0 && (
        <div className="hidden w-[200px] shrink-0 lg:block">
          <div className="sticky top-4 p-2">
            <WikiToC headings={headings} />
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Main WikiTab ────────────────────────────────────────────────────────── */

export function WikiTab({ bookId }: { bookId: string }) {
  const { accessToken } = useAuth();
  const { t } = useTranslation('wiki');
  const [search, setSearch] = useState('');
  const [kindFilter, setKindFilter] = useState('');
  const [selectedArticleId, setSelectedArticleId] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['wiki-articles', bookId, search, kindFilter],
    queryFn: () => wikiApi.listArticles(bookId, {
      search: search || undefined,
      kind_code: kindFilter || undefined,
      limit: 100,
    }, accessToken!),
    enabled: !!accessToken,
  });

  const articles = data?.items ?? [];
  const total = data?.total ?? 0;

  // Extract unique kinds for filter chips
  const kinds = useMemo(() => {
    const seen = new Map<string, WikiArticleListItem['kind']>();
    for (const a of articles) {
      if (!seen.has(a.kind.code)) seen.set(a.kind.code, a.kind);
    }
    return Array.from(seen.values());
  }, [articles]);

  // Auto-select first article
  const effectiveSelected = selectedArticleId && articles.some(a => a.article_id === selectedArticleId)
    ? selectedArticleId
    : articles[0]?.article_id ?? null;

  if (isLoading) {
    return (
      <div className="rounded-lg border p-8">
        <div className="flex gap-4">
          <Skeleton className="h-[400px] w-[220px]" />
          <Skeleton className="h-[400px] flex-1" />
        </div>
      </div>
    );
  }

  if (total === 0 && !search && !kindFilter) {
    return (
      <EmptyState
        icon={BookOpen}
        title={t('noArticles')}
        description={t('noArticlesDesc')}
      />
    );
  }

  return (
    <div className="flex overflow-hidden rounded-lg border" style={{ minHeight: 500 }}>
      {/* Left sidebar */}
      <div className="w-[220px] shrink-0">
        <WikiSidebar
          articles={articles}
          selectedId={effectiveSelected}
          onSelect={setSelectedArticleId}
          kinds={kinds}
          kindFilter={kindFilter}
          onKindFilter={setKindFilter}
          search={search}
          onSearch={setSearch}
          total={total}
          t={t}
        />
      </div>

      {/* Article view */}
      <div className="min-w-0 flex-1">
        {effectiveSelected ? (
          <WikiArticleView bookId={bookId} articleId={effectiveSelected} />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            {t('noMatch')}
          </div>
        )}
      </div>
    </div>
  );
}
