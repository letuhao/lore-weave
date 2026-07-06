// Studio Quality tab — `quality-promises`: the open-promise debt ledger
// (narrative_thread table, generation-time detected). DOCK-2 — thin wrapper,
// reuses ThreadsPanel + useWorkResolution AS-IS from the LOOM composition
// workspace (no fork). Unlike that workspace's `narrative_thread_enabled`
// settings gate (which only declutters an always-visible sidebar), Quality is
// opt-in navigation by definition, so this always renders when a Work exists.
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { ThreadsPanel } from '@/features/composition/components/ThreadsPanel';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { Skeleton } from '@/components/shared';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { QualityNoWorkState } from './QualityNoWorkState';

export function QualityPromisesPanel(props: IDockviewPanelProps) {
  useStudioPanel('quality-promises', props.api);
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const resolution = useWorkResolution(host.bookId, accessToken);

  if (resolution.isLoading) {
    return (
      <div data-testid="quality-promises-loading" className="space-y-3 p-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  const projectId = resolution.data?.status === 'found' ? resolution.data.work?.project_id : null;
  if (!projectId) {
    return <QualityNoWorkState testId="quality-promises-no-work" />;
  }

  return (
    <div data-testid="studio-quality-promises-panel" className="h-full min-h-0 overflow-auto">
      <ThreadsPanel projectId={projectId} token={accessToken} enabled />
    </div>
  );
}
