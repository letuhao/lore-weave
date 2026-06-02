import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles, Check, Pencil, X, Undo2 } from 'lucide-react';
import type { Proposal } from '../types';

/** The author action bar (sticky). Promote is the ④ gate; Approve/Edit/Reject are
 *  the pre-promote lifecycle. A promoted proposal can be Retracted (un-promote the
 *  enrichment supplement from canon); a rejected one shows a status note. */
export function ProposalActionBar({
  proposal,
  onPromote,
  onApprove,
  onReject,
  onEdit,
  onRetract,
  busy,
}: {
  proposal: Proposal;
  onPromote: () => void;
  onApprove: () => void;
  onReject: (reason?: string) => void;
  onEdit: () => void;
  onRetract: () => void;
  busy?: boolean;
}) {
  const { t } = useTranslation('enrichment');
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');

  if (proposal.review_status === 'promoted') {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-xs text-primary">
          <Check className="h-4 w-4" /> {t('actions.already_promoted')}
        </div>
        <button
          onClick={onRetract}
          disabled={busy}
          data-testid="enrichment-retract-trigger"
          className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-destructive/30 px-3 py-1.5 text-xs text-destructive transition-colors hover:bg-destructive/10 disabled:opacity-50"
        >
          <Undo2 className="h-3.5 w-3.5" /> {t('actions.retract')}
        </button>
      </div>
    );
  }
  if (proposal.review_status === 'rejected') {
    return <div className="text-xs text-destructive">{t('actions.rejected_note')}</div>;
  }

  if (rejecting) {
    return (
      <div className="space-y-2" data-testid="enrichment-reject-form">
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={2}
          placeholder={t('actions.reject_reason')}
          data-testid="enrichment-reject-reason"
          className="w-full rounded-md border bg-background p-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring/40"
        />
        <div className="flex gap-2">
          <button
            onClick={() => onReject(reason.trim() || undefined)}
            disabled={busy}
            data-testid="enrichment-reject-confirm"
            className="inline-flex items-center gap-1.5 rounded-md bg-destructive px-3 py-2 text-sm font-medium text-destructive-foreground transition-colors hover:bg-destructive/90 disabled:opacity-50"
          >
            <X className="h-4 w-4" /> {t('actions.reject_confirm')}
          </button>
          <button
            onClick={() => {
              setRejecting(false);
              setReason('');
            }}
            className="rounded-md border px-3 py-2 text-sm text-muted-foreground hover:bg-secondary"
          >
            {t('actions.cancel')}
          </button>
        </div>
      </div>
    );
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
        onClick={() => setRejecting(true)}
        disabled={busy}
        className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-destructive/30 px-3 py-2 text-sm text-destructive transition-colors hover:bg-destructive/10 disabled:opacity-50"
      >
        <X className="h-4 w-4" /> {t('actions.reject')}
      </button>
    </div>
  );
}
