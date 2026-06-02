import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { ProposalCard } from './ProposalCard';
import type { Proposal, ReviewStatus, Tier } from '../types';

const STATUSES: (ReviewStatus | 'all')[] = [
  'all',
  'proposed',
  'approved',
  'promoted',
  'rejected',
];

const TIERS: (Tier | 'all')[] = ['all', 'P1', 'P2', 'P3'];

/** Left pane: search + status filter + (when a book's enrichment spans >1 general
 *  project) a client-side project picker, over a scrollable list of ProposalCards. */
export function ProposalList({
  items,
  selectedId,
  onSelect,
  search,
  onSearch,
  status,
  onStatus,
  tier,
  onTier,
  projectIds,
  projectFilter,
  onProjectFilter,
}: {
  items: Proposal[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  search: string;
  onSearch: (s: string) => void;
  status: ReviewStatus | 'all';
  onStatus: (s: ReviewStatus | 'all') => void;
  tier: Tier | 'all';
  onTier: (tier: Tier | 'all') => void;
  projectIds: string[];
  projectFilter: string | null;
  onProjectFilter: (p: string | null) => void;
}) {
  const { t } = useTranslation('enrichment');

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-2 border-b p-3">
        <input
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder={t('proposals.search')}
          data-testid="enrichment-search"
          className="w-full rounded-md border bg-background px-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
        />
        <div className="flex flex-wrap gap-1">
          {STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => onStatus(s)}
              className={cn(
                'rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors',
                status === s
                  ? 'bg-primary/15 text-primary'
                  : 'bg-secondary text-muted-foreground hover:text-foreground',
              )}
            >
              {s === 'all' ? t('proposals.status_all') : t(`review.${s}`)}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-[10px] text-muted-foreground">{t('proposals.technique')}:</span>
          {TIERS.map((tg) => (
            <button
              key={tg}
              onClick={() => onTier(tg)}
              data-testid={`enrichment-tier-${tg}`}
              className={cn(
                'rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors',
                tier === tg
                  ? 'bg-primary/15 text-primary'
                  : 'bg-secondary text-muted-foreground hover:text-foreground',
              )}
            >
              {tg === 'all' ? t('proposals.status_all') : tg}
            </button>
          ))}
        </div>
        {projectIds.length > 1 && (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-[10px] text-muted-foreground">{t('proposals.project')}:</span>
            <button
              onClick={() => onProjectFilter(null)}
              className={cn(
                'rounded-full px-2 py-0.5 text-[10px]',
                !projectFilter ? 'bg-primary/15 text-primary' : 'bg-secondary text-muted-foreground',
              )}
            >
              {t('proposals.all_projects')}
            </button>
            {projectIds.map((pid) => (
              <button
                key={pid}
                onClick={() => onProjectFilter(pid)}
                title={pid}
                className={cn(
                  'rounded-full px-2 py-0.5 font-mono text-[10px]',
                  projectFilter === pid ? 'bg-primary/15 text-primary' : 'bg-secondary text-muted-foreground',
                )}
              >
                {pid.slice(0, 8)}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="flex-1 overflow-y-auto">
        {items.length === 0 ? (
          <p className="p-4 text-center text-xs text-muted-foreground">{t('proposals.none')}</p>
        ) : (
          items.map((p) => (
            <ProposalCard
              key={p.proposal_id}
              proposal={p}
              selected={p.proposal_id === selectedId}
              onSelect={() => onSelect(p.proposal_id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
