import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, GitMerge, Check, X } from 'lucide-react';
import { toast } from 'sonner';
import type { MergeCandidate } from '../types';
import { useMergeCandidates } from '../hooks/useMergeCandidates';

type Props = { bookId: string; onClose: () => void };

/** One proposed cluster: member rows with a winner radio + confirm/dismiss. */
function MergeCandidateCard({
  candidate,
  busy,
  onConfirm,
  onDismiss,
}: {
  candidate: MergeCandidate;
  busy: boolean;
  onConfirm: (winnerId: string) => void;
  onDismiss: () => void;
}) {
  const { t } = useTranslation('glossaryEditor');
  const fallbackWinner = candidate.suggested_winner_entity_id || candidate.members[0]?.entity_id || '';
  const [winner, setWinner] = useState(fallbackWinner);

  return (
    <div className="rounded-lg border p-3">
      <div className="mb-2 flex items-center gap-2 text-[10px] text-muted-foreground">
        <span className="rounded bg-secondary px-1.5 py-0.5">{candidate.kind_code}</span>
        <span>{t('merge_candidates.score', { score: Math.round(candidate.score * 100) })}</span>
      </div>
      {candidate.rationale && (
        <p className="mb-2 text-[11px] italic text-muted-foreground">{candidate.rationale}</p>
      )}
      <p className="mb-2 text-xs text-muted-foreground">{t('merge_candidates.winner_label')}</p>
      <div className="mb-3 space-y-1">
        {candidate.members.map((m) => (
          <label
            key={m.entity_id}
            className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-secondary/50"
          >
            <input
              type="radio"
              name={`winner-${candidate.candidate_id}`}
              checked={winner === m.entity_id}
              onChange={() => setWinner(m.entity_id)}
              data-testid={`merge-winner-${m.entity_id}`}
            />
            <span className="truncate font-medium">{m.name || t('merge_candidates.unnamed')}</span>
            {m.aliases.length > 0 && (
              <span className="truncate text-[10px] text-muted-foreground">({m.aliases.join(', ')})</span>
            )}
            <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">
              {t('merge_candidates.mentions', { count: m.chapter_link_count })}
            </span>
          </label>
        ))}
      </div>
      <div className="flex items-center gap-1.5">
        <button
          onClick={() => onConfirm(winner)}
          disabled={busy || !winner}
          data-testid={`merge-confirm-${candidate.candidate_id}`}
          className="inline-flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/5 px-2.5 py-1 text-[11px] font-medium text-primary hover:bg-primary/10 transition-colors disabled:opacity-50"
        >
          <Check className="h-3 w-3" />
          {t('merge_candidates.confirm')}
        </button>
        <button
          onClick={onDismiss}
          disabled={busy}
          data-testid={`merge-dismiss-${candidate.candidate_id}`}
          className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[11px] font-medium text-muted-foreground hover:bg-secondary transition-colors disabled:opacity-50"
        >
          <X className="h-3 w-3" />
          {t('merge_candidates.dismiss')}
        </button>
      </div>
    </div>
  );
}

/**
 * "Merge Candidates" inbox (glossary AI-pipeline v2, mui #1c). Lists coreference
 * clusters the detector proposed; the author confirms a merge (folds members
 * into a chosen winner — destructive but reversible via the Undo toast) or
 * dismisses the cluster. Mirrors the AiSuggestionsPanel review pattern.
 */
export function MergeCandidatePanel({ bookId, onClose }: Props) {
  const { t } = useTranslation('glossaryEditor');
  const { candidates, total, isLoading, error, confirm, dismiss, undo } = useMergeCandidates(bookId);
  const [busy, setBusy] = useState<string | null>(null);

  const onConfirm = async (c: MergeCandidate, winnerId: string) => {
    const name = c.members.find((m) => m.entity_id === winnerId)?.name || t('merge_candidates.unnamed');
    setBusy(c.candidate_id);
    try {
      const journalIds = await confirm(c, winnerId);
      if (journalIds.length === 0) {
        // Every loser was skipped/failed server-side (stale or invalid) — don't
        // claim a merge that didn't happen (review-impl MED-1).
        toast.info(t('merge_candidates.toast_none'));
        return;
      }
      // Count reflects what ACTUALLY merged, not the cluster size.
      toast.success(t('merge_candidates.toast_merged', { count: journalIds.length, name }), {
        action: {
          label: t('merge_candidates.undo'),
          onClick: () => {
            void Promise.all(journalIds.map((j) => undo(j))).then(() =>
              toast.success(t('merge_candidates.toast_undone')),
            );
          },
        },
      });
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const onDismiss = async (c: MergeCandidate) => {
    setBusy(c.candidate_id);
    try {
      await dismiss(c);
      toast.success(t('merge_candidates.toast_dismissed'));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b px-4 py-3">
        <button
          onClick={onClose}
          className="rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <GitMerge className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">{t('merge_candidates.title')}</h3>
        <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground">{total}</span>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <p className="mb-4 max-w-2xl text-xs text-muted-foreground">{t('merge_candidates.intro')}</p>

        {isLoading && (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <div key={i} className="h-24 animate-pulse rounded-md bg-secondary" />)}
          </div>
        )}

        {error && <p className="text-sm text-destructive">{(error as Error).message}</p>}

        {!isLoading && !error && candidates.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-16 text-center">
            <GitMerge className="h-8 w-8 text-muted-foreground/50" />
            <p className="text-sm font-medium">{t('merge_candidates.empty_title')}</p>
            <p className="max-w-sm text-xs text-muted-foreground">{t('merge_candidates.empty_desc')}</p>
          </div>
        )}

        {candidates.length > 0 && (
          <div className="space-y-3">
            {candidates.map((c) => (
              <MergeCandidateCard
                key={c.candidate_id}
                candidate={c}
                busy={busy === c.candidate_id}
                onConfirm={(winnerId) => void onConfirm(c, winnerId)}
                onDismiss={() => void onDismiss(c)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
