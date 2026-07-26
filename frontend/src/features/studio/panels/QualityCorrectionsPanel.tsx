// Studio Quality tab — `quality-corrections`: your accept / edit / pick-other / regenerate / reject
// rates on AI drafts, the within-author A/B quality signal (spec §6). DISPLAY-ONLY per the S6 charter
// — the capture seam (accept/reject → generation_correction) is S1's; this only READS the stats route.
//
// A PORT of the CorrectionStatsTable extracted from QualityPanel (F-Q11 — NOT QualityPanel whole,
// whose other half already ships as `quality-coverage`, a paid pass). Gated on a composition Work
// (offers the Set-up-co-writer CTA on a fresh book, D0); an errored fetch is `unavailable` (we could
// not look), never a false "clean/empty".
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { useCorrectionStats } from '@/features/composition/hooks/useCorrectionStats';
import { CorrectionStatsTable } from '@/features/composition/components/CorrectionStatsTable';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { QualityWorkGate } from './QualityNoWorkState';
import { useQualityWork } from './useQualityWork';

export function QualityCorrectionsPanel(props: IDockviewPanelProps) {
  useStudioPanel('quality-corrections', props.api);
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const work = useQualityWork(host.bookId, accessToken);

  if (work.kind !== 'ready') {
    return <QualityWorkGate state={work} testIdPrefix="quality-corrections" bookId={host.bookId} token={accessToken} />;
  }
  return <CorrectionsBody projectId={work.projectId} token={accessToken} />;
}

function CorrectionsBody({ projectId, token }: { projectId: string; token: string | null }) {
  const { t } = useTranslation('composition');
  const stats = useCorrectionStats(projectId, token);

  return (
    <div data-testid="studio-quality-corrections-panel" className="flex h-full min-h-0 flex-col gap-2 overflow-auto p-3 text-sm">
      {stats.isLoading && (
        <div data-testid="quality-corrections-loading" className="p-4 text-neutral-500">
          {t('loadingStats', { defaultValue: 'Loading quality…' })}
        </div>
      )}
      {/* unavailable ≠ empty: an errored fetch means we could not LOOK, not that there are no
          corrections. Never render it as a clean/cold-start state (the same no-silent-fail rule the
          canon panel and useQualityWork enforce). */}
      {stats.isError && (
        <div data-testid="quality-corrections-unavailable" className="rounded bg-amber-50 p-2 text-xs text-amber-700 dark:bg-amber-950 dark:text-amber-300">
          {t('statsUnavailable', { defaultValue: 'Quality stats unavailable — could not reach the co-writer service. Rates may exist; we could not look.' })}
        </div>
      )}
      {stats.data && <CorrectionStatsTable stats={stats.data} />}
    </div>
  );
}
