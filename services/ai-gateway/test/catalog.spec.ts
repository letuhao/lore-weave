import { computeCatalog, ProviderResult } from '../src/federation/catalog.js';
import { ProviderConfig } from '../src/config/config.js';

const knowledge: ProviderConfig = { name: 'knowledge', mcpUrl: 'http://k/mcp' };
const glossary: ProviderConfig = { name: 'glossary', mcpUrl: 'http://g/mcp' };

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
  });
});
