import { describe, expect, it, vi } from 'vitest';
import { buildStudioCommands, filterCommands } from '../useStudioCommands';
import { OPENABLE_STUDIO_PANELS, type StudioPanelDef } from '../../panels/catalog';

const t = (key: string, opts?: Record<string, unknown>) => (opts?.defaultValue as string) ?? key;

const chrome = () => ({ setActiveView: vi.fn(), toggleSidebar: vi.fn(), toggleBottom: vi.fn() });
const panel = (id: string): StudioPanelDef =>
  ({ id, component: (() => null) as unknown as StudioPanelDef['component'], titleKey: `panels.${id}.title`, descKey: `panels.${id}.desc` });

/** Shared no-op stubs for params every buildStudioCommands() call needs — keeps individual
 * tests focused on what they actually assert. */
const baseOpts = () => ({
  onOpenPanel: vi.fn(),
  onOpenQuickOpen: vi.fn(),
  onChooseYourFocus: vi.fn(),
  onStartGuidedTour: vi.fn(),
  t,
});

describe('buildStudioCommands', () => {
  it('always includes chrome commands (navigate + layout); no Panels without a catalog', () => {
    const c = chrome();
    const cmds = buildStudioCommands({ chrome: c, panels: [], ...baseOpts() });
    const ids = cmds.map((x) => x.id);
    expect(ids).toContain('view.showManuscript');
    expect(ids).toContain('view.toggleBottom');
    expect(ids).toContain('view.goToChapter');
    expect(cmds.some((x) => x.group === 'Panels')).toBe(false);
  });

  it('adds one "Studio: Open …" per CATALOG panel; run() opens by panel id', () => {
    const onOpenPanel = vi.fn();
    const cmds = buildStudioCommands({ chrome: chrome(), panels: [panel('cast')], ...baseOpts(), onOpenPanel });
    const p = cmds.find((x) => x.id === 'studio.openPanel.cast');
    // name = t(titleKey, {defaultValue: id}) → 'cast'; label = "Studio: Open cast" (openPanel default)
    expect(p?.label).toBe('Studio: Open cast');
    p?.run();
    expect(onOpenPanel).toHaveBeenCalledWith('cast');
  });

  it('the Context Inspector panel is palette-openable from the real catalog (§11 studio entry point)', () => {
    const onOpenPanel = vi.fn();
    const cmds = buildStudioCommands({
      chrome: chrome(),
      panels: OPENABLE_STUDIO_PANELS,
      ...baseOpts(),
      onOpenPanel,
    });
    const p = cmds.find((x) => x.id === 'studio.openPanel.context-inspector');
    expect(p).toBeDefined();
    // #18 — context-inspector is catalogued under 'editor', not the old flat 'Panels' bucket.
    expect(p!.group).toBe('editor');
    p!.run();
    expect(onOpenPanel).toHaveBeenCalledWith('context-inspector');
  });

  // #18 — domain-area grouping: a categorized panel groups by its category label; an
  // uncategorized one (forward-compat guard) falls back to the generic 'Panels' bucket.
  it('groups panel commands by category; uncategorized panels fall back to "Panels"', () => {
    const withCategory: StudioPanelDef = { ...panel('glossary'), category: 'storyBible' };
    const noCategory = panel('legacy-uncategorized');
    const cmds = buildStudioCommands({
      chrome: chrome(),
      panels: [withCategory, noCategory],
      ...baseOpts(),
    });
    expect(cmds.find((x) => x.id === 'studio.openPanel.glossary')?.group).toBe('storyBible');
    expect(cmds.find((x) => x.id === 'studio.openPanel.legacy-uncategorized')?.group).toBe('Panels');
  });

  // #18 B4 — panel commands sort by the fixed CATEGORY_ORDER, not catalog array order, so the
  // palette shell's adjacent-row group headers render clean (non-interleaved) sub-groups.
  //
  // X-2 — `quality` is fed FIRST and must land THIRD (editor → knowledge → quality → enrichment).
  // This is the assertion that would have red-flagged the bug the day the quality tab shipped:
  // `quality` was absent from CATEGORY_ORDER, so indexOf returned -1 and all 5 shipped quality
  // panels sorted ABOVE `editor` (index 0) at the very top of the palette. A category MISSING from
  // the catalog sorts LAST (harmless); one UNLISTED in CATEGORY_ORDER sorts FIRST (loud, wrong).
  it('sorts panel commands by the fixed category order regardless of input array order', () => {
    const quality: StudioPanelDef = { ...panel('quality-promises'), category: 'quality' };
    const enrichment: StudioPanelDef = { ...panel('enrichment-gaps'), category: 'enrichment' };
    const editor: StudioPanelDef = { ...panel('compose'), category: 'editor' };
    const knowledge: StudioPanelDef = { ...panel('kg-overview'), category: 'knowledge' };
    // Deliberately out of CATEGORY_ORDER (quality, enrichment, editor, knowledge) to prove it sorts.
    const cmds = buildStudioCommands({
      chrome: chrome(),
      panels: [quality, enrichment, editor, knowledge],
      ...baseOpts(),
    });
    const panelCmdIds = cmds.filter((c) => c.id.startsWith('studio.openPanel.')).map((c) => c.id);
    expect(panelCmdIds).toEqual([
      'studio.openPanel.compose',          // editor
      'studio.openPanel.kg-overview',      // knowledge
      'studio.openPanel.quality-promises', // quality  ← was sorting FIRST, above editor
      'studio.openPanel.enrichment-gaps',  // enrichment
    ]);
  });

  it('chrome commands carry a description (the palette sublabel)', () => {
    const cmds = buildStudioCommands({ chrome: chrome(), panels: [], ...baseOpts() });
    expect(cmds.find((x) => x.id === 'view.toggleBottom')?.description).toBe('Jobs · Generation · Issues');
  });

  it('command run() dispatches the right chrome action', () => {
    const c = chrome();
    const onOpenQuickOpen = vi.fn();
    const cmds = buildStudioCommands({ chrome: c, panels: [], ...baseOpts(), onOpenQuickOpen });
    cmds.find((x) => x.id === 'view.showQuality')!.run();
    expect(c.setActiveView).toHaveBeenCalledWith('quality');
    cmds.find((x) => x.id === 'view.toggleSidebar')!.run();
    expect(c.toggleSidebar).toHaveBeenCalledOnce();
    cmds.find((x) => x.id === 'view.goToChapter')!.run();
    expect(onOpenQuickOpen).toHaveBeenCalledOnce();
  });

  // #19 — Help group: re-run the role picker / start the guided tour on demand.
  it('includes the Help commands and dispatches their callbacks', () => {
    const onChooseYourFocus = vi.fn();
    const onStartGuidedTour = vi.fn();
    const cmds = buildStudioCommands({ chrome: chrome(), panels: [], ...baseOpts(), onChooseYourFocus, onStartGuidedTour });
    cmds.find((x) => x.id === 'studio.chooseYourFocus')!.run();
    expect(onChooseYourFocus).toHaveBeenCalledOnce();
    cmds.find((x) => x.id === 'studio.startGuidedTour')!.run();
    expect(onStartGuidedTour).toHaveBeenCalledOnce();
  });
});

describe('filterCommands', () => {
  const cmds = buildStudioCommands({ chrome: chrome(), panels: [], ...baseOpts() });
  it('empty query returns all', () => {
    expect(filterCommands(cmds, '  ')).toHaveLength(cmds.length);
  });
  it('substring-matches the label case-insensitively', () => {
    const r = filterCommands(cmds, 'bottom');
    expect(r).toHaveLength(1);
    expect(r[0].id).toBe('view.toggleBottom');
  });
});
