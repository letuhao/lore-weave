import { useState, useMemo, useDeferredValue } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Search } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { FormDialog } from '@/components/shared';
import { Skeleton } from '@/components/shared/Skeleton';
import { useOptionalStudioHost } from '@/features/studio/host/StudioHostProvider';
import { glossaryApi } from '@/features/glossary/api';
import { wikiApi } from '../api';
import { cn } from '@/lib/utils';

// 15_wiki_panels.md B3 — DOCK-9: hand-rolled `fixed inset-0` overlay replaced with the shared
// FormDialog. B1a — DOCK-7: the empty-state "go to Glossary" link would navigate the whole studio
// away from itself when this dialog is opened from inside the `wiki` panel; branch like
// StepConfig.tsx / ExtractionWizard's jobs-list fix (a known panel id, so a direct
// `host.openPanel('glossary')` is simpler than the generic link resolver).
export function CreateArticleDialog({ bookId, open, onClose }: {
  bookId: string;
  open: boolean;
  onClose: (articleId?: string) => void;
}) {
  const { accessToken } = useAuth();
  const { t } = useTranslation('wiki');
  const studioHost = useOptionalStudioHost();
  const [entitySearch, setEntitySearch] = useState('');
  const deferredEntitySearch = useDeferredValue(entitySearch);
  const [creating, setCreating] = useState(false);
  const [offset, setOffset] = useState(0);
  const pageSize = 20;

  // Server-side search + pagination via listEntities
  const { data: entityData, isLoading: entitiesLoading } = useQuery({
    queryKey: ['glossary-entities-picker', bookId, deferredEntitySearch, offset],
    queryFn: () => glossaryApi.listEntities(bookId, {
      searchQuery: deferredEntitySearch,
      kindCodes: [],
      status: 'all',
      limit: pageSize,
      offset,
    }, accessToken!),
    enabled: !!accessToken && open,
    staleTime: 15_000,
  });

  // Fetch existing wiki article entity_ids to mark which already have articles
  const { data: wikiData } = useQuery({
    queryKey: ['wiki-articles-ids', bookId],
    queryFn: () => wikiApi.listArticles(bookId, { limit: 500 }, accessToken!),
    enabled: !!accessToken && open,
    staleTime: 30_000,
  });

  const existingEntityIds = useMemo(
    () => new Set((wikiData?.items ?? []).map(a => a.entity_id)),
    [wikiData],
  );

  const entities = entityData?.items ?? [];
  const totalEntities = entityData?.total ?? 0;
  const hasMore = offset + pageSize < totalEntities;
  const hasPrev = offset > 0;

  const handleCreate = async (entityId: string, kindCode: string) => {
    if (!accessToken || creating) return;
    setCreating(true);
    try {
      const article = await wikiApi.createArticle(bookId, {
        entity_id: entityId,
        template_code: kindCode,
      }, accessToken);
      onClose(article.article_id);
    } catch {
      toast.error(t('createFailed'));
    } finally {
      setCreating(false);
    }
  };

  return (
    <FormDialog
      open={open}
      onOpenChange={(next) => { if (!next) onClose(); }}
      title={t('createArticle')}
      description={t('selectEntity')}
      size="lg"
    >
      <div className="flex flex-col gap-0">
        {/* Search */}
        <div className="relative -mt-1 mb-3">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            className="h-9 w-full rounded-md border bg-background pl-8 pr-3 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
            placeholder={t('searchEntities')}
            value={entitySearch}
            onChange={e => { setEntitySearch(e.target.value); setOffset(0); }}
            autoFocus
          />
        </div>

        {/* Entity list */}
        <div className="max-h-[420px] min-h-[200px] overflow-y-auto">
          {entitiesLoading ? (
            <div className="space-y-1 p-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full rounded" />
              ))}
            </div>
          ) : entities.length === 0 ? (
            <div className="px-5 py-10 text-center">
              <p className="text-sm text-muted-foreground">
                {totalEntities === 0 && !deferredEntitySearch
                  ? 'No glossary entities yet.'
                  : deferredEntitySearch
                    ? 'No entities match your search.'
                    : 'No entities found.'}
              </p>
              {totalEntities === 0 && !deferredEntitySearch && (
                <>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Create entities in the <strong>Glossary</strong> tab first, then come back here.
                  </p>
                  {studioHost ? (
                    <button
                      type="button"
                      onClick={() => { studioHost.openPanel('glossary'); onClose(); }}
                      className="mt-3 inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary"
                    >
                      Go to Glossary
                    </button>
                  ) : (
                    <Link
                      to={`/books/${bookId}/glossary`}
                      onClick={() => onClose()}
                      className="mt-3 inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary"
                    >
                      Go to Glossary
                    </Link>
                  )}
                </>
              )}
            </div>
          ) : (
            <div className="p-1.5">
              {entities.map(e => {
                const hasArticle = existingEntityIds.has(e.entity_id);
                return (
                  <button
                    key={e.entity_id}
                    onClick={() => handleCreate(e.entity_id, e.kind.code)}
                    disabled={creating || hasArticle}
                    className={cn(
                      'flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors',
                      hasArticle
                        ? 'cursor-not-allowed opacity-40'
                        : 'hover:bg-secondary',
                    )}
                  >
                    <span
                      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-medium"
                      style={{ backgroundColor: e.kind.color + '18', color: e.kind.color }}
                    >
                      {e.kind.icon || e.kind.name.charAt(0)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">
                        {e.display_name || 'Untitled'}
                      </div>
                      <div className="text-[10px] text-muted-foreground">
                        {e.kind.name}
                        {e.status === 'draft' && ' · Draft'}
                      </div>
                    </div>
                    {hasArticle && (
                      <span className="shrink-0 text-[10px] text-muted-foreground">
                        Has article
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Pagination footer */}
        {totalEntities > 0 && (
          <div className="flex items-center justify-between border-t pt-2.5">
            <span className="text-[11px] text-muted-foreground">
              {offset + 1}–{Math.min(offset + pageSize, totalEntities)} of {totalEntities} entities
            </span>
            <div className="flex gap-1.5">
              <button
                onClick={() => setOffset(Math.max(0, offset - pageSize))}
                disabled={!hasPrev}
                className="rounded border px-2.5 py-1 text-[11px] font-medium hover:bg-secondary disabled:opacity-30"
              >
                Prev
              </button>
              <button
                onClick={() => setOffset(offset + pageSize)}
                disabled={!hasMore}
                className="rounded border px-2.5 py-1 text-[11px] font-medium hover:bg-secondary disabled:opacity-30"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </FormDialog>
  );
}
