// Studio `flywheel` (category: knowledge — D-S6-F1). The canon-growth reward: after a publish's
// extraction completes, "+N entities / +N relations / +N events" your last chapter ADDED to canon,
// with clickable highlights. The panel that makes the loop feel closed — publishing pays you back.
//
// A PORT of the composition FlywheelPanel (render + hook + read route all ship). The one real porting
// decision is the DEEP-LINK RETARGET: legacy wired onOpenCast/Timeline/Relations to an in-page tab
// switch (CompositionPanel.selectTab), but the dock has PANELS, not tabs — so they retarget to
// host.openPanel of S7's cast / kg-timeline / kg-graph panels. (Porting the render without retargeting
// would ship three dead chips.)
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { FlywheelPanel } from '@/features/composition/components/FlywheelPanel';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { QualityWorkGate } from './QualityNoWorkState';
import { useQualityWork } from './useQualityWork';

export function FlywheelStudioPanel(props: IDockviewPanelProps) {
  useStudioPanel('flywheel', props.api);
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const work = useQualityWork(host.bookId, accessToken);

  if (work.kind !== 'ready') {
    return <QualityWorkGate state={work} testIdPrefix="flywheel" bookId={host.bookId} token={accessToken} />;
  }

  return (
    <div data-testid="studio-flywheel-panel" className="h-full min-h-0 overflow-auto">
      <FlywheelPanel
        projectId={work.projectId}
        token={accessToken}
        // Retarget the in-page tab switches to dock panels (S7's homes). A chip whose target isn't
        // registered yet still opens gracefully (openPanel is a no-op if the id is unknown) rather
        // than firing a dead selectTab.
        onOpenCast={(name) => host.openPanel('cast', name ? { params: { focusName: name } } : undefined)}
        onOpenTimeline={() => host.openPanel('kg-timeline')}
        onOpenRelations={() => host.openPanel('kg-graph')}
      />
    </div>
  );
}
