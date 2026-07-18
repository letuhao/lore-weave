// #06b Command Palette — the command set. Static chrome commands (View: …) + one "Studio: Open …"
// per catalog panel (STUDIO_PANELS — every buildable panel, so a CLOSED panel is still openable;
// the mount-scoped registry drives the agent rack, not this list). Chrome commands ship on their own.
import type { StudioPanelDef, StudioPanelCategory } from '../panels/catalog';
import type { ActivityView } from '../types';

export interface StudioCommand {
  id: string;
  label: string;
  description?: string;
  group: string;
  run: () => void;
}

// #18 — fixed display order for panel-command sub-groups, NOT alphabetical: categories sit
// directly after Recent (highest command volume = primary discovery surface), before the static
// Navigate/Layout groups. A panel with no `category` (forward-compat guard) sorts last under the
// generic 'panels' fallback label — never dropped, never crashes.
// Exported so the #19 User Guide panel groups by the exact same order instead of duplicating it.
//
// X-2 — `quality` sits after `knowledge`, before `translation`: it reads the manuscript, so it
// groups with the other analysis surfaces. It was MISSING here while 5 `quality` panels shipped,
// and the failure modes are INVERTED: an un-categorized panel sorts LAST (harmless fallback), but
// an UNLISTED category indexOf()s to -1 and sorts FIRST — so all 5 sat above `editor` at the very
// top of the palette. "Forgot to add it" must be UNBUILDABLE, not merely ugly.
export const CATEGORY_ORDER = [
  'editor', 'storyBible', 'knowledge', 'quality', 'translation',
  'enrichment', 'sharing', 'platform', 'discovery', 'jobs',
] as const satisfies readonly StudioPanelCategory[];

// X-2 — compile-time exhaustiveness. A new StudioPanelCategory not listed above is now a TYPE ERROR.
// ⚠ The `as const satisfies` above is LOAD-BEARING, NOT STYLE: with the old `: StudioPanelCategory[]`
// annotation, `(typeof CATEGORY_ORDER)[number]` widens back to the full union, so `Exclude<>` is
// always `never` and this guard PASSES WHILE STILL MISSING 'quality'. Dropping the annotation is
// what gives the tuple its literal element type. Verify with `npx tsc --noEmit`, not vitest.
type _UnorderedCategory = Exclude<StudioPanelCategory, (typeof CATEGORY_ORDER)[number]>;
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const _CATEGORY_ORDER_IS_EXHAUSTIVE: [_UnorderedCategory] extends [never] ? true : never = true;

interface ChromeActions {
  setActiveView: (v: ActivityView) => void;
  toggleSidebar: () => void;
  toggleBottom: () => void;
}

type TFn = (key: string, opts?: Record<string, unknown>) => string;

export function buildStudioCommands(opts: {
  chrome: ChromeActions;
  panels: StudioPanelDef[];
  onOpenPanel: (panelId: string) => void;
  onOpenQuickOpen: () => void;
  /** #19 — re-run the Studio role picker on demand (never re-flips the seen flag). */
  onChooseYourFocus: () => void;
  /** #19 — start the `core` guided tour on demand. */
  onStartGuidedTour: () => void;
  t: TFn;
}): StudioCommand[] {
  const { chrome, panels, onOpenPanel, onOpenQuickOpen, onChooseYourFocus, onStartGuidedTour, t } = opts;
  const group = (k: string, dflt: string) => t(`palette.group.${k}`, { defaultValue: dflt });
  const cmd = (key: string, dflt: string) => t(`palette.cmd.${key}`, { defaultValue: dflt });
  const desc = (key: string, dflt: string) => t(`palette.desc.${key}`, { defaultValue: dflt });

  const cmds: StudioCommand[] = [];

  // Panels — from the static catalog (all buildable panels). Label "Studio: Open <name>".
  // Sorted by CATEGORY_ORDER (not catalog array order, which only loosely clusters by domain)
  // so the palette shell's adjacent-row group-header rendering produces clean, non-interleaved
  // sub-groups instead of one flat "Panels" bucket (#18).
  const byCategoryOrder = (a: StudioPanelDef, b: StudioPanelDef) => {
    const ai = a.category ? CATEGORY_ORDER.indexOf(a.category) : CATEGORY_ORDER.length;
    const bi = b.category ? CATEGORY_ORDER.indexOf(b.category) : CATEGORY_ORDER.length;
    return ai - bi;
  };
  for (const p of [...panels].sort(byCategoryOrder)) {
    const name = t(p.titleKey, { defaultValue: p.id });
    const categoryGroup = p.category
      ? group(p.category, p.category)
      : group('panels', 'Panels');
    cmds.push({
      id: `studio.openPanel.${p.id}`,
      label: t('palette.openPanel', { name, defaultValue: `Studio: Open ${name}` }),
      description: t(p.descKey, { defaultValue: '' }),
      group: categoryGroup,
      run: () => onOpenPanel(p.id),
    });
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

  // #19 — Help: re-run the role picker or start the guided tour on demand. Last group so it
  // never disrupts the #18 category header ordering above.
  const help = group('help', 'Help');
  cmds.push({ id: 'studio.chooseYourFocus', label: cmd('chooseYourFocus', 'Studio: Choose Your Focus'), description: desc('chooseYourFocus', 'Re-run the role picker'), group: help, run: onChooseYourFocus });
  cmds.push({ id: 'studio.startGuidedTour', label: cmd('startGuidedTour', 'Studio: Start Guided Tour'), description: desc('startGuidedTour', 'A quick tour of the core panels'), group: help, run: onStartGuidedTour });

  return cmds;
}

/** Case-insensitive substring filter on the command label. */
export function filterCommands(cmds: StudioCommand[], query: string): StudioCommand[] {
  const q = query.trim().toLowerCase();
  if (!q) return cmds;
  return cmds.filter((c) => c.label.toLowerCase().includes(q));
}
