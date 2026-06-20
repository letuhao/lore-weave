import { describe, it, expect, vi, afterEach } from 'vitest';
import { resolveUiTool, isUiTool } from '../uiNav';

// MCP fan-out (C-NAV) — the pure nav resolver: tool name + args → {path, result}.
// The `result` flag always reflects whether navigation was actually performed so
// the agent can never falsely believe the UI moved.

describe('resolveUiTool', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('isUiTool recognises the ui_* set and rejects others', () => {
    expect(isUiTool('ui_navigate')).toBe(true);
    expect(isUiTool('ui_watch_job')).toBe(true);
    expect(isUiTool('propose_edit')).toBe(false);
  });

  it('ui_navigate honours an allowlisted path', () => {
    expect(resolveUiTool('ui_navigate', { path: '/books/b1/glossary' })).toEqual({
      path: '/books/b1/glossary',
      result: { navigated: true },
    });
  });

  it('ui_navigate rejects a disallowed path (navigated:false, no path)', () => {
    expect(resolveUiTool('ui_navigate', { path: '/evil/route' })).toEqual({
      path: null,
      result: { navigated: false },
    });
    // also rejects a non-absolute path
    expect(resolveUiTool('ui_navigate', { path: 'books' }).result).toEqual({ navigated: false });
  });

  it('ui_navigate rejects open-redirect / scheme-injection attempts', () => {
    // Protocol-relative URL ("//host") — would navigate off-origin. The
    // allowlist only matches absolute in-app paths under a known prefix.
    for (const evil of [
      '//evil.com',
      '//evil.com/books',
      'https://evil.com',
      'http://evil.com/books',
      'javascript:alert(1)',
      'mailto:x@evil.com',
      '\\\\evil.com',
    ]) {
      const r = resolveUiTool('ui_navigate', { path: evil });
      expect(r).toEqual({ path: null, result: { navigated: false } });
    }
  });

  it('ui_open_book / ui_open_chapter encode a malicious id so it cannot escape its segment', () => {
    // A path-traversal id stays percent-encoded inside its route segment — it can
    // never resolve to "/settings" etc.
    const evilId = '../../settings';
    const enc = encodeURIComponent(evilId); // "..%2F..%2Fsettings"
    const book = resolveUiTool('ui_open_book', { book_id: evilId, tab: 'glossary' });
    expect(book.path).toBe(`/books/${enc}/glossary`);
    expect(book.path).not.toContain('../');

    const chapter = resolveUiTool('ui_open_chapter', { book_id: evilId, chapter_id: evilId, mode: 'read' });
    expect(chapter.path).toBe(`/books/${enc}/chapters/${enc}/read`);
    expect(chapter.path).not.toContain('../');
  });

  it('ui_open_book builds the tab route, overview = bare path', () => {
    expect(resolveUiTool('ui_open_book', { book_id: 'b1', tab: 'translation' })).toEqual({
      path: '/books/b1/translation',
      result: { opened: true },
    });
    expect(resolveUiTool('ui_open_book', { book_id: 'b1' }).path).toBe('/books/b1');
    expect(resolveUiTool('ui_open_book', { book_id: 'b1', tab: 'overview' }).path).toBe('/books/b1');
  });

  it('ui_open_book missing id → opened:false', () => {
    expect(resolveUiTool('ui_open_book', {})).toEqual({ path: null, result: { opened: false } });
  });

  it('ui_open_chapter builds edit/read routes', () => {
    expect(resolveUiTool('ui_open_chapter', { book_id: 'b1', chapter_id: 'c1', mode: 'read' })).toEqual({
      path: '/books/b1/chapters/c1/read',
      result: { opened: true },
    });
    // default mode = edit
    expect(resolveUiTool('ui_open_chapter', { book_id: 'b1', chapter_id: 'c1' }).path).toBe(
      '/books/b1/chapters/c1/edit',
    );
  });

  it('ui_watch_job focuses the jobs page', () => {
    expect(resolveUiTool('ui_watch_job', { job_id: 'j1' })).toEqual({
      path: '/jobs?focus=j1',
      result: { watching: true },
    });
  });

  it('ui_show_panel resolves a query param relative to the current path', () => {
    vi.stubGlobal('window', { location: { pathname: '/books/b1' } });
    const r = resolveUiTool('ui_show_panel', { panel: 'enrichment', args: { entity: 'e9' } });
    expect(r.result).toEqual({ shown: true });
    expect(r.path).toContain('/books/b1?');
    expect(r.path).toContain('panel=enrichment');
    expect(r.path).toContain('entity=e9');
  });

  it('ui_show_panel with no panel → shown:false', () => {
    expect(resolveUiTool('ui_show_panel', {})).toEqual({ path: null, result: { shown: false } });
  });
});
