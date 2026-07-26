// 14_utility_panels.md B2 — the `job-detail` dock panel: singleton, retargets via params
// {service, jobId} (json-editor/skill-editor precedent, docs/standards/dockable-gui.md DOCK-6).
// Thin view over the SAME JobsStreamProvider/JobMonitor the standalone
// /jobs/:service/:jobId page uses (DOCK-2 — no fork). JobMonitor's back-breadcrumb is hidden
// via the injected `hideBack` prop instead of route-navigating (DOCK-7) — the dock tabs already
// show what's open.
import { useEffect, useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { JobsStreamProvider } from '@/features/jobs/context/JobsStreamProvider';
import { JobMonitor } from '@/features/jobs/components/JobMonitor';
import { useStudioPanel } from './useStudioPanel';

interface JobDetailParams { service?: unknown; jobId?: unknown }

const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);

export function JobDetailPanel(props: IDockviewPanelProps) {
  useStudioPanel('job-detail', props.api);
  const { t } = useTranslation('studio');

  // Retarget on EVERY updateParameters (R3 singleton — json-editor precedent: the event fires
  // on every call, so clicking a different job row while job-detail is already open still lands).
  const p = (props.params ?? {}) as JobDetailParams;
  const [target, setTarget] = useState<{ service: string | null; jobId: string | null }>({
    service: str(p.service), jobId: str(p.jobId),
  });
  useEffect(() => {
    const d = props.api.onDidParametersChange?.((next: Record<string, unknown> | undefined) => {
      const np = (next ?? {}) as JobDetailParams;
      setTarget({ service: str(np.service), jobId: str(np.jobId) });
    });
    return () => d?.dispose?.();
  }, [props.api]);

  if (!target.service || !target.jobId) {
    return (
      <div data-testid="studio-job-detail-panel" className="p-4 text-xs text-muted-foreground">
        {t('panels.job-detail.empty', { defaultValue: 'Open a job from the Jobs panel to watch it here.' })}
      </div>
    );
  }

  return (
    <div data-testid="studio-job-detail-panel" className="h-full min-h-0 overflow-auto p-4">
      <JobsStreamProvider>
        <JobMonitor service={target.service} jobId={target.jobId} hideBack />
      </JobsStreamProvider>
    </div>
  );
}
