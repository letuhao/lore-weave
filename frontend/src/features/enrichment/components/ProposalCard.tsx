import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { TechniqueBadge, VerifyBadge, ReviewStatusBadge, H0Marker } from './badges';
import type { Proposal } from '../types';

/** A scannable proposal summary. Click selects (no unmount — the detail is keyed by
 *  id and swaps via CSS/state, per the FE rules). Surfaces the H0 marker, confidence,
 *  the dimension/source counts, and (for needs_review) an advisory-flag preview;
 *  auto-rejected cards dim and show the reject reason instead of content. */
export function ProposalCard({
  proposal,
  selected,
  onSelect,
}: {
  proposal: Proposal;
  selected: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation('enrichment');
  const name = proposal.canonical_name || proposal.target_ref || '—';
  const verify = proposal.provenance_json?.canon_verify;
  const verifyStatus = proposal.provenance_json?.verify_status;
  const dimCount = Object.keys(proposal.provenance_json?.dimensions ?? {}).length;
  const srcCount = proposal.source_refs_json?.length ?? 0;
  const flagCount = verify?.flags?.length ?? 0;
  const autoRejected = verifyStatus === 'auto_rejected';

  return (
    <button
      onClick={onSelect}
      data-testid="enrichment-proposal-card"
      className={cn(
        'flex w-full flex-col gap-1 border-b px-3 py-2.5 text-left transition-colors last:border-b-0',
        selected ? 'border-l-2 border-l-primary bg-primary/5' : 'hover:bg-card/60',
        autoRejected && 'opacity-70',
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
        <H0Marker />
      </div>
      {autoRejected ? (
        <p className="text-[11px] text-destructive" data-testid="enrichment-card-reject-reason">
          {proposal.rejected_reason || t('card.auto_rejected')}
        </p>
      ) : (
        <p className="line-clamp-2 text-[11px] text-muted-foreground">{proposal.content}</p>
      )}
      <div className="flex flex-wrap items-center gap-x-2 font-mono text-[10px] text-muted-foreground">
        <span>{t('card.confidence', { value: proposal.confidence.toFixed(2) })}</span>
        <span aria-hidden>·</span>
        <span data-testid="enrichment-card-summary">
          {t('card.summary', { dims: dimCount, sources: srcCount })}
        </span>
      </div>
      {!autoRejected && flagCount > 0 && (
        <div className="space-y-0.5" data-testid="enrichment-card-advisory">
          {/* #8: show the flag KIND + evidence inline (e.g. "REGURGITATION · 逐字重合 14 字"),
              not just a count — the kind is a technical token shown raw (like the tier). */}
          {(verify?.flags ?? []).slice(0, 2).map((f, i) => (
            <p key={i} className="flex items-start gap-1 text-[11px] text-warning">
              <span className="shrink-0 rounded bg-warning/15 px-1 font-mono text-[10px] uppercase">
                {f.kind}
              </span>
              {f.evidence && <span className="line-clamp-1">{f.evidence}</span>}
            </p>
          ))}
          {flagCount > 2 && (
            <p className="text-[10px] text-muted-foreground">{t('card.advisory', { count: flagCount })}</p>
          )}
        </div>
      )}
    </button>
  );
}
