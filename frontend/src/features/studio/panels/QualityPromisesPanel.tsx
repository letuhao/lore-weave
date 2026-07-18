// Studio Quality tab — `quality-promises`: the open-promise debt ledger
// (narrative_thread table, generation-time detected). DOCK-2 — thin wrapper,
// reuses ThreadsPanel + useWorkResolution AS-IS from the LOOM composition
// workspace (no fork). Unlike that workspace's `narrative_thread_enabled`
// settings gate (which only declutters an always-visible sidebar), Quality is
// opt-in navigation by definition, so this always renders when a Work exists.
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { ThreadsPanel } from '@/features/composition/components/ThreadsPanel';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { QualityWorkGate } from './QualityNoWorkState';
import { useQualityWork } from './useQualityWork';

/** 24 PH18 — the Plan Hub's thread badge deep-links here with the `narrative_thread.id`, which IS
 *  what this panel lists (unlike the canon lens, whose rows carry no rule id). */
interface PromisesFocusParams {
  focusThreadId?: string | null;
}

export function QualityPromisesPanel(props: IDockviewPanelProps) {
  useStudioPanel('quality-promises', props.api);
  const focusThreadId = (props.params as PromisesFocusParams | undefined)?.focusThreadId ?? null;
  const host = useStudioHost();
  const { accessToken } = useAuth();
  // `unavailable` (composition-service is DOWN) must NOT render as "no co-writer session yet" —
  // unconsulted is not empty. See useQualityWork / RUN-STATE DR-27.
  const work = useQualityWork(host.bookId, accessToken);
  if (work.kind !== 'ready') return <QualityWorkGate state={work} testIdPrefix="quality-promises" bookId={host.bookId} token={accessToken} />;

  return (
    <div data-testid="studio-quality-promises-panel" className="h-full min-h-0 overflow-auto">
      <ThreadsPanel projectId={work.projectId} token={accessToken} enabled focusThreadId={focusThreadId} />
    </div>
  );
}
