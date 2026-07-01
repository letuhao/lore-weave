// The static catalog of buildable studio dock panels — every panel the studio CAN open, whether
// or not it's currently mounted. This is the source for:
//   • StudioDock's dockview component map (id → component)
//   • the Command Palette "Studio: Open …" commands (#06b) — a CLOSED panel must still be openable,
//     which a mount-scoped registry (useRegisteredTools) can't provide. The registry stays for the
//     AGENT rack (#07a — which tools are LIVE this turn); the catalog is what can be opened.
// Convention: `id` === the dockview component id (so host.openPanel adds `component: id`).
import type { FunctionComponent } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { WelcomePanel } from '../components/panels/WelcomePanel';
import { ComposePanel } from './ComposePanel';
import { EditorPanel } from './EditorPanel';
import { PlannerPanel } from '@/features/plan-forge/components/PlannerPanel';

export interface StudioPanelDef {
  id: string;
  component: FunctionComponent<IDockviewPanelProps>;
  /** i18n keys (studio namespace) for the dock tab title + palette description. */
  titleKey: string;
  descKey: string;
  /** Omit from the Command Palette "Open" list (e.g. the default Welcome placeholder). */
  hiddenFromPalette?: boolean;
}

export const STUDIO_PANELS: StudioPanelDef[] = [
  { id: 'compose', component: ComposePanel, titleKey: 'panels.compose.title', descKey: 'panels.compose.desc' },
  { id: 'editor', component: EditorPanel, titleKey: 'panels.editor.title', descKey: 'panels.editor.desc' },
  { id: 'planner', component: PlannerPanel, titleKey: 'panels.planner.title', descKey: 'panels.planner.desc' },
  { id: 'welcome', component: WelcomePanel, titleKey: 'welcome.tab', descKey: 'welcome.tab', hiddenFromPalette: true },
];

/** dockview component map (id → component) for StudioDock. */
export const STUDIO_PANEL_COMPONENTS: Record<string, FunctionComponent<IDockviewPanelProps>> =
  Object.fromEntries(STUDIO_PANELS.map((p) => [p.id, p.component]));

/** Panels offered in the Command Palette "Open" group. */
export const OPENABLE_STUDIO_PANELS = STUDIO_PANELS.filter((p) => !p.hiddenFromPalette);

export function getStudioPanelDef(id: string): StudioPanelDef | undefined {
  return STUDIO_PANELS.find((p) => p.id === id);
}
