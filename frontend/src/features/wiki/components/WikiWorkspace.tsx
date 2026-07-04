import { useState, useMemo, useDeferredValue } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Search, BookOpen, Clock, Pencil, Plus, Sparkles, RefreshCw, MessageSquare } from 'lucide-react';
import { toast } from 'sonner';
import type { JSONContent } from '@tiptap/react';
import { useAuth } from '@/auth';
import { useOptionalStudioHost } from '@/features/studio/host/StudioHostProvider';
import { wikiApi } from '@/features/wiki/api';
import type { WikiArticleListItem, WikiInfoboxAttr } from '@/features/wiki/types';
import { useWikiGenJob } from '@/features/wiki/hooks/useWikiGenJob';
import { GenerateWikiDialog } from '@/features/wiki/components/GenerateWikiDialog';
import { WikiGenJobBanner } from '@/features/wiki/components/WikiGenJobBanner';
import { WikiGenJobDetail } from '@/features/wiki/components/WikiGenJobDetail';
import { WikiGenBadge } from '@/features/wiki/components/WikiGenBadge';
import { VerifyFlagsPanel } from '@/features/wiki/components/VerifyFlagsPanel';
import { WikiSuggestionReview } from '@/features/wiki/components/WikiSuggestionReview';
import { KnowledgeUpdatesPanel } from '@/features/wiki/components/KnowledgeUpdatesPanel';
import { CreateArticleDialog } from '@/features/wiki/components/CreateArticleDialog';
import { useWikiStaleness } from '@/features/wiki/hooks/useWikiStaleness';
import { ContentRenderer } from '@/components/reader/ContentRenderer';
import { CitationProvider } from '@/components/reader/CitationContext';
import { Skeleton } from '@/components/shared/Skeleton';
import { EmptyState } from '@/components/shared';
import { cn } from '@/lib/utils';

// 15_wiki_panels.md B1 — the shared Wiki master-detail workspace (DOCK-2 "no fork"): the SAME
// implementation the classic `WikiTab` page (frontend/src/pages/book-tabs/WikiTab.tsx, now a
// thin caller) and the studio's `wiki` dock panel (WikiPanel.tsx) both render. Extracted from
// the former WikiTab.tsx verbatim except for the B1a DOCK-7 fixes noted inline below.

/* ── Infobox ─────────────────────────────────────────────────────────────── */

function WikiInfobox({ attrs, kindName, displayName }: {
  attrs: WikiInfoboxAttr[];
  kindName: string;
  displayName: string;
}) {
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

export function WikiSidebar({ articles, selectedId, onSelect, kinds, kindFilter, onKindFilter, search, onSearch, t, onGenerate, generating, onCreateOpen }: {
  articles: WikiArticleListItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  kinds: { code: string; name: string; icon: string; color: string }[];
  kindFilter: string;
  onKindFilter: (k: string) => void;
  search: string;
  onSearch: (s: string) => void;
  t: (key: string, opts?: Record<string, unknown>) => string;
  onGenerate?: () => void;
  generating?: boolean;
  onCreateOpen?: () => void;
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

  // W3 — "N articles · M by AI" split. M counts AI-authored articles
  // (generation_status set) within the loaded list, so it is always ≤ N.
  const aiCount = useMemo(
    () => articles.filter(a => a.generation_status != null).length,
    [articles],
  );

  return (
    <div className="flex h-full flex-col rounded-l-lg border-r bg-card">
      {/* Header */}
      <div className="border-b p-3">
        <div className="mb-1 flex items-center gap-1.5">
          <BookOpen className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs font-semibold">{t('title')}</span>
          <div className="ml-auto flex gap-1">
            {onGenerate && (
              <button
                onClick={onGenerate}
                disabled={generating}
                title={t('generateStubs')}
                data-testid="wiki-generate-trigger"
                className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground disabled:opacity-50"
              >
                <Sparkles className="h-3 w-3" />
              </button>
            )}
            {onCreateOpen && (
              <button
                onClick={onCreateOpen}
                title={t('createArticle')}
                className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground"
              >
                <Plus className="h-3 w-3" />
              </button>
            )}
          </div>
        </div>
        <span className="text-[10px] text-muted-foreground">
          {t('articles', { count: articles.length })}
          {aiCount > 0 && <> &middot; {t('aiSplit', { count: aiCount })}</>}
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
                data-testid="wiki-article-row"
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
                <span className="ml-auto flex shrink-0 items-center gap-1">
                  {a.is_knowledge_stale && (
                    <span className="rounded-full bg-amber-400/15 px-1.5 py-0.5 text-[9px] font-medium text-amber-500">
                      {t('staleness.outdated')}
                    </span>
                  )}
                  <WikiGenBadge status={a.generation_status} subtle />
                  {a.status === 'draft' && (
                    <span className="shrink-0 rounded-full bg-amber-400/12 px-1.5 py-0.5 text-[9px] font-medium text-amber-400">
                      {t('draft')}
                    </span>
                  )}
                </span>
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

export function WikiArticleView({ bookId, articleId, onRegenerate }: {
  bookId: string;
  articleId: string;
  onRegenerate: (entityId: string, displayName: string) => void;
}) {
  const { accessToken } = useAuth();
  const { t } = useTranslation('wiki');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showSugs, setShowSugs] = useState(false);
  // B1a (DOCK-7) — Edit/History would otherwise navigate() the whole app away from a mounted
  // studio; branch through the host when this view lives inside the `wiki` dock panel (mirrors
  // StepConfig.tsx / ExtractionWizard's jobs-list fix). Outside the studio (classic WikiTab page)
  // both fall back to the plain edit route, same as today.
  const studioHost = useOptionalStudioHost();
  const openEditor = (rightPanel?: 'history') => {
    if (studioHost) {
      studioHost.openPanel('wiki-editor', { params: { articleId, ...(rightPanel ? { rightPanel } : {}) } });
    } else {
      navigate(`/books/${bookId}/wiki/${articleId}/edit`);
    }
  };

  const { data: article, isLoading } = useQuery({
    queryKey: ['wiki-article', bookId, articleId],
    queryFn: () => wikiApi.getArticle(bookId, articleId, accessToken!),
    enabled: !!accessToken && !!articleId,
  });

  // W1 — pending suggestions for THIS article (the AI-regen clobber-guard files them).
  const { data: sugData } = useQuery({
    queryKey: ['wiki-suggestions', bookId, 'pending'],
    queryFn: () => wikiApi.listSuggestions(bookId, { status: 'pending', limit: 50 }, accessToken!),
    enabled: !!accessToken,
  });
  const articleSugs = (sugData?.items ?? []).filter((s) => s.article_id === articleId);

  const handleReviewSug = async (sugId: string, sugArticleId: string, action: 'accept' | 'reject') => {
    if (!accessToken) return;
    try {
      await wikiApi.reviewSuggestion(bookId, sugArticleId, sugId, { action }, accessToken);
      toast.success(action === 'accept' ? t('suggestionAccepted') : t('suggestionRejected'));
      queryClient.invalidateQueries({ queryKey: ['wiki-suggestions', bookId] });
      if (action === 'accept') {
        queryClient.invalidateQueries({ queryKey: ['wiki-article', bookId, sugArticleId] });
        queryClient.invalidateQueries({ queryKey: ['wiki-revisions', bookId, sugArticleId] });
        // /review-impl F1: accepting an AI-regen resolves staleness server-side
        // (status→regenerated + clears is_knowledge_stale) and changes the article's
        // generation_status — refresh the feed + sidebar badges so they don't go stale.
        queryClient.invalidateQueries({ queryKey: ['wiki-staleness', bookId] });
        queryClient.invalidateQueries({ queryKey: ['wiki-articles', bookId] });
      }
    } catch {
      toast.error(t('reviewFailed'));
    }
  };

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
              <WikiGenBadge status={article.generation_status} />
              {article.is_knowledge_stale && (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-400/15 px-2 py-0.5 text-[10px] font-medium text-amber-500">
                  {t('staleness.outdated')}
                </span>
              )}
              {articleSugs.length > 0 && (
                <button
                  type="button"
                  onClick={() => setShowSugs((v) => !v)}
                  className="inline-flex items-center gap-1 rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-medium text-primary hover:brightness-110"
                >
                  <MessageSquare className="h-3 w-3" />
                  {t('suggestions.pendingChip', { count: articleSugs.length })}
                </button>
              )}
            </div>
            <div className="flex gap-1">
              <button
                onClick={() => onRegenerate(article.entity_id, article.display_name)}
                title={t('gen.regenerate')}
                data-testid="wiki-regenerate"
                className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium hover:bg-secondary"
              >
                <RefreshCw className="h-3 w-3" />
                {t('gen.regenerate')}
              </button>
              <button
                onClick={() => openEditor()}
                className="inline-flex items-center gap-1 rounded-md bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground hover:brightness-110"
              >
                <Pencil className="h-3 w-3" />
                {t('edit')}
              </button>
              {/* B8 — was a dead button (no onClick at all, pre-existing); wired to open the
                  editor pre-focused on its History tab. Outside the studio there's no route
                  param for an initial tab, so it falls back to the plain edit route (still
                  strictly better than doing nothing). */}
              <button
                onClick={() => openEditor('history')}
                data-testid="wiki-history"
                className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium hover:bg-secondary"
              >
                <Clock className="h-3 w-3" />
                {t('history')}
              </button>
            </div>
          </div>
          <p className="mb-4 text-[11px] text-muted-foreground">
            {t('lastEdited')} {updatedDate} &middot; {t('revisions', { count: article.revision_count })}
          </p>

          {showSugs && articleSugs.length > 0 && (
            <div className="mb-4 rounded-lg border">
              <div className="border-b px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {t('suggestions.pendingTitle', { count: articleSugs.length })}
              </div>
              {articleSugs.map((sug) => (
                <WikiSuggestionReview
                  key={sug.suggestion_id}
                  suggestion={sug}
                  currentBodyJson={article.body_json}
                  bookId={bookId}
                  onAccept={() => handleReviewSug(sug.suggestion_id, sug.article_id, 'accept')}
                  onReject={() => handleReviewSug(sug.suggestion_id, sug.article_id, 'reject')}
                />
              ))}
            </div>
          )}
        </div>

        {/* Body */}
        <div className="px-6 pb-6">
          <VerifyFlagsPanel
            provenance={article.generation_provenance}
            blocked={article.generation_status === 'blocked'}
          />
          {article.infobox.length > 0 && (
            <WikiInfobox
              attrs={article.infobox}
              kindName={article.kind.name}
              displayName={article.display_name}
            />
          )}

          {hasContent ? (
            <div className="wiki-article-body">
              <CitationProvider bookId={bookId}>
                <ContentRenderer blocks={blocks} mode="full" />
              </CitationProvider>
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

/* ── Main WikiWorkspace ──────────────────────────────────────────────────── */

export function WikiWorkspace({ bookId }: { bookId: string }) {
  const { accessToken } = useAuth();
  const { t } = useTranslation('wiki');
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [kindFilter, setKindFilter] = useState('');
  const [selectedArticleId, setSelectedArticleId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [genOpen, setGenOpen] = useState(false);
  // wiki-llm M7b-2b/Phase-2b — set when the dialog is opened to REGENERATE
  // specific entities (single article OR a batch from the change-feed); null =
  // batch generate-by-kind via the Sparkles button.
  const [regenTarget, setRegenTarget] = useState<{ entity_ids: string[]; name: string } | null>(null);
  const [knowledgeOpen, setKnowledgeOpen] = useState(false);
  // wiki-llm M7b-2a — the LLM-gen job controller (poll + trigger + resume/cancel).
  const { job, isActive, busy, trigger, resume, cancel } = useWikiGenJob(bookId);
  // wiki-llm Phase-2b — the "Knowledge updates" change-feed count (badge).
  const { count: staleCount } = useWikiStaleness(bookId);

  const openBatchGenerate = () => { setRegenTarget(null); setGenOpen(true); };
  const openRegenerate = (entity_id: string, name: string) => {
    setRegenTarget({ entity_ids: [entity_id], name });
    setGenOpen(true);
  };
  const openBatchRegenerate = (entity_ids: string[], name: string) => {
    setRegenTarget({ entity_ids, name });
    setGenOpen(true);
  };

  const { data, isLoading } = useQuery({
    queryKey: ['wiki-articles', bookId, deferredSearch, kindFilter],
    queryFn: () => wikiApi.listArticles(bookId, {
      search: deferredSearch || undefined,
      kind_code: kindFilter || undefined,
      limit: 100,
    }, accessToken!),
    enabled: !!accessToken,
  });

  const articles = data?.items ?? [];
  const total = data?.total ?? 0;

  const kinds = useMemo(() => {
    const seen = new Map<string, WikiArticleListItem['kind']>();
    for (const a of articles) {
      if (!seen.has(a.kind.code)) seen.set(a.kind.code, a.kind);
    }
    return Array.from(seen.values());
  }, [articles]);

  const effectiveSelected = selectedArticleId && articles.some(a => a.article_id === selectedArticleId)
    ? selectedArticleId
    : articles[0]?.article_id ?? null;

  const handleCreateClose = (articleId?: string) => {
    setCreateOpen(false);
    if (articleId) {
      queryClient.invalidateQueries({ queryKey: ['wiki-articles', bookId] });
      setSelectedArticleId(articleId);
    }
  };

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
      <>
        <WikiGenJobBanner job={job} onResume={resume} onCancel={cancel} busy={busy} />
        <WikiGenJobDetail key={job?.job_id ?? 'none'} job={job} />
        <EmptyState
          icon={BookOpen}
          title={t('noArticles')}
          description={t('noArticlesDesc')}
          action={
            <div className="flex gap-2">
              <button
                onClick={openBatchGenerate}
                disabled={isActive}
                data-testid="wiki-generate-empty"
                className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:brightness-110 disabled:opacity-50"
              >
                <Sparkles className="h-3.5 w-3.5" />
                {t('generateFromGlossary')}
              </button>
              <button
                onClick={() => setCreateOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary"
              >
                <Plus className="h-3.5 w-3.5" />
                {t('createArticle')}
              </button>
            </div>
          }
        />
        <CreateArticleDialog bookId={bookId} open={createOpen} onClose={handleCreateClose} />
        <GenerateWikiDialog
          open={genOpen}
          onClose={() => setGenOpen(false)}
          onTrigger={trigger}
          busy={busy}
          bookId={bookId}
          entityIds={regenTarget?.entity_ids}
          regenName={regenTarget?.name}
        />
      </>
    );
  }

  return (
    <>
      {staleCount > 0 && (
        <button
          onClick={() => setKnowledgeOpen(true)}
          data-testid="wiki-knowledge-updates"
          className="mb-3 flex w-full items-center gap-2 rounded-lg border border-amber-400/40 bg-amber-400/8 px-4 py-2 text-left text-xs font-medium text-amber-500 hover:bg-amber-400/12"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          {t('staleness.banner', { count: staleCount })}
          <span className="ml-auto rounded-full bg-amber-400/20 px-2 py-0.5 text-[10px]">{staleCount}</span>
        </button>
      )}
      <WikiGenJobBanner job={job} onResume={resume} onCancel={cancel} busy={busy} />
      <WikiGenJobDetail key={job?.job_id ?? 'none'} job={job} />
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
            t={t}
            onGenerate={openBatchGenerate}
            generating={isActive}
            onCreateOpen={() => setCreateOpen(true)}
          />
        </div>

        {/* Article view */}
        <div className="min-w-0 flex-1">
          {effectiveSelected ? (
            <WikiArticleView bookId={bookId} articleId={effectiveSelected} onRegenerate={openRegenerate} />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              {t('noMatch')}
            </div>
          )}
        </div>
      </div>
      <CreateArticleDialog bookId={bookId} open={createOpen} onClose={handleCreateClose} />
      <GenerateWikiDialog
        open={genOpen}
        onClose={() => setGenOpen(false)}
        onTrigger={trigger}
        busy={busy}
        bookId={bookId}
        entityIds={regenTarget?.entity_ids}
        regenName={regenTarget?.name}
      />
      <KnowledgeUpdatesPanel
        bookId={bookId}
        open={knowledgeOpen}
        onClose={() => setKnowledgeOpen(false)}
        onRegenerate={openBatchRegenerate}
      />
    </>
  );
}
