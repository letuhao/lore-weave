import { computeCatalog, ProviderResult } from '../src/federation/catalog.js';
import { EXTRA_PREFIX_MAP, ProviderConfig } from '../src/config/config.js';

const knowledge: ProviderConfig = { name: 'knowledge', mcpUrl: 'http://k/mcp' };
const glossary: ProviderConfig = { name: 'glossary', mcpUrl: 'http://g/mcp' };
const book: ProviderConfig = { name: 'book', mcpUrl: 'http://b/mcp', prefix: 'book_' };

const tool = (name: string, schema: unknown = { type: 'object' }) => ({
  name,
  description: name,
  inputSchema: schema,
});

describe('computeCatalog', () => {
  it('merges tools and maps each to its provider, sorted by name', () => {
    const c = computeCatalog([
      { provider: knowledge, tools: [tool('memory_search'), tool('memory_forget')] },
      { provider: glossary, tools: [tool('glossary_search')] },
    ]);
    expect(c.toolList.map((t) => t.name)).toEqual([
      'glossary_search',
      'memory_forget',
      'memory_search',
    ]);
    expect(c.toolToProvider.get('memory_search')).toBe(knowledge);
    expect(c.toolToProvider.get('glossary_search')).toBe(glossary);
    expect(c.partial).toBe(false);
    expect(c.version).toHaveLength(16);
  });

  it('is partial when a provider errors, contributing the others (H10)', () => {
    const results: ProviderResult[] = [
      { provider: knowledge, tools: [tool('memory_search')] },
      { provider: glossary, error: new Error('down') },
    ];
    const c = computeCatalog(results);
    expect(c.partial).toBe(true);
    expect(c.toolList.map((t) => t.name)).toEqual(['memory_search']);
  });

  it('version is stable for identical input and changes when a schema changes', () => {
    const a = computeCatalog([{ provider: knowledge, tools: [tool('t', { type: 'object', x: 1 })] }]);
    const b = computeCatalog([{ provider: knowledge, tools: [tool('t', { type: 'object', x: 1 })] }]);
    const c = computeCatalog([{ provider: knowledge, tools: [tool('t', { type: 'object', x: 2 })] }]);
    expect(a.version).toBe(b.version);
    expect(a.version).not.toBe(c.version);
  });

  it('keeps the first provider on a name collision (H7)', () => {
    const c = computeCatalog([
      { provider: knowledge, tools: [tool('dup')] },
      { provider: glossary, tools: [tool('dup')] },
    ]);
    expect(c.toolList).toHaveLength(1);
    expect(c.toolToProvider.get('dup')).toBe(knowledge);
  });

  it('empty input yields an empty, non-partial catalog', () => {
    const c = computeCatalog([]);
    expect(c.toolList).toEqual([]);
    expect(c.partial).toBe(false);
    expect(c.providers).toEqual([]);
  });

  it('drops + warns a mis-prefixed tool, keeps the correctly-prefixed one (C-GW)', () => {
    const warn = jest.fn();
    const c = computeCatalog(
      [{ provider: book, tools: [tool('book_create'), tool('memory_search')] }],
      warn,
    );
    expect(c.toolList.map((t) => t.name)).toEqual(['book_create']);
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('memory_search'));
  });

  it('keeps tools matching ANY of a provider\'s prefixes (memory_ + kg_ + story_) — drops the rest (HIGH-1)', () => {
    const warn = jest.fn();
    const knowledgeMulti: ProviderConfig = {
      name: 'knowledge',
      mcpUrl: 'http://k/mcp',
      prefix: 'memory_',
      extraPrefixes: ['kg_', 'story_'],
    };
    const c = computeCatalog(
      [
        {
          provider: knowledgeMulti,
          // story_search = the universal manuscript find; it was silently dropped in
          // prod until story_ was added to knowledge's extraPrefixes. Pin that it survives.
          tools: [tool('memory_search'), tool('kg_graph_query'), tool('kg_schema_edit'), tool('story_search'), tool('glossary_x')],
        },
      ],
      warn,
    );
    // all three namespaces survive; the foreign-namespace tool is dropped + warned
    expect(c.toolList.map((t) => t.name)).toEqual(['kg_graph_query', 'kg_schema_edit', 'memory_search', 'story_search']);
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('glossary_x'));
  });

  it('an admin provider declaring kg_ keeps kg_admin_* tools (MED-2 mechanism)', () => {
    const knowledgeAdmin: ProviderConfig = {
      name: 'knowledge-admin',
      mcpUrl: 'http://k/mcp/admin',
      prefix: 'kg_',
    };
    const c = computeCatalog(
      [{ provider: knowledgeAdmin, tools: [tool('kg_admin_template_read'), tool('kg_admin_propose_template')] }],
      jest.fn(),
    );
    expect(c.toolList.map((t) => t.name)).toEqual(['kg_admin_propose_template', 'kg_admin_template_read']);
  });

  it('does not police a provider with no prefix (legacy/unmapped)', () => {
    const c = computeCatalog([{ provider: knowledge, tools: [tool('anything_goes')] }], jest.fn());
    expect(c.toolList.map((t) => t.name)).toEqual(['anything_goes']);
  });

  it('reports per-provider availability — a down provider reads available:false (H10)', () => {
    const c = computeCatalog([
      { provider: knowledge, tools: [tool('memory_search')] },
      { provider: glossary, error: new Error('down') },
    ]);
    expect(c.providers).toEqual([
      { name: 'knowledge', available: true },
      { name: 'glossary', available: false },
    ]);
    expect(c.partial).toBe(true);
  });
});

// Track D Wave 0 (0d) — the C-GW prefix gate is a *silent* warn-and-drop, so the
// universal `web_search` tool hosted on provider-registry (logical name `settings`)
// needs `web_` in EXTRA_PREFIX_MAP.settings or it vanishes from the federated catalog.
// This is exactly how `story_search` was once lost (see config.ts EXTRA_PREFIX_MAP docs).
describe('C-GW prefix gate — universal `web_search` on the settings provider', () => {
  const settingsNoExtra: ProviderConfig = { name: 'settings', mcpUrl: 'http://p/mcp', prefix: 'settings_' };
  const settingsWithWeb: ProviderConfig = {
    name: 'settings',
    mcpUrl: 'http://p/mcp',
    prefix: 'settings_',
    extraPrefixes: ['web_'],
  };

  it('WITHOUT `web_` the gate silently drops web_search (the failure mode)', () => {
    const c = computeCatalog([
      { provider: settingsNoExtra, tools: [tool('settings_list_models'), tool('web_search')] },
    ]);
    expect(c.toolList.map((t) => t.name)).toEqual(['settings_list_models']);
    expect(c.toolToProvider.get('web_search')).toBeUndefined();
  });

  it('WITH `web_` the tool survives and routes to provider-registry', () => {
    const c = computeCatalog([
      { provider: settingsWithWeb, tools: [tool('settings_list_models'), tool('web_search')] },
    ]);
    expect(c.toolList.map((t) => t.name)).toContain('web_search');
    expect(c.toolToProvider.get('web_search')).toBe(settingsWithWeb);
  });

  it('EXTRA_PREFIX_MAP.settings declares `web_` (the real config, not a fixture)', () => {
    expect(EXTRA_PREFIX_MAP.settings).toContain('web_');
  });
});
