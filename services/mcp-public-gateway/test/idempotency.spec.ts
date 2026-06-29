import {
  Idempotency,
  PENDING_MARKER,
  type IdempotencyStore,
} from '../src/idempotency/idempotency-store.js';
import {
  advertiseIdempotencyKeyInList,
  batchIdempotentItems,
  idempotencyInProgressError,
  idempotencyInProgressErrorForId,
  idempotencyRedisKey,
  idempotentWriteCallInfo,
  stripIdempotencyKey,
  stripIdempotencyKeyFromBatch,
} from '../src/idempotency/idempotency.js';

// A fake store mirroring SET-NX semantics we can drive deterministically.
class FakeStore implements IdempotencyStore {
  m = new Map<string, string>();
  async claimOrLoad(key: string, pendingValue: string): Promise<{ won: true } | { won: false; value: string }> {
    if (!this.m.has(key)) {
      this.m.set(key, pendingValue);
      return { won: true };
    }
    return { won: false, value: this.m.get(key)! };
  }
  async store(key: string, value: string): Promise<void> {
    this.m.set(key, value);
  }
  async remove(key: string): Promise<void> {
    this.m.delete(key);
  }
}

class ErrorStore implements IdempotencyStore {
  async claimOrLoad(): Promise<never> {
    throw new Error('redis down');
  }
  async store(): Promise<void> {
    throw new Error('redis down');
  }
  async remove(): Promise<void> {
    throw new Error('redis down');
  }
}

const call = (name: string, args: Record<string, unknown> = {}, id: unknown = 1) => ({
  jsonrpc: '2.0',
  method: 'tools/call',
  params: { name, arguments: args },
  id,
});

describe('idempotentWriteCallInfo', () => {
  it('matches a single write_auto tools/call carrying a usable idempotency_key', () => {
    const info = idempotentWriteCallInfo(call('book_create', { title: 'X', idempotency_key: 'abc' }));
    expect(info).toEqual({ toolName: 'book_create', idemKey: 'abc' });
  });

  it('returns info with idemKey=null when the key is present but unusable (still must be stripped)', () => {
    expect(idempotentWriteCallInfo(call('book_create', { idempotency_key: '' }))).toEqual({
      toolName: 'book_create',
      idemKey: null,
    });
    expect(idempotentWriteCallInfo(call('book_create', { idempotency_key: 123 }))).toEqual({
      toolName: 'book_create',
      idemKey: null,
    });
    const long = 'x'.repeat(201);
    expect(idempotentWriteCallInfo(call('book_create', { idempotency_key: long }))).toEqual({
      toolName: 'book_create',
      idemKey: null,
    });
  });

  it('returns null when there is no idempotency_key at all', () => {
    expect(idempotentWriteCallInfo(call('book_create', { title: 'X' }))).toBeNull();
  });

  it('returns null for non-write_auto tiers, reads, and the wrong shapes', () => {
    expect(idempotentWriteCallInfo(call('book_get', { idempotency_key: 'k' }))).toBeNull(); // read
    expect(idempotentWriteCallInfo(call('translation_start_job', { idempotency_key: 'k' }))).toBeNull(); // write_confirm
    expect(idempotentWriteCallInfo(call('not_a_tool', { idempotency_key: 'k' }))).toBeNull(); // unknown
    expect(idempotentWriteCallInfo([call('book_create', { idempotency_key: 'k' })])).toBeNull(); // batch
    expect(idempotentWriteCallInfo({ method: 'tools/list' })).toBeNull();
    expect(idempotentWriteCallInfo(null)).toBeNull();
  });
});

describe('stripIdempotencyKey', () => {
  it('removes idempotency_key but preserves the other arguments and the envelope', () => {
    const stripped = stripIdempotencyKey(call('book_create', { title: 'X', idempotency_key: 'abc' }, 7)) as {
      method: string;
      id: number;
      params: { name: string; arguments: Record<string, unknown> };
    };
    expect(stripped.params.arguments).toEqual({ title: 'X' });
    expect('idempotency_key' in stripped.params.arguments).toBe(false);
    expect(stripped.method).toBe('tools/call');
    expect(stripped.id).toBe(7);
    expect(stripped.params.name).toBe('book_create');
  });

  it('does not mutate the original body', () => {
    const body = call('book_create', { title: 'X', idempotency_key: 'abc' });
    stripIdempotencyKey(body);
    expect((body.params.arguments as Record<string, unknown>).idempotency_key).toBe('abc');
  });

  it('is a no-op when there is no idempotency_key or the body is not a single call', () => {
    const noKey = call('book_create', { title: 'X' });
    expect(stripIdempotencyKey(noKey)).toBe(noKey);
    const batch = [call('book_create', { idempotency_key: 'k' })];
    expect(stripIdempotencyKey(batch)).toBe(batch);
  });
});

describe('idempotencyRedisKey + idempotencyInProgressError', () => {
  it('scopes the redis key per credential + tool + key', () => {
    expect(idempotencyRedisKey('key-1', 'book_create', 'abc')).toBe('mcp:idem:key-1:book_create:abc');
  });

  it('builds an in-progress JSON-RPC error preserving the request id', () => {
    const err = idempotencyInProgressError(call('book_create', {}, 42)) as {
      error: { code: number; message: string };
      id: unknown;
    };
    expect(err.error.code).toBe(-32030);
    expect(err.error.message).toMatch(/in progress/i);
    expect(err.id).toBe(42);
  });

  it('idempotencyInProgressErrorForId carries the explicit id (the batch per-item form)', () => {
    const err = idempotencyInProgressErrorForId('item-9') as { error: { code: number }; id: unknown };
    expect(err.error.code).toBe(-32030);
    expect(err.id).toBe('item-9');
    expect((idempotencyInProgressErrorForId(undefined) as { id: unknown }).id).toBeNull();
  });
});

describe('batchIdempotentItems (D-PMCP-BATCH-IDEMPOTENCY)', () => {
  it('returns one descriptor per write_auto element carrying an idempotency_key (id + tool + key)', () => {
    const body = [
      call('book_create', { title: 'A', idempotency_key: 'k-a' }, 1),
      call('book_get', { id: 'x' }, 2), // read — ignored
      call('composition_create_work', { title: 'W', idempotency_key: 'k-w' }, 3),
      call('book_create', { title: 'NoKey' }, 4), // no key — ignored
    ];
    expect(batchIdempotentItems(body)).toEqual([
      { id: 1, toolName: 'book_create', idemKey: 'k-a' },
      { id: 3, toolName: 'composition_create_work', idemKey: 'k-w' },
    ]);
  });

  it('keeps an element with an UNUSABLE key (idemKey=null) — it must still be stripped, not deduped', () => {
    const body = [call('book_create', { idempotency_key: '' }, 7)];
    expect(batchIdempotentItems(body)).toEqual([{ id: 7, toolName: 'book_create', idemKey: null }]);
  });

  it('returns [] for a non-array body, a write_confirm/read batch, or a batch with no keys', () => {
    expect(batchIdempotentItems(call('book_create', { idempotency_key: 'k' }))).toEqual([]); // single
    expect(batchIdempotentItems([call('translation_start_job', { idempotency_key: 'k' }, 1)])).toEqual([]); // write_confirm
    expect(batchIdempotentItems([call('book_get', { idempotency_key: 'k' }, 1)])).toEqual([]); // read
    expect(batchIdempotentItems([call('book_create', { title: 'x' }, 1)])).toEqual([]); // no key
    expect(batchIdempotentItems(null)).toEqual([]);
  });
});

describe('stripIdempotencyKeyFromBatch', () => {
  it('removes idempotency_key from every element that has one, preserving the rest', () => {
    const body = [
      call('book_create', { title: 'A', idempotency_key: 'k-a' }, 1),
      call('book_get', { id: 'x' }, 2),
    ];
    const out = stripIdempotencyKeyFromBatch(body) as Array<{ params: { arguments: Record<string, unknown> } }>;
    expect('idempotency_key' in out[0].params.arguments).toBe(false);
    expect(out[0].params.arguments.title).toBe('A');
    expect(out[1].params.arguments).toEqual({ id: 'x' }); // untouched element
  });

  it('does not mutate the original batch and is a no-op for a non-array body', () => {
    const body = [call('book_create', { idempotency_key: 'k' }, 1)];
    stripIdempotencyKeyFromBatch(body);
    expect((body[0].params.arguments as Record<string, unknown>).idempotency_key).toBe('k');
    const single = call('book_create', { idempotency_key: 'k' });
    expect(stripIdempotencyKeyFromBatch(single)).toBe(single);
  });
});

describe('advertiseIdempotencyKeyInList', () => {
  const list = (tools: Array<{ name: string; inputSchema?: unknown }>) =>
    JSON.stringify({ jsonrpc: '2.0', result: { tools }, id: 1 });

  it('adds an optional idempotency_key property to write_auto tools only', () => {
    const text = list([
      { name: 'book_create', inputSchema: { type: 'object', properties: { title: { type: 'string' } } } },
      { name: 'book_get', inputSchema: { type: 'object', properties: { id: { type: 'string' } } } },
    ]);
    const out = JSON.parse(advertiseIdempotencyKeyInList(text));
    const byName = Object.fromEntries(out.result.tools.map((t: { name: string }) => [t.name, t]));
    expect(byName.book_create.inputSchema.properties.idempotency_key.type).toBe('string');
    expect(byName.book_get.inputSchema.properties.idempotency_key).toBeUndefined(); // read tool untouched
  });

  it('is idempotent (does not overwrite an already-present idempotency_key) and fail-safe on bad JSON', () => {
    const withKey = list([
      {
        name: 'book_create',
        inputSchema: { type: 'object', properties: { idempotency_key: { type: 'string', description: 'mine' } } },
      },
    ]);
    const out = JSON.parse(advertiseIdempotencyKeyInList(withKey));
    expect(out.result.tools[0].inputSchema.properties.idempotency_key.description).toBe('mine');
    expect(advertiseIdempotencyKeyInList('not json')).toBe('not json');
  });
});

describe('Idempotency service', () => {
  const KEY = 'mcp:idem:k1:book_create:abc';

  it('claims on first call, reports pending while in-flight, replays after complete, releases on abort', async () => {
    const idem = new Idempotency(new FakeStore());
    expect(await idem.begin(KEY)).toEqual({ kind: 'proceed' });
    // a concurrent identical request, claim still pending
    expect(await idem.begin(KEY)).toEqual({ kind: 'pending' });
    await idem.complete(KEY, '{"result":{"id":"book-1"}}');
    expect(await idem.begin(KEY)).toEqual({ kind: 'replay', text: '{"result":{"id":"book-1"}}' });
    await idem.abort(KEY);
    expect(await idem.begin(KEY)).toEqual({ kind: 'proceed' }); // released → re-claimable
  });

  it('does not cache an oversized body — releases the claim so a retry re-executes', async () => {
    const store = new FakeStore();
    const idem = new Idempotency(store);
    await idem.begin(KEY); // claim
    await idem.complete(KEY, 'x'.repeat(256 * 1024 + 1)); // over MAX_CACHED_BYTES → abort
    expect(store.m.has(KEY)).toBe(false);
    expect(await idem.begin(KEY)).toEqual({ kind: 'proceed' });
  });

  it('is DISABLED (always proceed) when no store is configured', async () => {
    const idem = new Idempotency(null);
    expect(await idem.begin(KEY)).toEqual({ kind: 'proceed' });
    await idem.complete(KEY, 'x'); // no-op, no throw
    await idem.abort(KEY); // no-op, no throw
    expect(await idem.begin(KEY)).toEqual({ kind: 'proceed' });
  });

  it('fails OPEN (proceed, no dedup) when the store errors', async () => {
    const idem = new Idempotency(new ErrorStore());
    expect(await idem.begin(KEY)).toEqual({ kind: 'proceed' });
    await idem.complete(KEY, 'x'); // swallowed
    await idem.abort(KEY); // swallowed
  });

  it('the pending marker is a value no real JSON-RPC response collides with', () => {
    // A cached value is always JSON-RPC text (starts with { or [); the marker is not JSON.
    expect(() => JSON.parse(PENDING_MARKER)).toThrow();
    expect(PENDING_MARKER.startsWith('{')).toBe(false);
    expect(PENDING_MARKER.startsWith('[')).toBe(false);
  });
});
