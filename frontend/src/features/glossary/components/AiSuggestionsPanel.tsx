import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Sparkles, Check, X, MapPin } from 'lucide-react';
import { toast } from 'sonner';
import type { GlossaryEntitySummary } from '../types';
import { useAiSuggestions } from '../hooks/useAiSuggestions';

type Props = {
  bookId: string;
  onClose: () => void;
};

/**
 * "AI Suggestions" inbox (glossary AI-pipeline v2, mui #1). Lists draft
 * entities knowledge-service wrote back (tag ai-suggested) and lets the
 * author promote them to canon or reject them (tombstoned). Mirrors the
 * UnknownEntitiesPanel review pattern.
 */
export function AiSuggestionsPanel({ bookId, onClose }: Props) {
  const { t } = useTranslation('glossaryEditor');
  const { items, total, isLoading, error, promote, reject } = useAiSuggestions(bookId);
  const [busy, setBusy] = useState<string | null>(null);

  const act = async (entity: GlossaryEntitySummary, action: 'promote' | 'reject') => {
    const name = entity.display_name || t('ai_suggestions.unnamed');
    setBusy(entity.entity_id);
    try {
      if (action === 'promote') {
        await promote(entity);
        toast.success(t('ai_suggestions.toast_promoted', { name }));
      } else {
        await reject(entity);
        toast.success(t('ai_suggestions.toast_rejected', { name }));
      }
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Top bar */}
      <div className="flex items-center gap-3 border-b px-4 py-3">
        <button
          onClick={onClose}
          className="rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <Sparkles className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">{t('ai_suggestions.title')}</h3>
        <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground">{total}</span>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <p className="mb-4 max-w-2xl text-xs text-muted-foreground">{t('ai_suggestions.intro')}</p>

        {isLoading && (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <div key={i} className="h-14 animate-pulse rounded-md bg-secondary" />)}
          </div>
        )}

        {error && <p className="text-sm text-destructive">{(error as Error).message}</p>}

        {!isLoading && !error && items.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-16 text-center">
            <Sparkles className="h-8 w-8 text-muted-foreground/50" />
            <p className="text-sm font-medium">{t('ai_suggestions.empty_title')}</p>
            <p className="max-w-sm text-xs text-muted-foreground">{t('ai_suggestions.empty_desc')}</p>
          </div>
        )}

        {items.length > 0 && (
          <div className="divide-y rounded-lg border">
            {items.map((e) => (
              <div key={e.entity_id} className="flex items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{e.display_name || t('ai_suggestions.unnamed')}</div>
                  <div className="mt-0.5 flex items-center gap-2 text-[10px] text-muted-foreground">
                    <span className="rounded bg-secondary px-1.5 py-0.5">{e.kind?.name ?? e.kind?.code}</span>
                    {e.scope_label && (
                      <span className="inline-flex items-center gap-0.5 rounded bg-violet-500/15 px-1.5 py-0.5 text-violet-400">
                        <MapPin className="h-2.5 w-2.5" />
                        {e.scope_label}
                      </span>
                    )}
                    <span>{t('ai_suggestions.mentions', { count: e.chapter_link_count })}</span>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => act(e, 'promote')}
                    disabled={busy === e.entity_id}
                    data-testid={`ai-promote-${e.entity_id}`}
                    className="inline-flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/5 px-2.5 py-1 text-[11px] font-medium text-primary hover:bg-primary/10 transition-colors disabled:opacity-50"
                  >
                    <Check className="h-3 w-3" />
                    {t('ai_suggestions.promote')}
                  </button>
                  <button
                    onClick={() => act(e, 'reject')}
                    disabled={busy === e.entity_id}
                    data-testid={`ai-reject-${e.entity_id}`}
                    className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[11px] font-medium text-muted-foreground hover:bg-secondary transition-colors disabled:opacity-50"
                  >
                    <X className="h-3 w-3" />
                    {t('ai_suggestions.reject')}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
