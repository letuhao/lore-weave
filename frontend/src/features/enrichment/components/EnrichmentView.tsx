import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useEnrichmentContext, type EnrichmentPanel } from '../context/EnrichmentContext';
import { useProposals } from '../hooks/useProposals';
import { useEnrichmentSources } from '../hooks/useEnrichmentSources';
import { useEnrichmentJobs } from '../hooks/useEnrichmentJobs';
import { ProposalsPanel } from './ProposalsPanel';
import { GapsPanel } from './GapsPanel';
import { SourcesPanel } from './SourcesPanel';
import { JobsPanel } from './JobsPanel';
import { SettingsPanel } from './SettingsPanel';
import { H0Marker } from './badges';

const PANELS: EnrichmentPanel[] = ['proposals', 'gaps', 'sources', 'jobs', 'settings'];

/** The feature shell: H0 chip + a secondary tab strip (with live count badges) over
 *  the four panels. Panels are lazy-mounted on first visit then kept mounted (CSS
 *  `hidden`), so switching sub-tabs never destroys a panel's state. The count hooks
 *  share react-query cache with the panels (same query keys) — no double fetch. */
export function EnrichmentView() {
  const { t } = useTranslation('enrichment');
  const { bookId, activePanel, setActivePanel, gapCount } = useEnrichmentContext();
  const [visited] = useState(() => new Set<EnrichmentPanel>([activePanel]));
  visited.add(activePanel);

  // LE-065 — tab count badges. proposals uses the unfiltered ('all') total so the
  // badge reflects the whole book, not the active status filter inside the panel.
  const { total: proposalCount } = useProposals(bookId);
  const { total: sourceCount } = useEnrichmentSources(bookId);
  const { total: jobCount } = useEnrichmentJobs(bookId);
  const counts: Record<EnrichmentPanel, number | null> = {
    proposals: proposalCount,
    gaps: gapCount,
    sources: sourceCount,
    jobs: jobCount,
    settings: null, // no count badge for the profile-authoring tab
  };

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">{t('header')}</h3>
        <H0Marker />
      </div>
      <p className="-mt-2 text-xs text-muted-foreground">{t('subtitle')}</p>

      <div className="flex gap-1 border-b">
        {PANELS.map((p) => (
          <button
            key={p}
            onClick={() => setActivePanel(p)}
            data-testid={`enrichment-tab-${p}`}
            className={cn(
              'inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-xs font-medium transition-colors',
              activePanel === p
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t(`panel.${p}`)}
            {counts[p] != null && counts[p]! > 0 && (
              <span
                data-testid={`enrichment-tab-count-${p}`}
                className={cn(
                  'rounded-full px-1.5 py-0.5 text-[10px] font-semibold',
                  activePanel === p ? 'bg-primary/15 text-primary' : 'bg-secondary text-muted-foreground',
                )}
              >
                {counts[p]}
              </span>
            )}
          </button>
        ))}
      </div>

      {visited.has('proposals') && (
        <div className={activePanel === 'proposals' ? '' : 'hidden'}>
          <ProposalsPanel />
        </div>
      )}
      {visited.has('gaps') && (
        <div className={activePanel === 'gaps' ? '' : 'hidden'}>
          <GapsPanel />
        </div>
      )}
      {visited.has('sources') && (
        <div className={activePanel === 'sources' ? '' : 'hidden'}>
          <SourcesPanel />
        </div>
      )}
      {visited.has('jobs') && (
        <div className={activePanel === 'jobs' ? '' : 'hidden'}>
          <JobsPanel />
        </div>
      )}
      {visited.has('settings') && (
        <div className={activePanel === 'settings' ? '' : 'hidden'}>
          <SettingsPanel />
        </div>
      )}
    </div>
  );
}
