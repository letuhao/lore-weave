// LOOM Composition (V1 slice 5) — the eval-gate dashboard (view).
//
// Shows the per-mode correction rates that REPLACE the saturating auto-judge as
// the quality signal (spec §6). Within one Work the author is fixed, so the
// auto-vs-cowrite columns are a within-author A/B: lower edit/regenerate/reject
// + higher accept in `auto` = the diverge→converge reranker earns its latency.
// Cold-start safe: rates show "—" until generations accumulate.
import { useTranslation } from 'react-i18next';
import { useCorrectionStats } from '../hooks/useCorrectionStats';
import { BookPromiseCoverageSection } from './BookPromiseCoverageSection';
import { CorrectionStatsTable } from './CorrectionStatsTable';

export function QualityPanel({ projectId, token, modelRef }: { projectId: string; token: string | null; modelRef: string }) {
  const { t } = useTranslation('composition');
  const stats = useCorrectionStats(projectId, token);

  // The correction-stats table and the (independent) book-level promise coverage both live
  // here; render the stats part into a node so a stats loading/error state doesn't hide the
  // coverage section below it.
  const statsContent = (stats.isLoading || stats.isError || !stats.data)
    ? <Hint>{stats.isLoading
        ? t('loadingStats', { defaultValue: 'Loading quality…' })
        : t('statsUnavailable', { defaultValue: 'Quality stats unavailable.' })}</Hint>
    : <CorrectionStatsTable stats={stats.data} />;

  return (
    <div data-testid="composition-quality" className="flex flex-col gap-2 p-3 text-sm">
      {statsContent}
      <BookPromiseCoverageSection projectId={projectId} token={token} modelRef={modelRef} />
    </div>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return <div className="p-4 text-sm text-neutral-500">{children}</div>;
}
