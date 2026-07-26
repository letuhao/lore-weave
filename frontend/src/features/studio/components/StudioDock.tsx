// The centre dock — dockview owns all layout here (drag / split / stack / float / pop-out).
// A thin wrapper: the panel-component registry + the theme + the layout hook. Real tool
// panels are registered in PANEL_COMPONENTS one at a time as they're built.
import type { MutableRefObject } from 'react';
import { DockviewReact, type DockviewApi, type DockviewReadyEvent, type DockviewTheme } from 'dockview-react';
import 'dockview-core/dist/styles/dockview.css';
import './dockviewTheme.css';
import { useStudioLayout } from '../hooks/useStudioLayout';
import { STUDIO_PANEL_COMPONENTS } from '../panels/catalog';

const PANEL_COMPONENTS = STUDIO_PANEL_COMPONENTS;

// J2 — the dock chrome follows the APP theme (dockviewTheme.css maps every dockview
// color var to the index.css tokens). The stock themeAbyss painted a hard-coded navy
// regardless of [data-theme] — the "studio ignores the theme" bug.
const LOREWEAVE_DOCK_THEME: DockviewTheme = {
  name: 'loreweave',
  className: 'dockview-theme-loreweave',
  colorScheme: 'dark',
  tabGroupIndicator: 'none',
};

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
        theme={LOREWEAVE_DOCK_THEME}
        className="absolute inset-0"
      />
    </div>
  );
}
