import type { IDockviewPanelProps } from 'dockview-react';
import { ContextInspectorView } from '@/features/chat/inspector/ContextInspectorView';
import { useStudioPanel } from './useStudioPanel';

// Context Compiler · Trace Inspector — the dockable studio panel (spec §11). Thin
// wrapper (DOCK-2): registers + self-titles via useStudioPanel, then renders the
// shared ContextInspectorView (also used by the standalone /context-inspector
// route). The view is self-contained (lists sessions + picks one) so it needs no
// studio/book context. Dockview keeps it mounted-but-hidden — MVC no-remount.
export function ContextInspectorPanel(props: IDockviewPanelProps) {
  useStudioPanel('context-inspector', props.api);
  return (
    <div className="h-full min-h-0" data-testid="studio-context-inspector-panel">
      <ContextInspectorView />
    </div>
  );
}
