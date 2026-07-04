import { describe, expect, it, vi } from 'vitest';
import { buildStudioCommands, filterCommands } from '../useStudioCommands';
import { OPENABLE_STUDIO_PANELS, type StudioPanelDef } from '../../panels/catalog';

const t = (key: string, opts?: Record<string, unknown>) => (opts?.defaultValue as string) ?? key;

const chrome = () => ({ setActiveView: vi.fn(), toggleSidebar: vi.fn(), toggleBottom: vi.fn() });
const panel = (id: string): StudioPanelDef =>
  ({ id, component: (() => null) as unknown as StudioPanelDef['component'], titleKey: `panels.${id}.title`, descKey: `panels.${id}.desc` });

describe('buildStudioCommands', () => {
  it('always includes chrome commands (navigate + layout); no Panels without a catalog', () => {
    const c = chrome();
    const cmds = buildStudioCommands({ chrome: c, panels: [], onOpenPanel: vi.fn(), onOpenQuickOpen: vi.fn(), t });
    const ids = cmds.map((x) => x.id);
    expect(ids).toContain('view.showManuscript');
    expect(ids).toContain('view.toggleBottom');
    expect(ids).toContain('view.goToChapter');
    expect(cmds.some((x) => x.group === 'Panels')).toBe(false);
  });

  it('adds one "Studio: Open …" per CATALOG panel; run() opens by panel id', () => {
    const onOpenPanel = vi.fn();
    const cmds = buildStudioCommands({ chrome: chrome(), panels: [panel('cast')], onOpenPanel, onOpenQuickOpen: vi.fn(), t });
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
      onOpenPanel,
      onOpenQuickOpen: vi.fn(),
      t,
    });
    const p = cmds.find((x) => x.id === 'studio.openPanel.context-inspector');
    expect(p).toBeDefined();
    expect(p!.group).toBe('Panels');
    p!.run();
    expect(onOpenPanel).toHaveBeenCalledWith('context-inspector');
  });

  it('chrome commands carry a description (the palette sublabel)', () => {
    const cmds = buildStudioCommands({ chrome: chrome(), panels: [], onOpenPanel: vi.fn(), onOpenQuickOpen: vi.fn(), t });
    expect(cmds.find((x) => x.id === 'view.toggleBottom')?.description).toBe('Jobs · Generation · Issues');
  });

  it('command run() dispatches the right chrome action', () => {
    const c = chrome();
    const onOpenQuickOpen = vi.fn();
    const cmds = buildStudioCommands({ chrome: c, panels: [], onOpenPanel: vi.fn(), onOpenQuickOpen, t });
    cmds.find((x) => x.id === 'view.showQuality')!.run();
    expect(c.setActiveView).toHaveBeenCalledWith('quality');
    cmds.find((x) => x.id === 'view.toggleSidebar')!.run();
    expect(c.toggleSidebar).toHaveBeenCalledOnce();
    cmds.find((x) => x.id === 'view.goToChapter')!.run();
    expect(onOpenQuickOpen).toHaveBeenCalledOnce();
  });
});

describe('filterCommands', () => {
  const cmds = buildStudioCommands({ chrome: chrome(), panels: [], onOpenPanel: vi.fn(), onOpenQuickOpen: vi.fn(), t });
  it('empty query returns all', () => {
    expect(filterCommands(cmds, '  ')).toHaveLength(cmds.length);
  });
  it('substring-matches the label case-insensitively', () => {
    const r = filterCommands(cmds, 'bottom');
    expect(r).toHaveLength(1);
    expect(r[0].id).toBe('view.toggleBottom');
  });
});
