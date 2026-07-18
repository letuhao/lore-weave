// 24 H5 — the three WRITE surfaces. These assert the wire shape (method + path + body + headers),
// which nothing else does: the drag tests stop at the handler call, and the controller tests mock
// this module. The load-bearing one is `If-Match` — drop that header and the OCC silently degrades
// to last-write-wins, with every test still green.
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { assignChapters, getArcs, moveArc, reorderNode } from '../api';

const TOKEN = 'tok';

function mockFetchOnce(body: unknown, init: { status?: number } = {}) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status: init.status ?? 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

/** The (url, init) the code actually put on the wire. */
function callOf(fetchMock: ReturnType<typeof vi.fn>) {
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  const headers = new Headers(init?.headers);
  return { url, init, headers, body: init?.body ? JSON.parse(String(init.body)) : undefined };
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());

describe('reorderNode (Row-4) — the OCC write', () => {
  it('POSTs the reorder with the version as If-Match', async () => {
    const fetchMock = mockFetchOnce({ id: 's1', parent_id: 'ch-2', version: 5 });
    await reorderNode('s1', { new_parent_id: 'ch-2', after_id: 's-b' }, 4, TOKEN);

    const { url, init, headers, body } = callOf(fetchMock);
    expect(url).toContain('/v1/composition/outline/nodes/s1/reorder');
    expect(init.method).toBe('POST');
    expect(headers.get('If-Match')).toBe('4'); // the OCC guard — a 412 depends on it
    expect(body).toEqual({ new_parent_id: 'ch-2', after_id: 's-b' });
  });

  it('a 412 rejects with a detectable status (so the caller can say "changed elsewhere")', async () => {
    mockFetchOnce({ code: 'NODE_VERSION_CONFLICT' }, { status: 412 });
    await expect(reorderNode('s1', { new_parent_id: 'ch-2', after_id: null }, 1, TOKEN)).rejects.toMatchObject({
      status: 412,
    });
  });
});

describe('moveArc (Row-2)', () => {
  it('POSTs the structural move — and carries NO If-Match (a move has no row version)', async () => {
    const fetchMock = mockFetchOnce({ id: 'a1', parent_id: 'saga', depth: 1 });
    await moveArc('a1', { new_parent_arc_id: 'saga', after_id: 'a2' }, TOKEN);

    const { url, init, headers, body } = callOf(fetchMock);
    expect(url).toContain('/v1/composition/arcs/a1/move');
    expect(init.method).toBe('POST');
    expect(headers.get('If-Match')).toBeNull();
    expect(body).toEqual({ new_parent_arc_id: 'saga', after_id: 'a2' });
  });
});

describe('assignChapters (Row-1)', () => {
  it('POSTs the bulk set with the arc + the chapter ids', async () => {
    const fetchMock = mockFetchOnce({ assigned: 1, structure_node_id: 'arc-b' });
    await assignChapters('book-1', 'arc-b', ['ch-9'], TOKEN);

    const { url, init, body } = callOf(fetchMock);
    expect(url).toContain('/v1/composition/books/book-1/arcs/assign-chapters');
    expect(init.method).toBe('POST');
    expect(body).toEqual({ structure_node_id: 'arc-b', chapter_node_ids: ['ch-9'] });
  });
});

describe('getArcs (read surface #1)', () => {
  it('normalises the route\'s `{nodes}` envelope to `{arcs}` (a live smoke caught this drift)', async () => {
    mockFetchOnce({ nodes: [{ id: 'a1', chapter_count: 3 }], book_id: 'book-1' });
    const res = await getArcs('book-1', TOKEN);
    expect(res.arcs).toHaveLength(1);
    expect(res.arcs[0].id).toBe('a1');
  });

  it('accepts an `{arcs}` envelope too, and an empty response is [] (never undefined)', async () => {
    mockFetchOnce({ arcs: [{ id: 'a2' }] });
    expect((await getArcs('book-1', TOKEN)).arcs[0].id).toBe('a2');

    mockFetchOnce({});
    expect((await getArcs('book-1', TOKEN)).arcs).toEqual([]);
  });
});
