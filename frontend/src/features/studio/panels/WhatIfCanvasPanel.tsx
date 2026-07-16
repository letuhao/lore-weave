// close-21-28 O-11 — the what-if branch-preview PRODUCER, in the Studio.
//
// The gap this closes (plan §6.4 O-11): spec 36 ported the CONSUMER
// (`PromoteWhatIfButton` → divergence) but NOT the producer. The what-if branch
// canvas — ephemeral scene branches, alt-take generation, judge badges — lives in
// `SceneGraphCanvas` (features/composition), which the legacy CompositionPanel page
// hosts; once Wave 6 retires that page (`graph → plan-hub`), the capability would
// vanish and `PromoteWhatIfButton` would have nothing to promote. This mounts the
// EXISTING self-contained producer in a Studio panel (the GroundingPanel precedent —
// SceneInspectorPanel imports it as-is), so the capability survives the port with no
// 449-LOC re-implementation. `plan-hub` remains the graph VIEW's home; this is the
// what-if EDITING surface it does not carry.
import type { IDockviewPanelProps } from 'dockview-react';

import { useAuth } from '@/auth';
import { SceneGraphCanvas } from '@/features/composition/components/SceneGraphCanvas';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';

import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function WhatIfCanvasPanel(props: IDockviewPanelProps) {
  useStudioPanel('whatif-canvas', props.api);
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const workQ = useWorkResolution(host.bookId, accessToken);
  const { data: activeWorkId } = useActiveWorkId(host.bookId, accessToken);
  // useWorkResolution resolves to the ENVELOPE `WorkResolution {status, work, candidates}`, not a bare
  // Work — SceneGraphCanvas needs the inner Work (it reads `work.settings`, `work.project_id`). Resolve
  // the ACTIVE Work (EC-3d: the user's per-book pref, else canonical), so a "Switch to" a dị bản opens
  // its what-if canvas, not always canon's. (Passing the raw envelope crashed the canvas on
  // `work.settings` — caught by the O-11 promote-flow live smoke; the unit test had mocked a bare work,
  // which hid the shape mismatch.)
  const work = resolveActiveWork(workQ.data, activeWorkId);

  if (!work) {
    // No composition Work yet ⇒ no scene graph to branch. A calm empty state, not an error —
    // the book has not been planned/compiled, so there is nothing to run a what-if against.
    return (
      <div
        data-testid="whatif-canvas-nowork"
        className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground"
      >
        This book has no plan yet — lay out its arcs and chapters first, then explore
        &ldquo;what if&rdquo; branches here.
      </div>
    );
  }

  return (
    <div data-testid="whatif-canvas" className="h-full min-h-0">
      <SceneGraphCanvas work={work} bookId={host.bookId} token={accessToken} />
    </div>
  );
}
