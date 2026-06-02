import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useEnrichmentContext, type EnrichmentPanel } from '../context/EnrichmentContext';
import { ProposalsPanel } from './ProposalsPanel';
import { GapsPanel } from './GapsPanel';
import { SourcesPanel } from './SourcesPanel';
import { JobsPanel } from './JobsPanel';
import { H0Marker } from './badges';

const PANELS: EnrichmentPanel[] = ['proposals', 'gaps', 'sources', 'jobs'];

/** The feature shell: H0 chip + a secondary tab strip over the four panels. Panels
 *  are lazy-mounted on first visit then kept mounted (CSS `hidden`), so switching
 *  sub-tabs never destroys a panel's state — same idiom the book tabs use. */
export function EnrichmentView() {
  const { t } = useTranslation('enrichment');
  const { activePanel, setActivePanel } = useEnrichmentContext();
  const [visited] = useState(() => new Set<EnrichmentPanel>([activePanel]));
  visited.add(activePanel);

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
              'border-b-2 px-3 py-2 text-xs font-medium transition-colors',
              activePanel === p
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t(`panel.${p}`)}
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
    </div>
  );
}
