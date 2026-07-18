import {
  ACTIVATION_TTL_SECONDS,
  InMemoryToolActivationStore,
} from '../src/session/tool-activation-store.js';
import { ToolActivation } from '../src/session/tool-activation.js';
import {
  filterListResponseText,
  findToolsCallIdKeys,
  isFindToolsCall,
  scopeFilterFindToolsBatch,
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

  // item #6 — entitlement-opacity: this key's OWN scope filter stripping a non-empty match set
  // down to zero must be distinguishable from ai-gateway's own "domain genuinely has no tools".
  it('adds a scope_note when THIS filter strips a non-empty match set down to zero', () => {
    const { text } = scopeFilterFindToolsResult(findToolsResponse('kg_search'), SCOPES); // fully out of scope
    const parsed = JSON.parse(text);
    expect(parsed.result.structuredContent.tools).toEqual([]);
    expect(parsed.result.structuredContent.scope_note).toContain('not enabled for this API key');
    // mirrored into the text content block too, like the tools field is.
    expect(JSON.parse(parsed.result.content[0].text).scope_note).toContain('not enabled for this API key');
  });

  it('does NOT add scope_note when the upstream match set was already empty', () => {
    const { text } = scopeFilterFindToolsResult(findToolsResponse(), SCOPES); // no matches at all
    const parsed = JSON.parse(text);
    expect(parsed.result.structuredContent.tools).toEqual([]);
    expect(parsed.result.structuredContent.scope_note).toBeUndefined();
  });

  it('does NOT add scope_note when at least one match survives the filter', () => {
    const { text } = scopeFilterFindToolsResult(findToolsResponse('book_get', 'kg_search'), SCOPES);
    const parsed = JSON.parse(text);
    expect(parsed.result.structuredContent.tools.map((t: { name: string }) => t.name)).toEqual(['book_get']);
    expect(parsed.result.structuredContent.scope_note).toBeUndefined();
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
    expect(isFindToolsCall([call('find_tools')])).toBe(false); // batch out of scope for the SINGLE path
  });
});

describe('findToolsCallIdKeys + scopeFilterFindToolsBatch — batched find_tools anti-oracle', () => {
  const call = (id: unknown, name: string) => ({ jsonrpc: '2.0', id, method: 'tools/call', params: { name } });
  // A batch RESPONSE item: a JSON-RPC object whose result is an MCP CallToolResult carrying matches.
  const ftResponseItem = (id: unknown, ...names: string[]) => {
    const tools = names.map((name) => ({ name, description: name }));
    return { jsonrpc: '2.0', id, result: { content: [{ type: 'text', text: JSON.stringify({ tools }) }], structuredContent: { tools } } };
  };

  it('finds the ids of every find_tools call in a batch (and ignores other calls)', () => {
    const ids = findToolsCallIdKeys([call(1, 'find_tools'), call(2, 'book_get'), call(3, 'find_tools')]);
    expect(ids.has(idKeyOf(1))).toBe(true);
    expect(ids.has(idKeyOf(3))).toBe(true);
    expect(ids.has(idKeyOf(2))).toBe(false);
    expect(ids.size).toBe(2);
  });

  it('scope-filters a batched find_tools result (the single-call path would have missed it)', () => {
    const body = [call(1, 'find_tools')];
    const ftIds = findToolsCallIdKeys(body);
    const upstream = JSON.stringify([ftResponseItem(1, 'book_get', 'kg_search')]); // kg_search out of scope
    const { text, activatedNames } = scopeFilterFindToolsBatch(upstream, SCOPES, ftIds);
    const parsed = JSON.parse(text);
    expect(parsed[0].result.structuredContent.tools.map((t: { name: string }) => t.name)).toEqual(['book_get']);
    expect(JSON.parse(parsed[0].result.content[0].text).tools.map((t: { name: string }) => t.name)).toEqual(['book_get']);
    expect(activatedNames).toEqual(['book_get']);
  });

  it('leaves a non-find_tools item in a mixed batch intact (matches by id only)', () => {
    const body = [call(1, 'find_tools'), call(2, 'book_get')];
    const ftIds = findToolsCallIdKeys(body);
    // item id=2 is book_get's result — happens to carry a name-bearing list of ITS OWN data; must not be filtered.
    const bookResult = { jsonrpc: '2.0', id: 2, result: { structuredContent: { tools: [{ name: 'not_a_tool', description: 'a book row' }] } } };
    const upstream = JSON.stringify([ftResponseItem(1, 'book_get', 'kg_search'), bookResult]);
    const { text } = scopeFilterFindToolsBatch(upstream, SCOPES, ftIds);
    const parsed = JSON.parse(text);
    expect(parsed[0].result.structuredContent.tools.map((t: { name: string }) => t.name)).toEqual(['book_get']); // filtered
    expect(parsed[1].result.structuredContent.tools.map((t: { name: string }) => t.name)).toEqual(['not_a_tool']); // untouched
  });

  it('filters a single-OBJECT response when the upstream collapsed a 1-element batch (id-matched)', () => {
    // ai-gateway returns a single object (not a 1-element array) for a 1-element batch request —
    // the exact anti-oracle bypass. The id-matched object MUST still be scope-filtered.
    const upstream = JSON.stringify(ftResponseItem(1, 'book_get', 'kg_search'));
    const { text, activatedNames } = scopeFilterFindToolsBatch(upstream, SCOPES, new Set([idKeyOf(1)]));
    expect(JSON.parse(text).result.structuredContent.tools.map((t: { name: string }) => t.name)).toEqual(['book_get']);
    expect(activatedNames).toEqual(['book_get']);
    // An object whose id is NOT a find_tools request is left intact (no over-filtering).
    const other = JSON.stringify(ftResponseItem(2, 'book_get', 'kg_search'));
    expect(scopeFilterFindToolsBatch(other, SCOPES, new Set([idKeyOf(1)]))).toEqual({ text: other, activatedNames: [] });
  });

  it('a wildcard key / empty id-set → unchanged + no names', () => {
    const upstream = JSON.stringify([ftResponseItem(1, 'book_get', 'kg_search')]);
    expect(scopeFilterFindToolsBatch(upstream, ['*'], new Set([idKeyOf(1)]))).toEqual({ text: upstream, activatedNames: [] });
    expect(scopeFilterFindToolsBatch(upstream, SCOPES, new Set())).toEqual({ text: upstream, activatedNames: [] });
  });

  // item #6 — same entitlement-opacity fix, batch sibling (both paths share filterOneFindToolsResult).
  it('adds scope_note to a batched find_tools result stripped fully by scope', () => {
    const body = [call(1, 'find_tools')];
    const ftIds = findToolsCallIdKeys(body);
    const upstream = JSON.stringify([ftResponseItem(1, 'kg_search')]); // fully out of scope for SCOPES
    const { text } = scopeFilterFindToolsBatch(upstream, SCOPES, ftIds);
    const parsed = JSON.parse(text);
    expect(parsed[0].result.structuredContent.tools).toEqual([]);
    expect(parsed[0].result.structuredContent.scope_note).toContain('not enabled for this API key');
  });
});

// idKey is internal to scope-filter; mirror its stable key here for the id-set assertions.
function idKeyOf(id: unknown): string {
  if (id === null || id === undefined) return ' null';
  return `${typeof id}:${String(id)}`;
}
