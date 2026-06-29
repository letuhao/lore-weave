import {
  ACTIVATION_TTL_SECONDS,
  InMemoryToolActivationStore,
} from '../src/session/tool-activation-store.js';
import { ToolActivation } from '../src/session/tool-activation.js';
import {
  filterListResponseText,
  isFindToolsCall,
  scopeFilterFindToolsResult,
} from '../src/scope/scope-filter.js';

const SCOPES = ['read', 'domain:book']; // allows book_* read tools, not knowledge

describe('InMemoryToolActivationStore', () => {
  it('round-trips an activated set per session', async () => {
    const s = new InMemoryToolActivationStore();
    await s.activate('sess-1', ['book_get', 'book_list'], 60);
    expect((await s.activated('sess-1', 60)).sort()).toEqual(['book_get', 'book_list']);
    // A different session is isolated (starts empty).
    expect(await s.activated('sess-2', 60)).toEqual([]);
  });

  it('unions across multiple activations', async () => {
    const s = new InMemoryToolActivationStore();
    await s.activate('s', ['book_get'], 60);
    await s.activate('s', ['book_list', 'book_get'], 60);
    expect((await s.activated('s', 60)).sort()).toEqual(['book_get', 'book_list']);
  });

  it('expires a session after its TTL (sliding clock)', async () => {
    let now = 1_000_000;
    const s = new InMemoryToolActivationStore(() => now);
    await s.activate('s', ['book_get'], 10); // expires at now + 10s
    now += 5_000;
    expect(await s.activated('s', 10)).toEqual(['book_get']); // still live (read slides TTL)
    now += 11_000; // past the slid window
    expect(await s.activated('s', 10)).toEqual([]); // expired
  });

  it('activate([]) is a no-op', async () => {
    const s = new InMemoryToolActivationStore();
    await s.activate('s', [], 60);
    expect(await s.activated('s', 60)).toEqual([]);
  });
});

describe('ToolActivation (fail-soft service)', () => {
  it('returns the activated set as a Set', async () => {
    const ta = new ToolActivation(new InMemoryToolActivationStore());
    await ta.activate('s', ['book_get']);
    const set = await ta.activated('s');
    expect(set.has('book_get')).toBe(true);
  });

  it('degrades to an empty set when the store throws (never throws)', async () => {
    const throwing = {
      activate: async () => {
        throw new Error('redis down');
      },
      activated: async () => {
        throw new Error('redis down');
      },
    };
    const ta = new ToolActivation(throwing);
    await expect(ta.activate('s', ['x'])).resolves.toBeUndefined(); // best-effort, no throw
    await expect(ta.activated('s')).resolves.toEqual(new Set()); // minimal surface
  });

  it('uses the 24h activation TTL', () => {
    expect(ACTIVATION_TTL_SECONDS).toBe(86_400);
  });
});

function listResponse(...names: string[]): string {
  return JSON.stringify({
    jsonrpc: '2.0',
    id: 1,
    result: { tools: names.map((name) => ({ name, description: name })) },
  });
}

function listedNames(text: string): string[] {
  return JSON.parse(text).result.tools.map((t: { name: string }) => t.name);
}

describe('filterListResponseText — session collapse (lazy tool-loading)', () => {
  const FULL = ['find_tools', 'book_get', 'book_list'];

  it('a FRESH session (empty activated) advertises only find_tools', () => {
    const out = filterListResponseText(listResponse(...FULL), SCOPES, undefined, new Set());
    expect(listedNames(out)).toEqual(['find_tools']);
  });

  it('a session that activated book_get shows find_tools + book_get (not book_list)', () => {
    const out = filterListResponseText(listResponse(...FULL), SCOPES, undefined, new Set(['book_get']));
    expect(listedNames(out).sort()).toEqual(['book_get', 'find_tools']);
  });

  it('without an activated set, behaves as before (full scoped list)', () => {
    const out = filterListResponseText(listResponse(...FULL), SCOPES, undefined);
    expect(listedNames(out).sort()).toEqual(['book_get', 'book_list', 'find_tools']);
  });

  it('an activated out-of-scope tool is still NOT advertised (scope wins over activation)', () => {
    const text = listResponse('find_tools', 'book_get', 'kg_search');
    // even if kg_search were somehow activated, it is out of scope → never listed
    const out = filterListResponseText(text, SCOPES, undefined, new Set(['book_get', 'kg_search']));
    expect(listedNames(out).sort()).toEqual(['book_get', 'find_tools']);
  });

  it('a wildcard (*) key keeps the full list (no collapse)', () => {
    const out = filterListResponseText(listResponse(...FULL), ['*'], undefined, new Set());
    expect(listedNames(out).sort()).toEqual(['book_get', 'book_list', 'find_tools']);
  });
});

function findToolsResponse(...names: string[]): string {
  const tools = names.map((name) => ({ name, description: name }));
  return JSON.stringify({
    jsonrpc: '2.0',
    id: 2,
    result: { content: [{ type: 'text', text: JSON.stringify({ tools }) }], structuredContent: { tools } },
  });
}

describe('scopeFilterFindToolsResult — anti-oracle + activation harvest', () => {
  it('intersects matches with scope (drops out-of-scope), returns in-scope names to activate', () => {
    const { text, activatedNames } = scopeFilterFindToolsResult(
      findToolsResponse('book_get', 'kg_search'), // kg_search is out of scope for SCOPES
      SCOPES,
    );
    const parsed = JSON.parse(text);
    expect(parsed.result.structuredContent.tools.map((t: { name: string }) => t.name)).toEqual(['book_get']);
    expect(activatedNames).toEqual(['book_get']);
    // the text content block mirrors the filtered structuredContent
    expect(JSON.parse(parsed.result.content[0].text).tools.map((t: { name: string }) => t.name)).toEqual(['book_get']);
  });

  it('a wildcard key passes through unchanged + activates nothing (full surface already)', () => {
    const input = findToolsResponse('book_get', 'kg_search');
    const { text, activatedNames } = scopeFilterFindToolsResult(input, ['*']);
    expect(text).toBe(input);
    expect(activatedNames).toEqual([]);
  });

  it('non-JSON / SSE body is left unchanged + no activation', () => {
    const { text, activatedNames } = scopeFilterFindToolsResult('event: message\ndata: ...', SCOPES);
    expect(text).toBe('event: message\ndata: ...');
    expect(activatedNames).toEqual([]);
  });
});

describe('isFindToolsCall', () => {
  const call = (name: string) => ({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name } });
  it('true for a single find_tools tools/call', () => {
    expect(isFindToolsCall(call('find_tools'))).toBe(true);
  });
  it('false for another tool, a list, or a batch', () => {
    expect(isFindToolsCall(call('book_get'))).toBe(false);
    expect(isFindToolsCall({ jsonrpc: '2.0', id: 1, method: 'tools/list' })).toBe(false);
    expect(isFindToolsCall([call('find_tools')])).toBe(false); // batch out of scope
  });
});
