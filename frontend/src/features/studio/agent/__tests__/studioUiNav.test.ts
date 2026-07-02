import { describe, expect, it, vi } from 'vitest';
import { isStudioUiTool, resolveStudioUiTool, makeStudioNavInterceptor } from '../studioUiNav';
import type { StudioHost } from '../../host/StudioHostProvider';

const mockHost = () =>
  ({ bookId: 'b1', openPanel: vi.fn(), focusManuscriptUnit: vi.fn() }) as unknown as StudioHost;

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

// #12 M-E live-caught: an agent ui_open_book on the current book navigated the SPA out of
// the studio, unmounting the whole surface (and orphaning the agent's own run). Same-book
// C-NAV calls must remap to dock actions; anything genuinely elsewhere falls through (null).
describe('makeStudioNavInterceptor', () => {
  it('ui_open_chapter (same book) → focuses the manuscript unit, no SPA nav', () => {
    const host = mockHost();
    const r = makeStudioNavInterceptor(host)('ui_open_chapter', { book_id: 'b1', chapter_id: 'ch7' })!;
    expect(r.path).toBeNull();
    expect(r.result.opened).toBe(true);
    r.effect!();
    expect(host.focusManuscriptUnit).toHaveBeenCalledWith('ch7');
  });

  it('ui_open_chapter without book_id → assumes the studio book (still intercepted)', () => {
    const host = mockHost();
    const r = makeStudioNavInterceptor(host)('ui_open_chapter', { chapter_id: 'ch7' })!;
    expect(r.path).toBeNull();
    r.effect!();
    expect(host.focusManuscriptUnit).toHaveBeenCalledWith('ch7');
  });

  it('ui_open_chapter for ANOTHER book → falls through to the real navigation', () => {
    const host = mockHost();
    expect(makeStudioNavInterceptor(host)('ui_open_chapter', { book_id: 'OTHER', chapter_id: 'ch7' })).toBeNull();
  });

  it('ui_open_book on the current book → success, no nav (the live-caught case)', () => {
    const host = mockHost();
    const r = makeStudioNavInterceptor(host)('ui_open_book', { book_id: 'b1' })!;
    expect(r.path).toBeNull();
    expect(r.effect).toBeUndefined();
    expect(r.result.opened).toBe(true);
  });

  it('ui_open_book on another book → falls through', () => {
    const host = mockHost();
    expect(makeStudioNavInterceptor(host)('ui_open_book', { book_id: 'OTHER' })).toBeNull();
  });

  it('ui_navigate to this book/studio → claimed as already-here; elsewhere → falls through', () => {
    const host = mockHost();
    const intercept = makeStudioNavInterceptor(host);
    expect(intercept('ui_navigate', { path: '/books/b1' })!.result.navigated).toBe(true);
    expect(intercept('ui_navigate', { path: '/books/b1/studio' })!.path).toBeNull();
    expect(intercept('ui_navigate', { path: '/usage' })).toBeNull();
    expect(intercept('ui_navigate', { path: '/books/OTHER' })).toBeNull();
  });

  it('never claims non-nav tools (ui_show_panel, ui_watch_job, MCP tools)', () => {
    const host = mockHost();
    const intercept = makeStudioNavInterceptor(host);
    expect(intercept('ui_show_panel', { panel: 'x' })).toBeNull();
    expect(intercept('ui_watch_job', { job_id: 'j1' })).toBeNull();
    expect(intercept('composition_outline_node_update', {})).toBeNull();
  });
});
