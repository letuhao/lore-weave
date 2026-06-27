import {
  isToolAllowed,
  filterTools,
  knownTool,
  domainScope,
  TOOL_POLICY,
} from '../src/scope/tool-policy.js';
import {
  gateRequestBody,
  isListRequest,
  isWriteRequest,
  countToolCalls,
  filterListResponseText,
} from '../src/scope/scope-filter.js';

// Scopes a typical "knowledge read" key would carry.
const KNOWLEDGE_READ = ['read', domainScope('knowledge')];
const BOOK_READ = ['read', domainScope('book')];

describe('tool-policy.isToolAllowed (default-deny)', () => {
  it('allows a read tool when the key holds tier + its domain', () => {
    expect(isToolAllowed('kg_graph_query', KNOWLEDGE_READ)).toBe(true);
    expect(isToolAllowed('book_get', BOOK_READ)).toBe(true);
  });

  it('denies an unknown / unclassified tool (H-E fail-closed)', () => {
    expect(isToolAllowed('totally_made_up_tool', KNOWLEDGE_READ)).toBe(false);
    expect(isToolAllowed('kg_admin_template_read', ['read', domainScope('knowledge')])).toBe(false);
    expect(isToolAllowed('book_delete', ['write_confirm', domainScope('book')])).toBe(false);
  });

  it('denies when the tier scope is missing', () => {
    // has knowledge domain but only read tier → cannot reach a write_auto tool
    expect(isToolAllowed('memory_remember', KNOWLEDGE_READ)).toBe(false);
    expect(isToolAllowed('memory_remember', ['write_auto', domainScope('knowledge')])).toBe(true);
  });

  it('denies when the domain scope is missing (a knowledge key cannot touch books)', () => {
    expect(isToolAllowed('book_get', KNOWLEDGE_READ)).toBe(false);
  });

  it('fails closed when the key holds tier scopes but NO domain scope', () => {
    expect(isToolAllowed('kg_graph_query', ['read'])).toBe(false);
    expect(isToolAllowed('book_get', ['read', 'write_auto'])).toBe(false);
  });

  it('requires EVERY touched domain for a cross-domain tool (H-F)', () => {
    const t = 'translation_start_extraction'; // touches translation + glossary
    expect(isToolAllowed(t, ['write_confirm', domainScope('translation')])).toBe(false);
    expect(isToolAllowed(t, ['write_confirm', domainScope('glossary')])).toBe(false);
    expect(
      isToolAllowed(t, ['write_confirm', domainScope('translation'), domainScope('glossary')]),
    ).toBe(true);
    // composition_generate touches composition+glossary+knowledge
    expect(
      isToolAllowed('composition_generate', [
        'write_confirm',
        domainScope('composition'),
        domainScope('glossary'),
      ]),
    ).toBe(false);
  });

  it('jobs/settings are their own explicit domain (never implied by another)', () => {
    expect(isToolAllowed('jobs_list', ['read', domainScope('knowledge')])).toBe(false);
    expect(isToolAllowed('jobs_list', ['read', domainScope('jobs')])).toBe(true);
    expect(isToolAllowed('settings_get_profile', ['read', domainScope('book')])).toBe(false);
    expect(isToolAllowed('settings_get_profile', ['read', domainScope('settings')])).toBe(true);
  });

  it('the wildcard scope bypasses all gating (dev/smoke key)', () => {
    expect(isToolAllowed('anything_at_all', ['*'])).toBe(true);
    expect(isToolAllowed('book_chapter_purge', ['*'])).toBe(true);
  });

  it('never classifies admin/secret/destructive tools (absent → denied)', () => {
    for (const t of ['kg_admin_propose_template', 'glossary_admin_propose_create', 'settings_provider_create', 'settings_provider_update_secret', 'book_delete', 'book_purge']) {
      expect(knownTool(t)).toBe(false);
    }
  });

  it('classifies settings_model_delete as write_confirm in the settings domain (drift fix)', () => {
    expect(isToolAllowed('settings_model_delete', ['write_confirm', domainScope('settings')])).toBe(true);
    // Not reachable by a lesser tier or wrong domain.
    expect(isToolAllowed('settings_model_delete', ['write_auto', domainScope('settings')])).toBe(false);
    expect(isToolAllowed('settings_model_delete', ['write_confirm', domainScope('book')])).toBe(false);
  });
});

describe('tool-policy.filterTools', () => {
  it('strips out-of-scope and unknown tools, keeps in-scope', () => {
    const tools = [
      { name: 'kg_graph_query' },
      { name: 'book_get' },
      { name: 'memory_remember' }, // write_auto — out of a read key's reach
      { name: 'mystery_tool' }, // unknown
    ];
    const out = filterTools(tools, KNOWLEDGE_READ);
    expect(out.map((t) => t.name)).toEqual(['kg_graph_query']);
  });

  it('wildcard returns the list untouched', () => {
    const tools = [{ name: 'a' }, { name: 'b' }];
    expect(filterTools(tools, ['*'])).toBe(tools);
  });
});

describe('scope-filter.gateRequestBody (request gate)', () => {
  it('returns null (allow) for an in-scope tools/call', () => {
    const body = { jsonrpc: '2.0', method: 'tools/call', params: { name: 'kg_graph_query' }, id: 1 };
    expect(gateRequestBody(body, KNOWLEDGE_READ)).toBeNull();
  });

  it('denies an out-of-scope tools/call with a JSON-RPC error (no relay)', () => {
    const body = { jsonrpc: '2.0', method: 'tools/call', params: { name: 'book_get' }, id: 7 };
    const denial = gateRequestBody(body, KNOWLEDGE_READ) as { error: { code: number; message: string }; id: number };
    expect(denial).not.toBeNull();
    expect(denial.id).toBe(7);
    expect(denial.error.code).toBe(-32601);
    // anti-oracle: same wording for unknown vs out-of-scope
    expect(denial.error.message).toContain("not available to this key");
  });

  it('denies an unknown tool call (H-E)', () => {
    const body = { jsonrpc: '2.0', method: 'tools/call', params: { name: 'nope' }, id: 1 };
    expect(gateRequestBody(body, KNOWLEDGE_READ)).not.toBeNull();
  });

  it('does not gate non-call methods (initialize, tools/list, ping)', () => {
    expect(gateRequestBody({ method: 'initialize', id: 1 }, KNOWLEDGE_READ)).toBeNull();
    expect(gateRequestBody({ method: 'tools/list', id: 1 }, KNOWLEDGE_READ)).toBeNull();
    expect(gateRequestBody({ method: 'ping', id: 1 }, KNOWLEDGE_READ)).toBeNull();
  });

  it('rejects the WHOLE batch (fail-closed) if any call is denied', () => {
    const body = [
      { jsonrpc: '2.0', method: 'tools/call', params: { name: 'kg_graph_query' }, id: 1 },
      { jsonrpc: '2.0', method: 'tools/call', params: { name: 'book_get' }, id: 2 },
    ];
    const denial = gateRequestBody(body, KNOWLEDGE_READ) as Array<{ id: number }>;
    expect(Array.isArray(denial)).toBe(true);
    expect(denial.map((d) => d.id)).toEqual([2]);
  });

  it('allows a batch where every call is in-scope', () => {
    const body = [
      { jsonrpc: '2.0', method: 'tools/call', params: { name: 'kg_graph_query' }, id: 1 },
      { jsonrpc: '2.0', method: 'tools/list', id: 2 },
    ];
    expect(gateRequestBody(body, KNOWLEDGE_READ)).toBeNull();
  });

  it('wildcard bypasses the gate', () => {
    const body = { jsonrpc: '2.0', method: 'tools/call', params: { name: 'book_chapter_purge' }, id: 1 };
    expect(gateRequestBody(body, ['*'])).toBeNull();
  });
});

describe('scope-filter.isWriteRequest (rate-limit fail-policy classifier)', () => {
  it('classifies a write-tier tools/call as a write', () => {
    expect(isWriteRequest({ method: 'tools/call', params: { name: 'book_create' } })).toBe(true); // write_auto
    expect(isWriteRequest({ method: 'tools/call', params: { name: 'kg_propose_fact' } })).toBe(true); // write_confirm
  });
  it('classifies reads / list / initialize / unknown as NOT a write', () => {
    expect(isWriteRequest({ method: 'tools/call', params: { name: 'book_get' } })).toBe(false); // read
    expect(isWriteRequest({ method: 'tools/call', params: { name: 'glossary_web_search' } })).toBe(false); // paid_read
    expect(isWriteRequest({ method: 'tools/list' })).toBe(false);
    expect(isWriteRequest({ method: 'initialize' })).toBe(false);
    expect(isWriteRequest({ method: 'tools/call', params: { name: 'unknown_tool' } })).toBe(false);
    expect(isWriteRequest(undefined)).toBe(false);
  });
  it('a batch is a write if ANY call is a write', () => {
    expect(isWriteRequest([
      { method: 'tools/call', params: { name: 'book_get' } },
      { method: 'tools/call', params: { name: 'book_create' } },
    ])).toBe(true);
  });
});

describe('scope-filter.countToolCalls (rate-limit weight)', () => {
  it('counts tools/call entries (single + batch); 0 for non-calls', () => {
    expect(countToolCalls({ method: 'tools/call', params: { name: 'book_get' } })).toBe(1);
    expect(countToolCalls({ method: 'tools/list' })).toBe(0);
    expect(countToolCalls([
      { method: 'tools/call', params: { name: 'book_get' } },
      { method: 'tools/list' },
      { method: 'tools/call', params: { name: 'book_create' } },
    ])).toBe(2);
    expect(countToolCalls(undefined)).toBe(0);
  });
});

describe('scope-filter.isListRequest', () => {
  it('detects a tools/list request (single + batch)', () => {
    expect(isListRequest({ method: 'tools/list', id: 1 })).toBe(true);
    expect(isListRequest([{ method: 'ping' }, { method: 'tools/list' }])).toBe(true);
    expect(isListRequest({ method: 'tools/call' })).toBe(false);
    expect(isListRequest(undefined)).toBe(false);
  });
});

describe('scope-filter.filterListResponseText (response filter)', () => {
  const resp = (tools: string[]) =>
    JSON.stringify({ jsonrpc: '2.0', result: { tools: tools.map((name) => ({ name })) }, id: 1 });

  it('strips out-of-scope tools from the advertised catalogue', () => {
    const out = filterListResponseText(
      resp(['kg_graph_query', 'book_get', 'memory_remember', 'unknown_x']),
      KNOWLEDGE_READ,
    );
    const parsed = JSON.parse(out);
    expect(parsed.result.tools.map((t: { name: string }) => t.name)).toEqual(['kg_graph_query']);
  });

  it('fails closed (empty list) when the response is not parseable JSON', () => {
    const out = filterListResponseText('event: message\ndata: not json', KNOWLEDGE_READ);
    const parsed = JSON.parse(out);
    expect(parsed.result.tools).toEqual([]);
  });

  it('logs federated tools missing from the policy table (drift signal)', () => {
    const warn = jest.fn();
    filterListResponseText(resp(['kg_graph_query', 'brand_new_tool']), KNOWLEDGE_READ, {
      warn,
    } as unknown as import('@nestjs/common').Logger);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('brand_new_tool'));
  });

  it('wildcard returns the response untouched', () => {
    const text = resp(['a', 'b']);
    expect(filterListResponseText(text, ['*'])).toBe(text);
  });

  it('filters each message of a batch response', () => {
    const batch = JSON.stringify([
      { result: { tools: [{ name: 'kg_graph_query' }, { name: 'book_get' }] }, id: 1 },
    ]);
    const out = JSON.parse(filterListResponseText(batch, KNOWLEDGE_READ));
    expect(out[0].result.tools.map((t: { name: string }) => t.name)).toEqual(['kg_graph_query']);
  });
});

describe('policy table sanity', () => {
  it('every entry has a valid tier and at least one domain', () => {
    const tiers = new Set(['read', 'paid_read', 'write_auto', 'write_confirm']);
    for (const [name, pol] of Object.entries(TOOL_POLICY)) {
      expect(tiers.has(pol.tier)).toBe(true);
      expect(pol.domains.length).toBeGreaterThan(0);
      expect(name).toMatch(/^[a-z]/);
    }
  });
});
