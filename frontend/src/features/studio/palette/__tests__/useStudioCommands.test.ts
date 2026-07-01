import { describe, expect, it, vi } from 'vitest';
import { buildStudioCommands, filterCommands } from '../useStudioCommands';
import type { StudioToolRegistration } from '../../host/types';

const t = (key: string, opts?: Record<string, unknown>) => (opts?.defaultValue as string) ?? key;

const chrome = () => ({ setActiveView: vi.fn(), toggleSidebar: vi.fn(), toggleBottom: vi.fn() });

describe('buildStudioCommands', () => {
  it('always includes chrome commands (navigate + layout); panels only from the registry', () => {
    const c = chrome();
    const cmds = buildStudioCommands({ chrome: c, tools: [], onOpenPanel: vi.fn(), onOpenQuickOpen: vi.fn(), t });
    const ids = cmds.map((x) => x.id);
    expect(ids).toContain('view.showManuscript');
    expect(ids).toContain('view.toggleBottom');
    expect(ids).toContain('view.goToChapter');
    // no registered tools → no Panels commands
    expect(cmds.some((x) => x.group === 'Panels')).toBe(false);
  });

  it('adds one "Studio: Open …" per registered tool, label FROM the registration', () => {
    const tool: StudioToolRegistration = { panelId: 'cast', label: 'Cast', paletteCommand: 'Studio: Open Cast', commandId: 'studio.openPanel.cast' };
    const onOpenPanel = vi.fn();
    const cmds = buildStudioCommands({ chrome: chrome(), tools: [tool], onOpenPanel, onOpenQuickOpen: vi.fn(), t });
    const panel = cmds.find((x) => x.id === 'studio.openPanel.cast');
    expect(panel?.label).toBe('Studio: Open Cast');
    panel?.run();
    expect(onOpenPanel).toHaveBeenCalledWith('cast');
  });

  it('command run() dispatches the right chrome action', () => {
    const c = chrome();
    const onOpenQuickOpen = vi.fn();
    const cmds = buildStudioCommands({ chrome: c, tools: [], onOpenPanel: vi.fn(), onOpenQuickOpen, t });
    cmds.find((x) => x.id === 'view.showQuality')!.run();
    expect(c.setActiveView).toHaveBeenCalledWith('quality');
    cmds.find((x) => x.id === 'view.toggleSidebar')!.run();
    expect(c.toggleSidebar).toHaveBeenCalledOnce();
    cmds.find((x) => x.id === 'view.goToChapter')!.run();
    expect(onOpenQuickOpen).toHaveBeenCalledOnce();
  });
});

describe('filterCommands', () => {
  const cmds = buildStudioCommands({ chrome: chrome(), tools: [], onOpenPanel: vi.fn(), onOpenQuickOpen: vi.fn(), t });
  it('empty query returns all', () => {
    expect(filterCommands(cmds, '  ')).toHaveLength(cmds.length);
  });
  it('substring-matches the label case-insensitively', () => {
    const r = filterCommands(cmds, 'bottom');
    expect(r).toHaveLength(1);
    expect(r[0].id).toBe('view.toggleBottom');
  });
});
