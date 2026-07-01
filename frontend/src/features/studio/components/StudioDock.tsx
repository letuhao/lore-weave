// The centre dock — dockview owns all layout here (drag / split / stack / float / pop-out).
// A thin wrapper: the panel-component registry + the theme + the layout hook. Real tool
// panels are registered in PANEL_COMPONENTS one at a time as they're built.
import type { MutableRefObject } from 'react';
import { DockviewReact, themeAbyss, type DockviewApi, type DockviewReadyEvent } from 'dockview-react';
import 'dockview-core/dist/styles/dockview.css';
import { useStudioLayout } from '../hooks/useStudioLayout';
import { STUDIO_PANEL_COMPONENTS } from '../panels/catalog';

const PANEL_COMPONENTS = STUDIO_PANEL_COMPONENTS;

/** apiRef (optional) mirrors the dockview api up to the frame so the Command Palette can open
 * panels into the dock. */
export function StudioDock({ bookId, apiRef }: { bookId: string; apiRef?: MutableRefObject<DockviewApi | null> }) {
  const { onReady } = useStudioLayout(bookId);
  const handleReady = (event: DockviewReadyEvent) => {
    onReady(event);
    if (apiRef) apiRef.current = event.api;
  };
  return (
    <div data-testid="studio-dock" className="relative min-h-0 flex-1">
      <DockviewReact
        onReady={handleReady}
        components={PANEL_COMPONENTS}
        theme={themeAbyss}
        className="absolute inset-0"
      />
    </div>
  );
}
