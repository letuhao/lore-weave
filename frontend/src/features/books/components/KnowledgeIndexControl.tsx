import { useTranslation } from 'react-i18next';
import { Brain, BrainCircuit, EyeOff } from 'lucide-react';

import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { useIndexChapter } from '@/features/books/hooks/useIndexChapter';

interface KnowledgeIndexControlProps {
  token: string;
  bookId: string;
  chapterId: string;
  /** Non-null ⇒ the chapter is IN the knowledge graph (possibly as a draft). */
  kgIndexedRevisionId?: string | null;
  /** The user's explicit "keep this out of my knowledge". */
  kgExclude?: boolean;
  /** Editor has unsaved changes → indexing would pin the STALE server draft, so the
   * action is disabled until the user saves (same reasoning as PublishControl). */
  dirty?: boolean;
  onChanged: () => void | Promise<void>;
}

/**
 * WS-0.9 view — the chapter editor's "Add to knowledge" affordance.
 *
 * Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md.
 *
 * This is the USER-VISIBLE half of publish-independent indexing. Publishing no longer
 * puts a chapter in the knowledge graph, so without this control there is literally no
 * way for a user to get a draft chapter into their KG — and, just as important, no way
 * for them to SEE what is in it. An invisible knowledge graph is one the user cannot
 * trust or correct.
 *
 * Deliberately separate from PublishControl: they are now different questions.
 *   PublishControl        → "is this the canonical, shareable version?"
 *   KnowledgeIndexControl → "should the assistant know about this?"
 *
 * Vocabulary: the user never sees "index", "extract", "canon" or "revision". They see
 * "Add to knowledge" / "In your knowledge" / "Forget this chapter".
 *
 * All logic lives in useIndexChapter (repo MVC rule: components render, hooks own logic).
 */
export function KnowledgeIndexControl({
  token,
  bookId,
  chapterId,
  kgIndexedRevisionId,
  kgExclude,
  dirty,
  onChanged,
}: KnowledgeIndexControlProps) {
  const { t } = useTranslation('editor');
  const { busy, forgetOpen, setForgetOpen, index, requestForget, confirmForget, allow } =
    useIndexChapter({ token, bookId, chapterId, onChanged });

  const isIndexed = !!kgIndexedRevisionId;
  const isExcluded = !!kgExclude;

  // ── Excluded: the ONLY affordance is to allow it back. Offering "Add to knowledge"
  // here would just 409 (kg_exclude is producer-side authoritative), so we show the
  // real next step instead of a button that cannot work.
  if (isExcluded) {
    return (
      <div className="flex items-center gap-1.5">
        <span
          className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
          data-testid="knowledge-badge"
          data-kg-state="excluded"
        >
          <EyeOff className="h-3 w-3" />
          {t('knowledge.excluded_badge')}
        </span>
        <button
          data-testid="knowledge-allow-button"
          onClick={() => void allow()}
          disabled={busy}
          className="inline-flex items-center rounded-md px-2 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-primary disabled:opacity-50"
        >
          {t('knowledge.allow')}
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      <span
        className={
          'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ' +
          (isIndexed ? 'bg-primary/12 text-primary' : 'bg-muted text-muted-foreground')
        }
        data-testid="knowledge-badge"
        data-kg-state={isIndexed ? 'indexed' : 'not-indexed'}
      >
        {isIndexed ? <BrainCircuit className="h-3 w-3" /> : <Brain className="h-3 w-3" />}
        {isIndexed ? t('knowledge.indexed_badge') : t('knowledge.not_indexed_badge')}
      </span>

      <button
        data-testid="knowledge-index-button"
        onClick={() => void index()}
        disabled={busy || dirty}
        title={dirty ? t('knowledge.save_first') : t('knowledge.hint')}
        className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors hover:border-primary/50 hover:text-primary disabled:opacity-50"
      >
        {isIndexed ? t('knowledge.reindex') : t('knowledge.add')}
      </button>

      {/* review-impl: the opt-out is available BEFORE indexing too, not only after.
          It used to be gated behind isIndexed — but publishing AUTO-indexes a chapter, so
          a user who wanted to keep a chapter out of their knowledge graph had no way to
          say so in advance. They had to let it in, then take it out. Now they can pre-empt
          it: excluding an un-indexed chapter simply keeps it out. */}
      <button
        data-testid="knowledge-forget-button"
        onClick={requestForget}
        disabled={busy}
        className="inline-flex items-center rounded-md px-2 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-destructive disabled:opacity-50"
      >
        {isIndexed ? t('knowledge.forget') : t('knowledge.keep_out')}
      </button>

      <ConfirmDialog
        open={forgetOpen}
        onOpenChange={setForgetOpen}
        title={t('knowledge.forget_confirm_title')}
        description={t('knowledge.forget_confirm_body')}
        confirmLabel={t('knowledge.forget')}
        variant="destructive"
        loading={busy}
        onConfirm={() => void confirmForget()}
      />
    </div>
  );
}
