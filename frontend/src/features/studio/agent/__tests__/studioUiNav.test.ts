import { describe, expect, it, vi } from 'vitest';
import { isStudioUiTool, resolveStudioUiTool } from '../studioUiNav';
import type { StudioHost } from '../../host/StudioHostProvider';

const mockHost = () => ({ openPanel: vi.fn(), focusManuscriptUnit: vi.fn() }) as unknown as StudioHost;

describe('isStudioUiTool', () => {
  it('recognizes the studio ui tools, rejects chat/unknown tools', () => {
    expect(isStudioUiTool('ui_open_studio_panel')).toBe(true);
    expect(isStudioUiTool('ui_focus_manuscript_unit')).toBe(true);
    expect(isStudioUiTool('ui_navigate')).toBe(false); // chat's own
    expect(isStudioUiTool('book_get_chapter')).toBe(false);
  });
});

describe('resolveStudioUiTool', () => {
  it('ui_open_studio_panel → opens the panel via the host', () => {
    const host = mockHost();
    const { result, effect } = resolveStudioUiTool('ui_open_studio_panel', { panel_id: 'cast' });
    expect(result).toEqual({ opened: true });
    effect!(host);
    expect(host.openPanel).toHaveBeenCalledWith('cast');
  });

  it('ui_open_studio_panel without panel_id → rejected with a corrective error, no effect', () => {
    const { result, effect } = resolveStudioUiTool('ui_open_studio_panel', {});
    expect(result.opened).toBe(false);
    expect(result.error).toMatch(/panel_id/);
    expect(effect).toBeUndefined();
  });

  // A live gemma-26b smoke sent `panel:"editor"` (the ui_show_panel/ui_open_book arg name) instead
  // of `panel_id`; the loop must still close. `page` is tolerated for the same reason.
  it('ui_open_studio_panel tolerates the `panel` / `page` aliases a weak model reaches for', () => {
    for (const args of [{ panel: 'editor' }, { page: 'editor' }] as Record<string, unknown>[]) {
      const host = mockHost();
      const { result, effect } = resolveStudioUiTool('ui_open_studio_panel', args);
      expect(result).toEqual({ opened: true });
      effect!(host);
      expect(host.openPanel).toHaveBeenCalledWith('editor');
    }
  });

  it('ui_focus_manuscript_unit → focuses the chapter via the host', () => {
    const host = mockHost();
    const { result, effect } = resolveStudioUiTool('ui_focus_manuscript_unit', { chapter_id: 'ch7' });
    expect(result).toEqual({ focused: true });
    effect!(host);
    expect(host.focusManuscriptUnit).toHaveBeenCalledWith('ch7');
  });

  it('unknown tool → empty resolution', () => {
    expect(resolveStudioUiTool('ui_navigate', { path: '/x' })).toEqual({ result: {} });
  });
});
