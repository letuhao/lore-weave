// S7·2 — the `world-map` dock panel. Thin: registers with the studio host (palette/agent rack +
// self-title), resolves its subject from props.params (a {worldId?, mapId?} deep-link — same seam
// as quality-canon's CanonFocusParams), and renders the editor body from features/world. All logic
// lives in useWorldMapEditor; the view is WorldMapEditor. Root data-testid="studio-world-map-panel".
import type { IDockviewPanelProps } from 'dockview-react';
import { WorldMapEditor } from '@/features/world/components/WorldMapEditor';
import { useWorldMapEditor, type WorldMapFocusParams } from '@/features/world/hooks/useWorldMapEditor';
import { useStudioPanel } from './useStudioPanel';

export function WorldMapEditorPanel(props: IDockviewPanelProps) {
  useStudioPanel('world-map', props.api);
  const ctl = useWorldMapEditor(props.params as WorldMapFocusParams | undefined);
  return (
    <div data-testid="studio-world-map-panel" className="h-full min-h-0">
      <WorldMapEditor ctl={ctl} />
    </div>
  );
}
