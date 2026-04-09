import { useState, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Save, Eye, EyeOff, Clock, CheckCircle2, XCircle, MessageSquare } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { wikiApi } from '@/features/wiki/api';
import type { WikiRevisionListItem, WikiSuggestionResp, WikiInfoboxAttr } from '@/features/wiki/types';
import { TiptapEditor, type TiptapEditorHandle } from '@/components/editor/TiptapEditor';
import { Skeleton } from '@/components/shared/Skeleton';
import { ConfirmDialog } from '@/components/shared';
import { cn } from '@/lib/utils';

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
              {attr.original_value || attr.translations[0]?.value || '\u2014'}
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

  const { data } = useQuery({
    queryKey: ['wiki-revisions', bookId, articleId],
    queryFn: () => wikiApi.listRevisions(bookId, articleId, { limit: 50 }, accessToken!),
    enabled: !!accessToken,
  });

  const handleRestore = async () => {
    if (!restoreTarget || !accessToken) return;
    try {
      await wikiApi.restoreRevision(bookId, articleId, restoreTarget.revision_id, accessToken);
      toast.success(`Restored to version ${restoreTarget.version}`);
      queryClient.invalidateQueries({ queryKey: ['wiki-article', bookId, articleId] });
      queryClient.invalidateQueries({ queryKey: ['wiki-revisions', bookId, articleId] });
      setRestoreTarget(null);
    } catch {
      toast.error('Failed to restore revision');
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

function SuggestionPanel({ bookId, articleId }: { bookId: string; articleId: string }) {
  const { accessToken } = useAuth();
  const { t } = useTranslation('wiki');
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: ['wiki-suggestions', bookId, 'pending'],
    queryFn: () => wikiApi.listSuggestions(bookId, { status: 'pending', limit: 50 }, accessToken!),
    enabled: !!accessToken,
  });

  const handleReview = async (sug: WikiSuggestionResp, action: 'accept' | 'reject') => {
    if (!accessToken) return;
    try {
      await wikiApi.reviewSuggestion(bookId, sug.article_id, sug.suggestion_id, { action }, accessToken);
      toast.success(action === 'accept' ? 'Suggestion accepted' : 'Suggestion rejected');
      queryClient.invalidateQueries({ queryKey: ['wiki-suggestions', bookId] });
      if (action === 'accept') {
        queryClient.invalidateQueries({ queryKey: ['wiki-article', bookId, sug.article_id] });
        queryClient.invalidateQueries({ queryKey: ['wiki-revisions', bookId, sug.article_id] });
      }
    } catch {
      toast.error('Failed to review suggestion');
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
          <div key={sug.suggestion_id} className="border-b px-3 py-2">
            <p className="mb-1 text-xs font-medium">{sug.article_display_name || 'Edit'}</p>
            <p className="mb-2 text-[11px] text-muted-foreground">{sug.reason || 'No reason given'}</p>
            <div className="flex gap-1">
              <button
                onClick={() => handleReview(sug, 'accept')}
                className="inline-flex items-center gap-1 rounded border border-green-500/20 bg-green-500/10 px-2 py-0.5 text-[10px] font-medium text-green-400 hover:bg-green-500/20"
              >
                <CheckCircle2 className="h-3 w-3" /> Accept
              </button>
              <button
                onClick={() => handleReview(sug, 'reject')}
                className="inline-flex items-center gap-1 rounded border border-red-500/15 bg-red-500/6 px-2 py-0.5 text-[10px] font-medium text-red-400 hover:bg-red-500/15"
              >
                <XCircle className="h-3 w-3" /> Reject
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Main WikiEditorPage ─────────────────────────────────────────────────── */

export function WikiEditorPage() {
  const { bookId = '', articleId = '' } = useParams();
  const { accessToken } = useAuth();
  const { t } = useTranslation('wiki');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const editorRef = useRef<TiptapEditorHandle>(null);

  const [body, setBody] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const [rightPanel, setRightPanel] = useState<'infobox' | 'history' | 'suggestions'>('infobox');

  const { data: article, isLoading } = useQuery({
    queryKey: ['wiki-article', bookId, articleId],
    queryFn: () => wikiApi.getArticle(bookId, articleId, accessToken!),
    enabled: !!accessToken && !!articleId,
  });

  const handleSave = useCallback(async (summary?: string) => {
    if (!accessToken || !article || body === null) return;
    setSaving(true);
    try {
      await wikiApi.patchArticle(bookId, articleId, {
        body_json: body,
        summary: summary || 'Updated article',
      }, accessToken);
      toast.success('Saved');
      queryClient.invalidateQueries({ queryKey: ['wiki-article', bookId, articleId] });
      queryClient.invalidateQueries({ queryKey: ['wiki-revisions', bookId, articleId] });
      queryClient.invalidateQueries({ queryKey: ['wiki-articles', bookId] });
    } catch {
      toast.error('Failed to save');
    } finally {
      setSaving(false);
    }
  }, [accessToken, article, body, bookId, articleId, queryClient]);

  const handleTogglePublish = useCallback(async () => {
    if (!accessToken || !article) return;
    const newStatus = article.status === 'published' ? 'draft' : 'published';
    try {
      await wikiApi.patchArticle(bookId, articleId, { status: newStatus }, accessToken);
      toast.success(newStatus === 'published' ? 'Published' : 'Unpublished');
      queryClient.invalidateQueries({ queryKey: ['wiki-article', bookId, articleId] });
      queryClient.invalidateQueries({ queryKey: ['wiki-articles', bookId] });
    } catch {
      toast.error('Failed to update status');
    }
  }, [accessToken, article, bookId, articleId, queryClient]);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Skeleton className="h-12 w-48" />
      </div>
    );
  }

  if (!article) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-2 text-muted-foreground">
        <p>Article not found</p>
        <button onClick={() => navigate(-1)} className="text-sm text-primary hover:underline">Go back</button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Top bar */}
      <div className="flex items-center gap-3 border-b bg-card px-4 py-2">
        <button
          onClick={() => navigate(`/books/${bookId}/wiki`)}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
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
              ref={editorRef}
              content={article.body_json}
              onUpdate={(json: unknown) => setBody(json)}
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
              <SuggestionPanel bookId={bookId} articleId={articleId} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
