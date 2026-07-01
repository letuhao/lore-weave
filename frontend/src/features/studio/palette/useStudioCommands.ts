// #06b Command Palette — the command set. Static chrome commands (View: …) + one "Studio: Open …"
// per REGISTERED dock tool (labels come from the registration, never hardcoded — C3). The Panels
// group is empty until panels register (incremental port); chrome commands ship on their own.
import type { StudioToolRegistration } from '../host/types';
import type { ActivityView } from '../types';

export interface StudioCommand {
  id: string;
  label: string;
  description?: string;
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
  const desc = (key: string, dflt: string) => t(`palette.desc.${key}`, { defaultValue: dflt });

  const cmds: StudioCommand[] = [];

  // Panels — dynamic, from the registry (empty until panels register). Description from the reg.
  for (const tool of tools) {
    cmds.push({ id: tool.commandId, label: tool.paletteCommand, description: tool.description, group: group('panels', 'Panels'), run: () => onOpenPanel(tool.panelId) });
  }

  // Navigate — switch the active navigator + jump to a location.
  const nav = group('navigate', 'Navigate');
  cmds.push({ id: 'view.showManuscript', label: cmd('showManuscript', 'View: Show Manuscript'), description: desc('showManuscript', 'Chapters & scenes'), group: nav, run: () => chrome.setActiveView('manuscript') });
  cmds.push({ id: 'view.showBible', label: cmd('showBible', 'View: Show Story Bible'), description: desc('showBible', 'Cast, world & canon'), group: nav, run: () => chrome.setActiveView('bible') });
  cmds.push({ id: 'view.showSearch', label: cmd('showSearch', 'View: Show Search'), description: desc('showSearch', 'Full-text & semantic'), group: nav, run: () => chrome.setActiveView('search') });
  cmds.push({ id: 'view.showQuality', label: cmd('showQuality', 'View: Show Quality'), description: desc('showQuality', 'Critic, promises & canon'), group: nav, run: () => chrome.setActiveView('quality') });
  cmds.push({ id: 'view.goToChapter', label: cmd('goToChapter', 'View: Go to Chapter…'), description: desc('goToChapter', 'Open Quick Open'), group: nav, run: onOpenQuickOpen });

  // Layout — chrome toggles.
  const layout = group('layout', 'Layout');
  cmds.push({ id: 'view.toggleSidebar', label: cmd('toggleSidebar', 'View: Toggle Side Bar'), description: desc('toggleSidebar', 'Show or hide the side bar'), group: layout, run: chrome.toggleSidebar });
  cmds.push({ id: 'view.toggleBottom', label: cmd('toggleBottom', 'View: Toggle Bottom Panel'), description: desc('toggleBottom', 'Jobs · Generation · Issues'), group: layout, run: chrome.toggleBottom });

  return cmds;
}

/** Case-insensitive substring filter on the command label. */
export function filterCommands(cmds: StudioCommand[], query: string): StudioCommand[] {
  const q = query.trim().toLowerCase();
  if (!q) return cmds;
  return cmds.filter((c) => c.label.toLowerCase().includes(q));
}
