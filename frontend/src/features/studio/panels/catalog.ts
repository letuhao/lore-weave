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
import { UsagePanel } from './UsagePanel';
import { NotificationsPanel } from './NotificationsPanel';
import { SettingsPanel } from './SettingsPanel';
import { TrashPanel } from './TrashPanel';
import { JsonEditorPanel } from './JsonEditorPanel';

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
  // #11 W2 — user-scoped panels (dockable migration wave 1).
  { id: 'usage', component: UsagePanel, titleKey: 'panels.usage.title', descKey: 'panels.usage.desc' },
  { id: 'notifications', component: NotificationsPanel, titleKey: 'panels.notifications.title', descKey: 'panels.notifications.desc' },
  { id: 'settings', component: SettingsPanel, titleKey: 'panels.settings.title', descKey: 'panels.settings.desc' },
  { id: 'trash', component: TrashPanel, titleKey: 'panels.trash.title', descKey: 'panels.trash.desc' },
  // #12 R3/R4 — singleton, retargets via params {docType, resourceId}; opened by "Open as JSON"
  // affordances only (hidden from palette ⇒ outside the agent enum, no contract change this cycle).
  { id: 'json-editor', component: JsonEditorPanel, titleKey: 'panels.jsonEditor.title', descKey: 'panels.jsonEditor.desc', hiddenFromPalette: true },
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
