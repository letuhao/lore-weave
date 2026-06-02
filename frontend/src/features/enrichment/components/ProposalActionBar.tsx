import { useTranslation } from 'react-i18next';
import { Sparkles, Check, Pencil, X } from 'lucide-react';
import type { Proposal } from '../types';

/** The author action bar (sticky). Promote is the ④ gate; Approve/Edit/Reject are
 *  the pre-promote lifecycle. A terminal proposal (promoted/rejected) shows a status
 *  note instead. */
export function ProposalActionBar({
  proposal,
  onPromote,
  onApprove,
  onReject,
  onEdit,
  busy,
}: {
  proposal: Proposal;
  onPromote: () => void;
  onApprove: () => void;
  onReject: () => void;
  onEdit: () => void;
  busy?: boolean;
}) {
  const { t } = useTranslation('enrichment');

  if (proposal.review_status === 'promoted') {
    return (
      <div className="flex items-center gap-2 text-xs text-primary">
        <Check className="h-4 w-4" /> {t('actions.already_promoted')}
      </div>
    );
  }
  if (proposal.review_status === 'rejected') {
    return <div className="text-xs text-destructive">{t('actions.rejected_note')}</div>;
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        onClick={onPromote}
        disabled={busy}
        data-testid="enrichment-promote-trigger"
        className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
      >
        <Sparkles className="h-4 w-4" /> {t('actions.promote')}
      </button>
      {proposal.review_status !== 'approved' && (
        <button
          onClick={onApprove}
          disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
        >
          <Check className="h-4 w-4" /> {t('actions.approve')}
        </button>
      )}
      <button
        onClick={onEdit}
        disabled={busy}
        className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
      >
        <Pencil className="h-4 w-4" /> {t('actions.edit')}
      </button>
      <button
        onClick={onReject}
        disabled={busy}
        className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-destructive/30 px-3 py-2 text-sm text-destructive transition-colors hover:bg-destructive/10 disabled:opacity-50"
      >
        <X className="h-4 w-4" /> {t('actions.reject')}
      </button>
    </div>
  );
}
