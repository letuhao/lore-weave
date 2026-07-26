import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  _clearJsonDocuments, _liveHandleCount, openJsonDocument, registerJsonDocumentProvider,
} from '../registry';
import { createFetchDocumentHandle } from '../fetchHandle';
import type { DocContext } from '../types';

const ctx: DocContext = { token: 'tok', bookId: 'b1' };

function fakeProvider(type = 'loreweave.test.v1') {
  const release = vi.fn();
  const open = vi.fn((_ctx: DocContext, rid: string) => ({
    type, resourceId: rid,
    getSnapshot: () => ({ doc: { rid }, etag: 1, dirty: false, status: 'idle' as const, detail: null }),
    subscribe: () => () => {},
    update: vi.fn(), save: vi.fn(async () => {}), revert: vi.fn(),
    reload: vi.fn(async () => {}), release,
  }));
  registerJsonDocumentProvider({ type, open });
  return { open, release };
}

beforeEach(() => _clearJsonDocuments());

describe('json document registry (S1/S2)', () => {
  it('unknown type rejects', async () => {
    await expect(openJsonDocument('nope.v1', 'r1', ctx)).rejects.toThrow(/no JSON document provider/);
  });

  it('two opens of the same resource SHARE one underlying handle; dispose at last release', async () => {
    const { open, release } = fakeProvider();
    const h1 = await openJsonDocument('loreweave.test.v1', 'r1', ctx);
    const h2 = await openJsonDocument('loreweave.test.v1', 'r1', ctx);
    expect(open).toHaveBeenCalledTimes(1);
    expect(_liveHandleCount()).toBe(1);

    h1.release();
    expect(release).not.toHaveBeenCalled(); // h2 still holds a ref
    h1.release(); // double-release must NOT steal h2's ref
    expect(release).not.toHaveBeenCalled();
    h2.release();
    expect(release).toHaveBeenCalledTimes(1);
    expect(_liveHandleCount()).toBe(0);
  });

  it('different resources get different handles', async () => {
    const { open } = fakeProvider();
    await openJsonDocument('loreweave.test.v1', 'r1', ctx);
    await openJsonDocument('loreweave.test.v1', 'r2', ctx);
    expect(open).toHaveBeenCalledTimes(2);
    expect(_liveHandleCount()).toBe(2);
  });
});

describe('createFetchDocumentHandle (stock handle)', () => {
  it('load → idle; update marks dirty; save persists and clears dirty with the new etag', async () => {
    const save = vi.fn(async () => ({ etag: 2 }));
    const h = createFetchDocumentHandle('t.v1', 'r1', {
      load: async () => ({ doc: { a: 1 }, etag: 1 }),
      save,
    });
    await vi.waitFor(() => expect(h.getSnapshot().status).toBe('idle'));
    expect(h.getSnapshot()).toMatchObject({ doc: { a: 1 }, etag: 1, dirty: false });

    h.update({ a: 2 });
    expect(h.getSnapshot().dirty).toBe(true);

    await h.save();
    expect(save).toHaveBeenCalledWith({ a: 2 }, 1);
    expect(h.getSnapshot()).toMatchObject({ doc: { a: 2 }, etag: 2, dirty: false, status: 'idle' });
  });

  it('save conflict surfaces status=conflict, keeps the working copy', async () => {
    const h = createFetchDocumentHandle('t.v1', 'r1', {
      load: async () => ({ doc: { a: 1 }, etag: 1 }),
      save: async () => { throw Object.assign(new Error('body'), { conflict: true }); },
    });
    await vi.waitFor(() => expect(h.getSnapshot().status).toBe('idle'));
    h.update({ a: 9 });
    await h.save();
    expect(h.getSnapshot()).toMatchObject({ status: 'conflict', detail: 'body', dirty: true, doc: { a: 9 } });
  });

  it('reload never clobbers a dirty working copy (G7/R6)', async () => {
    let serverDoc = { a: 1 };
    const h = createFetchDocumentHandle('t.v1', 'r1', {
      load: async () => ({ doc: serverDoc, etag: 1 }),
      save: async () => ({ etag: 2 }),
    });
    await vi.waitFor(() => expect(h.getSnapshot().status).toBe('idle'));
    h.update({ a: 'edited' });
    serverDoc = { a: 'server' };
    await h.reload();
    expect(h.getSnapshot().doc).toEqual({ a: 'edited' }); // working copy survives
    h.revert();
    expect(h.getSnapshot().doc).toEqual({ a: 'server' }); // revert lands on the reloaded base
  });

  it('revert drops edits and clears error state', async () => {
    const h = createFetchDocumentHandle('t.v1', 'r1', {
      load: async () => ({ doc: { a: 1 }, etag: 1 }),
      save: async () => { throw new Error('boom'); },
    });
    await vi.waitFor(() => expect(h.getSnapshot().status).toBe('idle'));
    h.update({ a: 2 });
    await h.save();
    expect(h.getSnapshot().status).toBe('error');
    h.revert();
    expect(h.getSnapshot()).toMatchObject({ doc: { a: 1 }, dirty: false, status: 'idle' });
  });
});
