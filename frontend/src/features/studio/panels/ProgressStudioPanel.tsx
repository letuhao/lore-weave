// Studio `progress` (category: editor, NOT a quality card — a word-count streak is not a quality
// judgment; D-S6-PROGRESS-CAT). Ports the composition ProgressPanel: words today / streak / book
// total / editable daily goal / 7-30 sparkline. The word-count reporting is a write-only loop until
// something reads it — this is that reader. Gated on a Work (offers the Set-up-co-writer CTA on a
// fresh book). BE-P2: the goal is per-user (no shared work.settings), so the panel no longer needs a
// settings blob.
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { ProgressPanel } from '@/features/composition/components/ProgressPanel';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { QualityWorkGate } from './QualityNoWorkState';
import { useQualityWork } from './useQualityWork';

export function ProgressStudioPanel(props: IDockviewPanelProps) {
  useStudioPanel('progress', props.api);
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const work = useQualityWork(host.bookId, accessToken);

  if (work.kind !== 'ready') {
    return <QualityWorkGate state={work} testIdPrefix="progress" bookId={host.bookId} token={accessToken} />;
  }

  return (
    <div data-testid="studio-progress-panel" className="h-full min-h-0 overflow-auto">
      <ProgressPanel bookId={host.bookId} projectId={work.projectId} token={accessToken} />
    </div>
  );
}
