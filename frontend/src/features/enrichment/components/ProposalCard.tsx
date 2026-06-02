import { cn } from '@/lib/utils';
import { TechniqueBadge, VerifyBadge, ReviewStatusBadge } from './badges';
import type { Proposal } from '../types';

/** A scannable proposal summary. Click selects (no unmount — the detail is keyed by
 *  id and swaps via CSS/state, per the FE rules). */
export function ProposalCard({
  proposal,
  selected,
  onSelect,
}: {
  proposal: Proposal;
  selected: boolean;
  onSelect: () => void;
}) {
  const name = proposal.canonical_name || proposal.target_ref || '—';
  const verifyStatus = proposal.provenance_json?.verify_status;

  return (
    <button
      onClick={onSelect}
      data-testid="enrichment-proposal-card"
      className={cn(
        'flex w-full flex-col gap-1 border-b px-3 py-2.5 text-left transition-colors last:border-b-0',
        selected ? 'border-l-2 border-l-primary bg-primary/5' : 'hover:bg-card/60',
      )}
    >
      <div className="flex items-center gap-2">
        <span className={cn('truncate font-serif text-sm', selected && 'font-medium')}>{name}</span>
        <span className="ml-auto shrink-0">
          <ReviewStatusBadge status={proposal.review_status} />
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <TechniqueBadge technique={proposal.technique} />
        <VerifyBadge status={verifyStatus} />
      </div>
      <p className="line-clamp-1 text-[11px] text-muted-foreground">{proposal.content}</p>
    </button>
  );
}
