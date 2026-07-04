import { useState, useCallback, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Save, Eye, EyeOff, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { wikiApi } from '../api';
import type { WikiRevisionListItem, WikiSuggestionResp, WikiInfoboxAttr } from '../types';
import { WikiSuggestionReview } from './WikiSuggestionReview';
import { TiptapEditor } from '@/components/editor/TiptapEditor';
import { Skeleton } from '@/components/shared/Skeleton';
import { ConfirmDialog } from '@/components/shared';
import { cn } from '@/lib/utils';

// 15_wiki_panels.md B2 — the shared article-editing workspace (DOCK-2 "no fork"): the SAME
// implementation the classic `WikiEditorPage` route and the studio's `wiki-editor` dock panel
// (WikiEditorPanel.tsx) both render. This component is deliberately "dumb" about retargeting —
// it always fully commits to whatever `articleId` prop it's given; the params-retargeting G7
// dirty-guard (15_wiki_panels.md B2b) lives one level up, in WikiEditorPanel, which decides
// WHEN to change the `articleId` it passes down (and remounts this component via `key` on a
// confirmed switch so all local state resets cleanly).
//
// B2a (DOCK-7) — Back/delete/not-found all route through the caller-supplied `onBack`, never a
// bare navigate(): the page passes a route navigate, the panel passes `host.openPanel('wiki')`.
//
// B2b (dirty-guard) — the classic page's Back button had NO dirty-guard at all before this
// migration (client-side navigate() doesn't fire beforeunload, so leaving mid-edit silently lost
// the draft). Since `onBack` is shared by both callers, gating it here on `dirty` fixes that
// pre-existing bug for the page too, for free.

export type WikiEditorRightPanel = 'infobox' | 'history' | 'suggestions';

/* ── Infobox sidebar (read-only) ─────────────────────────────────────────── */

function InfoboxPanel({ attrs, displayName, kindName }: {
  attrs: WikiInfoboxAttr[];
  displayName: string;
  kindName: string;
}) {
  const { t } = useTranslation('wiki');
  const visible = attrs.filter(a => a.original_value || a.translations.length > 0);

  return (
    <div className="flex flex-col overflow-y-auto p-3">
      <div className="mb-3 text-center">
        <div className="mx-auto mb-2 flex h-14 w-14 items-center justify-center rounded-lg border bg-gradient-to-br from-amber-900/30 to-amber-950/20">
          <span className="font-serif text-xl text-primary">{displayName.charAt(0)}</span>
        </div>
        <span className="font-serif text-sm font-semibold">{displayName}</span>
        <br />
        <span className="text-[10px] text-muted-foreground">{kindName}</span>
      </div>
      <div className="text-[11px]">
        {visible.map(attr => (
          <div key={attr.attr_value_id} className="mb-2">
            <label className="mb-0.5 block font-medium text-muted-foreground">
              {attr.attribute_def.name}
            </label>
            <div className="rounded border bg-background px-2 py-1 text-xs">
              {attr.original_value || attr.translations[0]?.value || '—'}
            </div>
          </div>
        ))}
        {visible.length === 0 && (
          <p className="text-center text-xs text-muted-foreground italic">{t('noContent')}</p>
        )}
      </div>
    </div>
  );
}

/* ── Revision history panel ──────────────────────────────────────────────── */

function RevisionPanel({ bookId, articleId }: { bookId: string; articleId: string }) {
  const { accessToken } = useAuth();
  const { t } = useTranslation('wiki');
  const queryClient = useQueryClient();
  const [restoreTarget, setRestoreTarget] = useState<WikiRevisionListItem | null>(null);

  const { data, isLoading: revsLoading } = useQuery({
    queryKey: ['wiki-revisions', bookId, articleId],
    queryFn: () => wikiApi.listRevisions(bookId, articleId, { limit: 50 }, accessToken!),
    enabled: !!accessToken,
  });

  if (revsLoading) {
    return (
      <div className="p-4 space-y-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    );
  }

  const handleRestore = async () => {
    if (!restoreTarget || !accessToken) return;
    try {
      await wikiApi.restoreRevision(bookId, articleId, restoreTarget.revision_id, accessToken);
      toast.success(t('restored', { version: restoreTarget.version }));
      queryClient.invalidateQueries({ queryKey: ['wiki-article', bookId, articleId] });
      queryClient.invalidateQueries({ queryKey: ['wiki-revisions', bookId, articleId] });
      setRestoreTarget(null);
    } catch {
      toast.error(t('restoreFailed'));
    }
  };

  const items = data?.items ?? [];
  const AUTHOR_COLORS: Record<string, string> = {
    owner: 'text-purple-400',
    community: 'text-teal-400',
    ai: 'text-amber-400',
  };

  return (
    <div className="flex flex-col">
      <div className="border-b px-3 py-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('history')} ({items.length})
        </span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {items.map(rev => (
          <div key={rev.revision_id} className="border-b px-3 py-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-medium">v{rev.version}</span>
              <span className={cn('text-[10px]', AUTHOR_COLORS[rev.author_type] || 'text-muted-foreground')}>
                {rev.author_type}
              </span>
            </div>
            <p className="mt-0.5 text-muted-foreground">{rev.summary || 'No summary'}</p>
            <div className="mt-1 flex items-center justify-between">
              <span className="text-[10px] text-muted-foreground">
                {new Date(rev.created_at).toLocaleDateString()}
              </span>
              {rev.version < (items[0]?.version ?? 0) && (
                <button
                  onClick={() => setRestoreTarget(rev)}
                  className="text-[10px] text-primary hover:underline"
                >
                  Restore
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
      {restoreTarget && (
        <ConfirmDialog
          open
          onOpenChange={(v) => { if (!v) setRestoreTarget(null); }}
          title={`Restore to version ${restoreTarget.version}?`}
          description="This will replace the current article body and create a new revision."
          confirmLabel="Restore"
          onConfirm={handleRestore}
        />
      )}
    </div>
  );
}

/* ── Suggestion review panel ─────────────────────────────────────────────── */

function SuggestionPanel({ bookId, articleId, currentBody }: { bookId: string; articleId: string; currentBody?: unknown }) {
  const { accessToken } = useAuth();
  const { t } = useTranslation('wiki');
  const queryClient = useQueryClient();

  const { data, isLoading: sugsLoading } = useQuery({
    queryKey: ['wiki-suggestions', bookId, 'pending'],
    queryFn: () => wikiApi.listSuggestions(bookId, { status: 'pending', limit: 50 }, accessToken!),
    enabled: !!accessToken,
  });

  if (sugsLoading) {
    return (
      <div className="p-4 space-y-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  const handleReview = async (sug: WikiSuggestionResp, action: 'accept' | 'reject') => {
    if (!accessToken) return;
    try {
      await wikiApi.reviewSuggestion(bookId, sug.article_id, sug.suggestion_id, { action }, accessToken);
      toast.success(action === 'accept' ? t('suggestionAccepted') : t('suggestionRejected'));
      queryClient.invalidateQueries({ queryKey: ['wiki-suggestions', bookId] });
      if (action === 'accept') {
        queryClient.invalidateQueries({ queryKey: ['wiki-article', bookId, sug.article_id] });
        queryClient.invalidateQueries({ queryKey: ['wiki-revisions', bookId, sug.article_id] });
        // /review-impl F1: an AI-regen accept resolves staleness server-side — keep the
        // feed + sidebar badges fresh (parity with the reader review handler).
        queryClient.invalidateQueries({ queryKey: ['wiki-staleness', bookId] });
        queryClient.invalidateQueries({ queryKey: ['wiki-articles', bookId] });
      }
    } catch {
      toast.error(t('reviewFailed'));
    }
  };

  const items = (data?.items ?? []).filter(s => s.article_id === articleId);

  if (items.length === 0) {
    return (
      <div className="p-4 text-center text-xs text-muted-foreground">
        No pending suggestions for this article.
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="border-b px-3 py-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Suggestions ({items.length})
        </span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {items.map(sug => (
          <WikiSuggestionReview
            key={sug.suggestion_id}
            suggestion={sug}
            currentBodyJson={currentBody}
            bookId={bookId}
            onAccept={() => handleReview(sug, 'accept')}
            onReject={() => handleReview(sug, 'reject')}
          />
        ))}
      </div>
    </div>
  );
}

/* ── Main WikiEditorWorkspace ────────────────────────────────────────────── */

export interface WikiEditorWorkspaceProps {
  bookId: string;
  articleId: string;
  initialRightPanel?: WikiEditorRightPanel;
  /** Leave the editor — page: navigate to the wiki tab; panel: host.openPanel('wiki'). Gated on
   * `dirty` here (B2b) so both callers get the same "discard unsaved changes?" guard for free. */
  onBack: () => void;
  /** Bubbles local dirty state up so a retargeting panel wrapper can gate its OWN param-driven
   * article switch (B2b) — this component has no idea it might be inside such a wrapper. */
  onDirtyChange?: (dirty: boolean) => void;
  /** Bubbles the loaded article's display name up for panel self-titling (BookReaderPanel
   * precedent) — omitted by the classic page, which titles itself via the browser tab/route. */
  onTitleChange?: (title: string) => void;
}

export function WikiEditorWorkspace({ bookId, articleId, initialRightPanel, onBack, onDirtyChange, onTitleChange }: WikiEditorWorkspaceProps) {
  const { accessToken } = useAuth();
  const { t } = useTranslation('wiki');
  const queryClient = useQueryClient();

  const [body, setBody] = useState<unknown>(null);
  const [dirty, setDirtyState] = useState(false);
  const setDirty = useCallback((v: boolean) => {
    setDirtyState(v);
    onDirtyChange?.(v);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onDirtyChange]);
  const [saving, setSaving] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [confirmBackOpen, setConfirmBackOpen] = useState(false);
  const [rightPanel, setRightPanel] = useState<WikiEditorRightPanel>(initialRightPanel ?? 'infobox');

  // A History-button re-open while ALREADY viewing this same article (no articleId change, so
  // no G7 concern) should still retarget the tab — sync whenever the caller passes a new value.
  useEffect(() => {
    if (initialRightPanel) setRightPanel(initialRightPanel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialRightPanel]);

  const { data: article, isLoading } = useQuery({
    queryKey: ['wiki-article', bookId, articleId],
    queryFn: () => wikiApi.getArticle(bookId, articleId, accessToken!),
    enabled: !!accessToken && !!articleId,
  });

  // Sync editor body when article data changes (e.g., after restore)
  useEffect(() => {
    if (article) {
      setBody(article.body_json);
      setDirty(false);
      onTitleChange?.(article.display_name);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [article]);

  // Warn on unsaved changes before unload
  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [dirty]);

  const handleEditorUpdate = useCallback((json: unknown) => {
    setBody(json);
    setDirty(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSave = useCallback(async (summary?: string) => {
    if (!accessToken || !article || body === null) return;
    setSaving(true);
    try {
      await wikiApi.patchArticle(bookId, articleId, {
        body_json: body,
        summary: summary || 'Updated article',
      }, accessToken);
      toast.success(t('saved'));
      setDirty(false);
      queryClient.invalidateQueries({ queryKey: ['wiki-article', bookId, articleId] });
      queryClient.invalidateQueries({ queryKey: ['wiki-revisions', bookId, articleId] });
      queryClient.invalidateQueries({ queryKey: ['wiki-articles', bookId] });
    } catch {
      toast.error(t('saveFailed'));
    } finally {
      setSaving(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, article, body, bookId, articleId, queryClient, t]);

  const handleTogglePublish = useCallback(async () => {
    if (!accessToken || !article) return;
    const newStatus = article.status === 'published' ? 'draft' : 'published';
    try {
      await wikiApi.patchArticle(bookId, articleId, { status: newStatus }, accessToken);
      toast.success(newStatus === 'published' ? t('published') : t('unpublished'));
      queryClient.invalidateQueries({ queryKey: ['wiki-article', bookId, articleId] });
      queryClient.invalidateQueries({ queryKey: ['wiki-articles', bookId] });
    } catch {
      toast.error(t('statusFailed'));
    }
  }, [accessToken, article, bookId, articleId, queryClient, t]);

  const handleDelete = useCallback(async () => {
    if (!accessToken) return;
    try {
      await wikiApi.deleteArticle(bookId, articleId, accessToken);
      toast.success(t('deleted'));
      queryClient.invalidateQueries({ queryKey: ['wiki-articles', bookId] });
      onBack();
    } catch {
      toast.error(t('deleteFailed'));
    }
  }, [accessToken, bookId, articleId, queryClient, onBack, t]);

  // B2b — the shared dirty-guard: Back (and the "article not found" fallback) must not silently
  // discard an unsaved draft. Delete doesn't need this gate — it already goes through its own
  // destructive ConfirmDialog below.
  const handleBackClick = () => {
    if (dirty) setConfirmBackOpen(true);
    else onBack();
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Skeleton className="h-12 w-48" />
      </div>
    );
  }

  if (!article) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
        <p>Article not found</p>
        <button onClick={onBack} className="text-sm text-primary hover:underline">Go back</button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Top bar */}
      <div className="flex items-center gap-3 border-b bg-card px-4 py-2">
        <button
          onClick={handleBackClick}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          Back
        </button>
        <div className="h-4 w-px bg-border" />
        <span
          className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
          style={{ backgroundColor: article.kind.color + '18', color: article.kind.color }}
        >
          {article.kind.name}
        </span>
        <span className="text-sm font-semibold">{article.display_name}</span>
        <span className="text-[11px] text-muted-foreground">
          &middot; {t('revisions', { count: article.revision_count })}
        </span>

        <div className="flex-1" />

        {/* Delete */}
        <button
          onClick={() => setDeleteOpen(true)}
          className="inline-flex items-center gap-1 rounded-md border border-destructive/20 px-2 py-1 text-[11px] font-medium text-destructive hover:bg-destructive/10"
        >
          <Trash2 className="h-3 w-3" />
          {t('deleteArticle')}
        </button>

        {/* Status toggle */}
        <button
          onClick={handleTogglePublish}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[11px] font-medium transition-colors',
            article.status === 'published'
              ? 'border-green-500/20 text-green-400 hover:bg-green-500/10'
              : 'border-amber-400/20 text-amber-400 hover:bg-amber-400/10',
          )}
        >
          {article.status === 'published' ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
          {article.status === 'published' ? t('published') : t('draft')}
        </button>

        {/* Save */}
        <button
          onClick={() => handleSave()}
          disabled={saving || body === null}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1 text-[11px] font-medium text-primary-foreground hover:brightness-110 disabled:opacity-50"
        >
          <Save className="h-3 w-3" />
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>

      {/* Editor + sidebar */}
      <div className="flex flex-1 overflow-hidden">
        {/* Center: TiptapEditor */}
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[800px] px-10 py-8">
            <TiptapEditor
              content={article.body_json}
              onUpdate={handleEditorUpdate}
            />
          </div>
        </div>

        {/* Right sidebar */}
        <div className="flex w-[280px] shrink-0 flex-col border-l bg-card">
          {/* Panel tabs */}
          <div className="flex border-b">
            {(['infobox', 'history', 'suggestions'] as const).map(panel => (
              <button
                key={panel}
                onClick={() => setRightPanel(panel)}
                className={cn(
                  'flex-1 border-b-2 px-2 py-2 text-center text-[11px] font-medium transition-colors',
                  rightPanel === panel
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground',
                )}
              >
                {panel === 'infobox' ? t('infobox') : panel === 'history' ? t('history') : 'Suggestions'}
              </button>
            ))}
          </div>

          {/* Panel content */}
          <div className="flex-1 overflow-y-auto">
            {rightPanel === 'infobox' && (
              <InfoboxPanel
                attrs={article.infobox}
                displayName={article.display_name}
                kindName={article.kind.name}
              />
            )}
            {rightPanel === 'history' && (
              <RevisionPanel bookId={bookId} articleId={articleId} />
            )}
            {rightPanel === 'suggestions' && (
              <SuggestionPanel bookId={bookId} articleId={articleId} currentBody={article?.body_json} />
            )}
          </div>
        </div>
      </div>
      {deleteOpen && (
        <ConfirmDialog
          open
          onOpenChange={(v) => { if (!v) setDeleteOpen(false); }}
          title={t('deleteArticle')}
          description={t('deleteConfirm')}
          confirmLabel={t('deleteArticle')}
          variant="destructive"
          onConfirm={handleDelete}
        />
      )}
      {confirmBackOpen && (
        <ConfirmDialog
          open
          onOpenChange={(v) => { if (!v) setConfirmBackOpen(false); }}
          title={t('discardTitle', { defaultValue: 'Discard unsaved changes?' })}
          description={t('discardDescription', { defaultValue: 'You have unsaved edits to this article. Leaving now will discard them.' })}
          confirmLabel={t('discardConfirm', { defaultValue: 'Discard & leave' })}
          variant="destructive"
          onConfirm={() => { setConfirmBackOpen(false); onBack(); }}
        />
      )}
    </div>
  );
}
