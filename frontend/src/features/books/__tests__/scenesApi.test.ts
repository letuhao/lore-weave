import { describe, it, expect, vi, beforeEach } from 'vitest';

// 22-C1 — pin the book-wide scene list call: URL shape + the server-side filter args
// (chapter_id, source_scene_id, q) that the scene-browser relies on. Mock the shared
// apiJson so this is a pure URL-contract test (no network).
const apiJson = vi.fn(async () => ({ items: [], next_cursor: null, total: 0 }));
vi.mock('@/api', () => ({
  apiJson: (...args: unknown[]) => apiJson(...args),
  apiBase: () => 'http://gw',
}));

import { booksApi, type Scene } from '../api';

describe('booksApi.listScenes (22-C1)', () => {
  beforeEach(() => apiJson.mockClear());

  it('hits the book-wide scenes route with no query when no opts', async () => {
    await booksApi.listScenes('tok', 'book-1');
    expect(apiJson).toHaveBeenCalledWith('/v1/books/book-1/scenes', { token: 'tok' });
  });

  it('forwards chapter_id, source_scene_id, q and cursor/limit as query params', async () => {
    await booksApi.listScenes('tok', 'book-1', {
      chapter_id: 'ch-9', source_scene_id: 'node-7', q: 'dragon', cursor: 'c1', limit: 100,
    });
    const [path] = apiJson.mock.calls[0] as [string, unknown];
    const url = new URL(path, 'http://gw');
    expect(url.pathname).toBe('/v1/books/book-1/scenes');
    expect(url.searchParams.get('chapter_id')).toBe('ch-9');
    expect(url.searchParams.get('source_scene_id')).toBe('node-7');
    expect(url.searchParams.get('q')).toBe('dragon');
    expect(url.searchParams.get('cursor')).toBe('c1');
    expect(url.searchParams.get('limit')).toBe('100');
  });

  it('omits falsy filters (empty q / no cursor) from the query', async () => {
    await booksApi.listScenes('tok', 'book-1', { q: '', chapter_id: 'ch-1' });
    const [path] = apiJson.mock.calls[0] as [string, unknown];
    expect(path).toBe('/v1/books/book-1/scenes?chapter_id=ch-1');
  });

  it('Scene type carries the identity/join fields (compile-time contract)', () => {
    // A NULL source_scene_id is the "written, not decompiled" union-row shape (BPS-13).
    const s: Scene = {
      scene_id: 's1', book_id: 'b1', chapter_id: 'c1', sort_order: 0, title: null,
      path: '/0', leaf_text: 'x', content_hash: 'h', source_scene_id: null,
      parse_version: 1, lifecycle_state: 'active',
    };
    expect(s.source_scene_id).toBeNull();
  });
});
