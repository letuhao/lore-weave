import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles, AlertTriangle } from 'lucide-react';
import { Skeleton, EmptyState } from '@/components/shared';
import { useProposals } from '../hooks/useProposals';
import { useProposalActions } from '../hooks/useProposalActions';
import { useEnrichmentContext } from '../context/EnrichmentContext';
import { ProposalList } from './ProposalList';
import { ProposalDetail } from './ProposalDetail';
import { tierOf } from '../types';
import type { ReviewStatus, Tier } from '../types';

/** The review workspace (list ⇄ detail) — the e2e target. Owns the filter state +
 *  the proposals/actions hooks; project + search filtering is client-side over the
 *  book-scoped list. */
export function ProposalsPanel() {
  const { t } = useTranslation('enrichment');
  const { bookId, selectedProposalId, setSelectedProposalId, projectFilter, setProjectFilter } =
    useEnrichmentContext();
  const [status, setStatus] = useState<ReviewStatus | 'all'>('all');
  const [tier, setTier] = useState<Tier | 'all'>('all');
  const [search, setSearch] = useState('');

  const { items, isLoading, isError, projectIds } = useProposals(bookId, { reviewStatus: status });
  const actions = useProposalActions(bookId);

  const filtered = useMemo(
    () =>
      items.filter((p) => {
        if (projectFilter && p.project_id !== projectFilter) return false;
        if (tier !== 'all' && tierOf(p.technique) !== tier) return false;
        if (search) {
          const hay = `${p.canonical_name ?? ''}${p.target_ref ?? ''}${p.content}`.toLowerCase();
          if (!hay.includes(search.toLowerCase())) return false;
        }
        return true;
      }),
    [items, projectFilter, tier, search],
  );

  // Derive selection (no useEffect): the chosen id if still present, else the first.
  const selected =
    filtered.find((p) => p.proposal_id === selectedProposalId) ?? filtered[0] ?? null;

  if (isLoading && items.length === 0) {
    return (
      <div className="space-y-3 p-5">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex min-h-[200px] items-center justify-center p-8" role="alert" data-testid="enrichment-proposals-error">
        <div className="flex items-center gap-2 text-sm text-destructive">
          <AlertTriangle className="h-4 w-4" />
          {t('proposals.error')}
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[520px] overflow-hidden rounded-lg border" data-testid="enrichment-proposals">
      <div className="w-[320px] shrink-0 border-r bg-card/40">
        <ProposalList
          items={filtered}
          selectedId={selected?.proposal_id ?? null}
          onSelect={setSelectedProposalId}
          search={search}
          onSearch={setSearch}
          status={status}
          onStatus={setStatus}
          tier={tier}
          onTier={setTier}
          projectIds={projectIds}
          projectFilter={projectFilter}
          onProjectFilter={setProjectFilter}
        />
      </div>
      <div className="min-w-0 flex-1">
        {selected ? (
          <ProposalDetail key={selected.proposal_id} proposal={selected} actions={actions} />
        ) : (
          <div className="flex h-full items-center justify-center p-8">
            <EmptyState
              icon={Sparkles}
              title={t('proposals.empty.title')}
              description={t('proposals.empty.description')}
            />
          </div>
        )}
      </div>
    </div>
  );
}
