import { afterEach, describe, expect, it, vi } from 'vitest';
import { followStudioLink, resolveStudioLink } from '../studioLinks';
import type { StudioHost } from '../StudioHostProvider';

const ctx = { bookId: 'b1', titleFor: (id: string) => `T:${id}` };

function fakeHost() {
  return {
    openPanel: vi.fn(),
    focusManuscriptUnit: vi.fn(),
  } as unknown as StudioHost;
}

function runStudio(link: string, host: StudioHost, c = ctx) {
  const r = resolveStudioLink(link, c);
  expect(r.kind).toBe('studio');
  if (r.kind === 'studio') r.effect(host);
}

describe('resolveStudioLink', () => {
  it('same-book chapter link → focusManuscriptUnit', () => {
    const host = fakeHost();
    runStudio('/books/b1/chapters/c7/edit', host);
    expect(host.focusManuscriptUnit).toHaveBeenCalledWith('c7');
  });

  it('other-book chapter link → external (studio is per-book)', () => {
    expect(resolveStudioLink('/books/OTHER/chapters/c7/edit', ctx)).toEqual({
      kind: 'external', url: '/books/OTHER/chapters/c7/edit',
    });
  });

  it('user-scoped panel paths → openPanel with the catalog title', () => {
    for (const [path, panelId] of [['/usage', 'usage'], ['/notifications', 'notifications'], ['/trash', 'trash']] as const) {
      const host = fakeHost();
      runStudio(path, host);
      expect(host.openPanel).toHaveBeenCalledWith(panelId, { title: `T:${panelId}`, params: undefined });
    }
  });

  it('settings tab deep-link → openPanel params (F1 seam)', () => {
    const host = fakeHost();
    runStudio('/settings/providers', host);
    expect(host.openPanel).toHaveBeenCalledWith('settings', { title: 'T:settings', params: { tab: 'providers' } });
  });

  it('bare /settings → openPanel without params', () => {
    const host = fakeHost();
    runStudio('/settings', host);
    expect(host.openPanel).toHaveBeenCalledWith('settings', { title: 'T:settings', params: undefined });
  });

  it('query/hash do not break matching', () => {
    const host = fakeHost();
    runStudio('/books/b1/chapters/c9/translations?version=3#top', host);
    expect(host.focusManuscriptUnit).toHaveBeenCalledWith('c9');
  });

  it('http(s) and unmapped app paths → external with the ORIGINAL link', () => {
    expect(resolveStudioLink('https://example.com/x', ctx)).toEqual({ kind: 'external', url: 'https://example.com/x' });
    expect(resolveStudioLink('/profile?u=1', ctx)).toEqual({ kind: 'external', url: '/profile?u=1' });
  });

  it('unsafe schemes / non-path strings → blocked (LOW-4 rule)', () => {
    // eslint-disable-next-line no-script-url
    expect(resolveStudioLink('javascript:alert(1)', ctx).kind).toBe('blocked');
    expect(resolveStudioLink('data:text/html,x', ctx).kind).toBe('blocked');
    expect(resolveStudioLink('books/b1', ctx).kind).toBe('blocked');
  });

  it('protocol-relative "//" is blocked — window.open would hit an EXTERNAL origin', () => {
    expect(resolveStudioLink('//evil.example/x', ctx).kind).toBe('blocked');
    expect(resolveStudioLink('//usage', ctx).kind).toBe('blocked');
  });

  it('14_kg_panels.md — the global KG panel paths → openPanel with the right kg-* id', () => {
    for (const [path, panelId] of [
      ['/knowledge', 'knowledge'],
      ['/knowledge/projects', 'knowledge'],
      ['/knowledge/jobs', 'kg-jobs'],
      ['/knowledge/global', 'kg-bio'],
      ['/knowledge/entities', 'kg-entities'],
      ['/knowledge/timeline', 'kg-timeline'],
      ['/knowledge/raw', 'kg-evidence'],
      ['/knowledge/insights', 'kg-insights'],
      ['/knowledge/privacy', 'kg-privacy'],
    ] as const) {
      const host = fakeHost();
      runStudio(path, host);
      expect(host.openPanel).toHaveBeenCalledWith(panelId, { title: `T:${panelId}`, params: undefined });
    }
  });

  it('14_kg_panels.md — a project-id-keyed /knowledge/projects/:id/:section path is NOT mapped (ambiguous project identity) — external', () => {
    expect(resolveStudioLink('/knowledge/projects/proj-9/overview', ctx)).toEqual({
      kind: 'external', url: '/knowledge/projects/proj-9/overview',
    });
  });

  it('same-book glossary page → openPanel(glossary)', () => {
    const host = fakeHost();
    runStudio('/books/b1/glossary', host);
    expect(host.openPanel).toHaveBeenCalledWith('glossary', { title: 'T:glossary', params: undefined });
  });

  it('other-book glossary page → external (studio is per-book)', () => {
    expect(resolveStudioLink('/books/OTHER/glossary', ctx)).toEqual({
      kind: 'external', url: '/books/OTHER/glossary',
    });
  });

  it('same-book wiki/enrichment pages → external (no dock panel exists yet for those)', () => {
    expect(resolveStudioLink('/books/b1/wiki', ctx)).toEqual({ kind: 'external', url: '/books/b1/wiki' });
    expect(resolveStudioLink('/books/b1/enrichment', ctx)).toEqual({ kind: 'external', url: '/books/b1/enrichment' });
  });

  it('works without titleFor (panels self-title on mount)', () => {
    const host = fakeHost();
    const r = resolveStudioLink('/usage', { bookId: 'b1' });
    expect(r.kind).toBe('studio');
    if (r.kind === 'studio') r.effect(host);
    expect(host.openPanel).toHaveBeenCalledWith('usage', { title: undefined, params: undefined });
  });
});

describe('followStudioLink', () => {
  afterEach(() => vi.restoreAllMocks());

  it('external → window.open in a new tab with noopener', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    const host = fakeHost();
    expect(followStudioLink('https://example.com', host, ctx)).toBe('external');
    expect(open).toHaveBeenCalledWith('https://example.com', '_blank', 'noopener,noreferrer');
    expect(host.openPanel).not.toHaveBeenCalled();
  });

  it('studio → runs the effect, never window.open', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    const host = fakeHost();
    expect(followStudioLink('/usage', host, ctx)).toBe('studio');
    expect(host.openPanel).toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
  });

  it('blocked → nothing happens', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    const host = fakeHost();
    expect(followStudioLink('mailto:x@y.z', host, ctx)).toBe('blocked');
    expect(open).not.toHaveBeenCalled();
    expect(host.openPanel).not.toHaveBeenCalled();
  });
});
