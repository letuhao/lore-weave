import { describe, it, expect, vi, afterEach } from 'vitest';
import { resolveUiTool, isUiTool, uiDirectiveFromResult } from '../uiNav';

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

  it('ui_navigate rejects a disallowed path (navigated:false + corrective error, no path)', () => {
    const r = resolveUiTool('ui_navigate', { path: '/evil/route' });
    expect(r.path).toBeNull();
    expect(r.result.navigated).toBe(false);
    expect(r.result.error).toBeTruthy(); // no-silent-no-op: the model is told why
    // also rejects a non-absolute path
    expect(resolveUiTool('ui_navigate', { path: 'books' }).result.navigated).toBe(false);
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
      expect(r.path).toBeNull();
      expect(r.result.navigated).toBe(false);
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

  it('ui_open_book missing id → opened:false + error', () => {
    const r = resolveUiTool('ui_open_book', {});
    expect(r.path).toBeNull();
    expect(r.result).toMatchObject({ opened: false });
    expect(r.result.error).toBeTruthy();
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

  it('ui_show_panel with no panel → shown:false + error', () => {
    const r = resolveUiTool('ui_show_panel', {});
    expect(r.path).toBeNull();
    expect(r.result).toMatchObject({ shown: false });
    expect(r.result.error).toBeTruthy();
  });
});

describe('uiDirectiveFromResult', () => {
  const dir = { type: 'io.loreweave/ui-directive', tool: 'ui_navigate', args: { path: '/settings' } };

  it('unwraps the REAL chat-service {ok, result: <directive>} envelope (the live-loop shape)', () => {
    // This is the exact TOOL_CALL_RESULT content shape the browser E2E revealed; a
    // detector that only checked the top level silently no-op'd in the live app.
    expect(uiDirectiveFromResult({ ok: true, result: dir })).toEqual(dir);
  });

  it('accepts a bare directive and a structuredContent wrapper too', () => {
    expect(uiDirectiveFromResult(dir)).toEqual(dir);
    expect(uiDirectiveFromResult({ structuredContent: dir })).toEqual(dir);
  });

  it('returns null for a non-directive result / junk', () => {
    expect(uiDirectiveFromResult({ ok: true, result: { books: [] } })).toBeNull();
    expect(uiDirectiveFromResult({ navigated: true })).toBeNull();
    expect(uiDirectiveFromResult(null)).toBeNull();
    expect(uiDirectiveFromResult('nope')).toBeNull();
  });
});
