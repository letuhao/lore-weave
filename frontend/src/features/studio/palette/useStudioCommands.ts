// #06b Command Palette — the command set. Static chrome commands (View: …) + one "Studio: Open …"
// per REGISTERED dock tool (labels come from the registration, never hardcoded — C3). The Panels
// group is empty until panels register (incremental port); chrome commands ship on their own.
import type { StudioToolRegistration } from '../host/types';
import type { ActivityView } from '../types';

export interface StudioCommand {
  id: string;
  label: string;
  group: string;
  run: () => void;
}

interface ChromeActions {
  setActiveView: (v: ActivityView) => void;
  toggleSidebar: () => void;
  toggleBottom: () => void;
}

type TFn = (key: string, opts?: Record<string, unknown>) => string;

export function buildStudioCommands(opts: {
  chrome: ChromeActions;
  tools: StudioToolRegistration[];
  onOpenPanel: (panelId: string) => void;
  onOpenQuickOpen: () => void;
  t: TFn;
}): StudioCommand[] {
  const { chrome, tools, onOpenPanel, onOpenQuickOpen, t } = opts;
  const group = (k: string, dflt: string) => t(`palette.group.${k}`, { defaultValue: dflt });
  const cmd = (key: string, dflt: string) => t(`palette.cmd.${key}`, { defaultValue: dflt });

  const cmds: StudioCommand[] = [];

  // Panels — dynamic, from the registry (empty until panels register).
  for (const tool of tools) {
    cmds.push({ id: tool.commandId, label: tool.paletteCommand, group: group('panels', 'Panels'), run: () => onOpenPanel(tool.panelId) });
  }

  // Navigate — switch the active navigator + jump to a location.
  const nav = group('navigate', 'Navigate');
  cmds.push({ id: 'view.showManuscript', label: cmd('showManuscript', 'View: Show Manuscript'), group: nav, run: () => chrome.setActiveView('manuscript') });
  cmds.push({ id: 'view.showBible', label: cmd('showBible', 'View: Show Story Bible'), group: nav, run: () => chrome.setActiveView('bible') });
  cmds.push({ id: 'view.showSearch', label: cmd('showSearch', 'View: Show Search'), group: nav, run: () => chrome.setActiveView('search') });
  cmds.push({ id: 'view.showQuality', label: cmd('showQuality', 'View: Show Quality'), group: nav, run: () => chrome.setActiveView('quality') });
  cmds.push({ id: 'view.goToChapter', label: cmd('goToChapter', 'View: Go to Chapter…'), group: nav, run: onOpenQuickOpen });

  // Layout — chrome toggles.
  const layout = group('layout', 'Layout');
  cmds.push({ id: 'view.toggleSidebar', label: cmd('toggleSidebar', 'View: Toggle Side Bar'), group: layout, run: chrome.toggleSidebar });
  cmds.push({ id: 'view.toggleBottom', label: cmd('toggleBottom', 'View: Toggle Bottom Panel'), group: layout, run: chrome.toggleBottom });

  return cmds;
}

/** Case-insensitive substring filter on the command label. */
export function filterCommands(cmds: StudioCommand[], query: string): StudioCommand[] {
  const q = query.trim().toLowerCase();
  if (!q) return cmds;
  return cmds.filter((c) => c.label.toLowerCase().includes(q));
}
