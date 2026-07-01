// The centre dock — dockview owns all layout here (drag / split / stack / float / pop-out).
// A thin wrapper: the panel-component registry + the theme + the layout hook. Real tool
// panels are registered in PANEL_COMPONENTS one at a time as they're built.
import { DockviewReact, themeAbyss, type IDockviewPanelProps } from 'dockview-react';
import 'dockview-core/dist/styles/dockview.css';
import { useStudioLayout } from '../hooks/useStudioLayout';
import { WelcomePanel } from './panels/WelcomePanel';

const PANEL_COMPONENTS: Record<string, React.FunctionComponent<IDockviewPanelProps>> = {
  welcome: WelcomePanel,
};

export function StudioDock({ bookId }: { bookId: string }) {
  const { onReady } = useStudioLayout(bookId);
  return (
    <div className="relative min-h-0 flex-1">
      <DockviewReact
        onReady={onReady}
        components={PANEL_COMPONENTS}
        theme={themeAbyss}
        className="absolute inset-0"
      />
    </div>
  );
}
