// 14_utility_panels.md B1 — the `jobs-list` dock panel: the unified Jobs dashboard (summary
// cards + filters + Active/History tables), user-scoped (no bookId anywhere). Thin view over
// the SAME JobsStreamProvider/JobsList/JobsMobile the standalone /jobs page uses (DOCK-2 — no
// fork). Row clicks open `job-detail` as a sibling dock tab via host.openPanel (DOCK-7 — the
// injected onOpenDetail callback replaces JobRow/JobCard's default route link, mirroring the
// NotificationsPanel → NotificationItem.onClick → followStudioLink precedent).
import type { IDockviewPanelProps } from 'dockview-react';
import { useIsMobile } from '@/hooks/useIsMobile';
import { JobsStreamProvider } from '@/features/jobs/context/JobsStreamProvider';
import { JobsList } from '@/features/jobs/components/JobsList';
import { JobsMobile } from '@/features/jobs/components/mobile/JobsMobile';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function JobsListPanel(props: IDockviewPanelProps) {
  useStudioPanel('jobs-list', props.api);
  const host = useStudioHost();
  const isMobile = useIsMobile();

  const onOpenDetail = (service: string, jobId: string) => {
    host.openPanel('job-detail', { params: { service, jobId } });
  };

  return (
    <div data-testid="studio-jobs-list-panel" className="h-full min-h-0 overflow-auto p-4">
      <JobsStreamProvider>
        {isMobile ? (
          <JobsMobile onOpenDetail={onOpenDetail} />
        ) : (
          <JobsList onOpenDetail={onOpenDetail} />
        )}
      </JobsStreamProvider>
    </div>
  );
}
